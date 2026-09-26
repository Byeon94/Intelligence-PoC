"""여신 탭 메인 화면 — 증권담보대출 수요 레이더 / 우리사주 금융 수요 리드 (DART 실데이터).

데이터 소스 (전부 DART OpenAPI 실데이터, 추정치 없음):
  - 증권담보대출(상속·증여) 리드 : 시가총액 상위 코스피 200 + 코스닥 100종목
    (_scan_universe, equity.listed_snapshot 기준)마다 majorstock.json(대량보유 상황보고)을
    조회해, 실제 `report_resn`(보고사유)에 '상속'·'증여'가 포함된 건만 잡는다.
    지분가치는 (보고서상 보유주식 증감수 × 시세 스냅샷 종가)로 계산한 추정치.
    한때 코스피·코스닥 전 종목(~2,500개)으로 넓혔다가 DART 호출량 때문에 수집이 수 분씩
    걸리고 opendart 남용 방지 차단까지 유발해(2026-09-20) 중대형주 300종목으로 좁혔다.
  - 우리사주 금융 수요 리드 : list.json(공시검색)을 corp_code 없이 시장 전체 주요사항보고(B)·
    발행공시(C)를 페이지 단위로 훑어(_esop_sweep) 두 갈래로 분류한다.
      · report_nm 에 '유상증자' → 이미 상장된 회사의 유상증자(위 300종목 대상만).
      · '증권신고서(지분증권)'만 있고 현재 상장사 목록(listed_snapshot 전체)에 없는 회사 →
        상장 전 IPO(공모). 신규 IPO 후보는 어느 시장에도 아직 속하지 않아 전 시장을 훑는다.
    (배정 비율·수요예측 금액 등 세부 수치는 공시 원문에만 있어 여기서는 만들어내지 않는다.)
  - 상속·증여/우리사주 뉴스 동향은 별도 모듈(inherit_news.py·esop_news.py)이다.

해설(note)은 공시에 실제로 찍힌 값(회사명·보고사유·날짜·지분율)만으로 만든 고정 문구다 —
LLM 이 수치를 지어낼 위험을 피하려고 여기서는 Gemini 를 호출하지 않는다.

수집(get_leads(force=True))은 /internal/warmup 배치에서만 한다. 일반 웹 요청은 DART 를 절대
직접 호출하지 않고 저장된 스냅샷만 읽는다(오늘자가 없으면 가장 최근 스냅샷을 "stale"로,
그마저 없으면 "pending"). 라이브 요청이 재수집을 트리거하던 예전 방식이 배치 밖에서도
대량 호출을 일으켜 opendart 차단을 유발한 적이 있어(2026-09-20) 제거했다.

수집 결과를 믿을 수 없으면(종목 스냅샷·corp_code 매핑 실패, DART 실패율 과다, 공시 스캔 중
페이지 실패) RuntimeError 로 중단해, 기존 정상 스냅샷을 빈/부분 결과로 덮어쓰지 않는다.
DART 호출은 전역 스로틀로 초당 약 4건으로 제한한다(스레드 동시성만 믿고 몰아 보내면
opendart 가 해당 IP 연결을 끊는 현상이 실제로 있었음).
"""
from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

import requests

from capital._datago import to_float
from main.config import get_settings
from main.snapshot_store import get_snapshot, latest_snapshot, save_snapshot
from main.utils import now_kst, today_iso, today_kst, ymd_to_iso

from .corp_map import corp_code
from .equity import listed_snapshot

logger = logging.getLogger(__name__)

_MAJORSTOCK_URL = "https://opendart.fss.or.kr/api/majorstock.json"
_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
_TABLE = "credit_lead_snapshots"

_MAX_WORKERS = 5
_LOOKBACK_DAYS = 60
_session = requests.Session()

# DART 쪽 남용 방지 차단을 피하기 위한 전역 호출 속도 제한(스레드 공유) — 초당 약 4건.
_MIN_CALL_INTERVAL = 0.25
_rate_lock = threading.Lock()
_last_call_at = [0.0]


def _throttle() -> None:
    with _rate_lock:
        now = time.monotonic()
        wait = _last_call_at[0] + _MIN_CALL_INTERVAL - now
        if wait > 0:
            time.sleep(wait)
        _last_call_at[0] = max(now, _last_call_at[0]) + _MIN_CALL_INTERVAL


class _CallHealth:
    """종목별 majorstock 호출 성공/실패 건수를 스레드 안전하게 센다.

    실패율이 너무 높으면(=DART 가 이 IP를 일시 차단한 상태) 텅 빈 결과를 '정상 수집'으로
    착각해 저장하지 않도록 check() 가 예외를 던진다.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.ok = 0
        self.fail = 0

    def record(self, success: bool) -> None:
        with self._lock:
            if success:
                self.ok += 1
            else:
                self.fail += 1

    def failing(self) -> bool:
        """충분히 시도했는데(20건 이상) 실패율이 70%를 넘는지 — 조기 중단 판단용."""
        total = self.ok + self.fail
        return total >= 20 and self.fail / total > 0.7

    def check(self, label: str) -> None:
        total = self.ok + self.fail
        # 시도한 호출이 하나라도 있는데 전부 실패 → 명백한 장애. 일부 종목만 실패할 수
        # 있으므로 그 외엔 표본이 충분할 때(10건 이상)만 70% 기준을 본다.
        if total > 0 and self.ok == 0:
            raise RuntimeError(
                f"{label}: DART 호출이 전부 실패했습니다({self.fail}/{total}) — "
                "일시적인 API 차단/장애로 보고 이번 수집 결과는 저장하지 않습니다."
            )
        if total >= 10 and self.fail / total > 0.7:
            raise RuntimeError(
                f"{label}: DART 호출 실패율이 너무 높습니다({self.fail}/{total}) — "
                "일시적인 API 차단/장애로 보고 이번 수집 결과는 저장하지 않습니다."
            )


_INHERIT_RE = re.compile(r"상속|증여")
_RIGHTS_KEYWORD_RE = re.compile(r"유상증자")
_EQUITY_REG_RE = re.compile(r"증권신고서\(지분증권\)")

_KOSPI_TOP_N = 200
_KOSDAQ_TOP_N = 100


def _scan_universe() -> list[dict]:
    """증권담보대출(상속·증여) 리드 스캔 대상 — 시가총액 상위 코스피 200·코스닥
    100종목만(모듈 docstring 참고). 시가총액이 없는(데이터 누락) 종목은 제외한다."""
    snap = listed_snapshot()
    kospi = sorted(
        (s for s in snap if s.get("market") == "KOSPI" and s.get("market_cap")),
        key=lambda s: s["market_cap"], reverse=True,
    )[:_KOSPI_TOP_N]
    kosdaq = sorted(
        (s for s in snap if s.get("market") == "KOSDAQ" and s.get("market_cap")),
        key=lambda s: s["market_cap"], reverse=True,
    )[:_KOSDAQ_TOP_N]
    return kospi + kosdaq


def _listed_corp_codes() -> set[str]:
    """현재 상장(코스피+코스닥 등 전 시장)된 종목의 DART corp_code 집합.

    우리사주 리드에서 '증권신고서(지분증권)'을 낸 회사가 이미 상장돼 있으면 유상증자
    계열 서류(중복)로 보고, 상장 목록에 없으면 IPO(공모) 건으로 분류하는 데 쓴다.
    corp_code() 조회는 캐시된 매핑에서 찾는 로컬 조회라 네트워크 호출이 없다.
    """
    out: set[str] = set()
    for s in listed_snapshot():
        cc = corp_code(s.get("code") or "")
        if cc:
            out.add(cc)
    return out


def _majorstock(cc: str, key: str, health: _CallHealth) -> list[dict]:
    _throttle()
    try:
        resp = _session.get(_MAJORSTOCK_URL, params={"crtfc_key": key, "corp_code": cc}, timeout=15)
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.info("majorstock 조회 실패(%s): %s", cc, exc)
        health.record(False)
        return []
    health.record(True)
    if data.get("status") != "000":
        return []
    return data.get("list") or []


def _list_page(key: str, pblntf_ty: str, bgn_de: str, end_de: str, page: int) -> dict:
    """list.json 한 페이지. 통신·파싱 실패는 1회만 재시도하고, 그래도 안 되면 예외."""
    params = {
        "crtfc_key": key, "pblntf_ty": pblntf_ty, "bgn_de": bgn_de, "end_de": end_de,
        "page_no": page, "page_count": 100,
    }
    for attempt in (1, 2):
        _throttle()
        try:
            return _session.get(_LIST_URL, params=params, timeout=20).json()
        except (requests.RequestException, ValueError) as exc:
            if attempt == 2:
                raise RuntimeError(
                    f"공시 전체 스캔 실패(pblntf_ty={pblntf_ty}, page={page}): {exc} — "
                    "부분 결과를 저장하지 않도록 이번 수집을 중단합니다."
                ) from exc
            time.sleep(1.0)
    raise AssertionError("unreachable")


def _esop_sweep(key: str, bgn_de: str) -> list[dict]:
    """corp_code 없이 시장 전체 주요사항보고(B)·발행공시(C)를 페이지 단위로 훑는다.

    corp_cls 를 지정하지 않는다 — IPO(공모) 후보 회사는 아직 코스피·코스닥 어느
    시장에도 속하지 않아 corp_cls=Y 등으로 좁히면 애초에 조회 대상에서 빠진다.
    중간 페이지가 실패하면(또는 DART 가 '조회 없음(013)' 외 오류를 주면) 일부만 모은 목록을
    전체처럼 저장하지 않도록 RuntimeError 를 올린다.
    """
    end_de = today_kst().strftime("%Y%m%d")
    rows: list[dict] = []
    for pblntf_ty in ("B", "C"):
        page = 1
        while page <= 50:  # 안전장치 — 정상 상황에서 60일치가 이 이상 나오진 않는다
            data = _list_page(key, pblntf_ty, bgn_de, end_de, page)
            status = data.get("status")
            if status == "013":  # 조회된 데이터 없음
                break
            if status != "000":
                raise RuntimeError(
                    f"공시 전체 스캔 DART 오류(pblntf_ty={pblntf_ty}, page={page}): "
                    f"{data.get('message') or status}"
                )
            rows.extend(data.get("list") or [])
            if page >= int(data.get("total_page") or 1):
                break
            page += 1
    return rows


def _inherit_note(name: str, resn: str, stake_pct: float | None, value_won: float | None) -> str:
    bits = [f"{name} 대주주(특수관계인 포함) 지분 변동 공시 — 보고사유 '{resn}'."]
    if stake_pct is not None:
        bits.append(f"이번 신고분 지분율 {stake_pct:g}%.")
    if value_won:
        bits.append(f"현재가 기준 추정 지분가치 약 {_eok_text(value_won)}.")
    bits.append("상속·증여세 재원 마련을 위한 증권담보대출 수요로 이어질 수 있는 이벤트입니다.")
    return " ".join(bits)


def _rights_note(name: str, title: str) -> str:
    return (
        f"{name} '{title}' 공시. 자본시장법상 유상증자 시 우리사주조합은 배정 물량의 "
        "20% 한도 내에서 우선배정을 받을 수 있어, 조합원 대상 우리사주 취득자금대출 수요로 "
        "이어질 수 있는 이벤트입니다. 실제 배정 여부·비율은 공시 원문 확인이 필요합니다."
    )


def _ipo_note(name: str, title: str) -> str:
    return (
        f"{name} '{title}' 공시(아직 상장 전 회사). 코스피·코스닥 신규상장(IPO) 시에도 "
        "우리사주조합에 공모 물량의 20% 한도 내 우선배정 기회가 있어, 상장 직후 우리사주 "
        "취득자금대출 수요로 이어질 수 있는 이벤트입니다. 배정 여부·비율은 증권신고서 "
        "원문 확인이 필요합니다."
    )


def _eok_text(won: float) -> str:
    eok = won / 1e8
    if eok >= 10000:
        return f"{eok / 10000:.1f}조원"
    return f"{eok:,.0f}억원"


def _scan_inherit(s: dict, key: str, cutoff: str, health: _CallHealth) -> list[dict]:
    code, name, price = s["code"], s["name"], s.get("close")
    cc = corp_code(code)
    if not cc:
        return []

    seen: set[str] = set()
    out: list[dict] = []
    for it in _majorstock(cc, key, health):
        rcept_dt = (it.get("rcept_dt") or "").strip()
        if rcept_dt < cutoff:
            continue
        resn = (it.get("report_resn") or "").strip()
        if not _INHERIT_RE.search(resn):
            continue
        rcept_no = (it.get("rcept_no") or "").strip()
        dedup = rcept_no + resn
        if not rcept_no or dedup in seen:
            continue
        seen.add(dedup)

        shares = to_float(it.get("stkqy_irds")) or to_float(it.get("stkqy"))
        stake_pct = to_float(it.get("stkrt"))
        value_won = abs(shares) * price if shares and price else None
        out.append({
            "kind": "inherit",
            "code": code,
            "name": name,
            "date": ymd_to_iso(rcept_dt),
            "reporter": (it.get("repror") or "").strip(),
            "reason": resn,
            "stake_pct": stake_pct,
            "value_won": value_won,
            "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + rcept_no,
            "note": _inherit_note(name, resn, stake_pct, value_won),
        })
    return out


def _latest_per_company(esop: list[dict]) -> list[dict]:
    """같은 회사가 정정·효력발생안내 등으로 여러 건 잡히면 최신 1건만 남긴다."""
    best: dict[str, dict] = {}
    for it in esop:
        key = it["name"]
        cur = best.get(key)
        if cur is None or it["date"] > cur["date"]:
            best[key] = it
    return list(best.values())


def _esop_monthly_summary(esop: list[dict]) -> list[dict]:
    counts: dict[str, dict[str, int]] = {}
    for it in esop:
        month = it["date"][:7]  # "YYYY-MM"
        row = counts.setdefault(month, {"rights": 0, "ipo": 0})
        row[it["category"]] += 1
    return [
        {"month": m, "rights": counts[m]["rights"], "ipo": counts[m]["ipo"]}
        for m in sorted(counts, reverse=True)
    ]


def _collateral_monthly_summary(collateral: list[dict]) -> list[dict]:
    """우리사주(esop_monthly)와 짝을 맞춘 증권담보대출(상속·증여) 월별 집계.

    뉴스 동향은 별도 API(inherit_news)라 여기엔 DART 건수만 들어간다 — 뉴스까지 합친
    월별 집계·AI 브리핑은 credit/lead_briefing.py 에서 뉴스와 함께 계산한다.
    """
    counts: dict[str, int] = {}
    for it in collateral:
        month = it["date"][:7]
        counts[month] = counts.get(month, 0) + 1
    return [{"month": m, "count": counts[m]} for m in sorted(counts, reverse=True)]


def _daily_counts(*lists: list[dict]) -> dict[str, int]:
    """날짜별 DART 리드 건수 — 화면 목록은 잘라서 내려주므로 KPI(최근 7일 등)는 이 값으로 센다."""
    counts: dict[str, int] = {}
    for items in lists:
        for it in items:
            if it.get("date"):
                counts[it["date"]] = counts.get(it["date"], 0) + 1
    return counts


def _collect_collateral(stocks: list[dict], key: str, cutoff: str) -> list[dict]:
    """300종목 majorstock 병렬 조회 → 상속·증여 보고사유 건(최신순). 실패율 과다면 RuntimeError."""
    health = _CallHealth()
    out: list[dict] = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
        futures = [ex.submit(_scan_inherit, s, key, cutoff, health) for s in stocks]
        for f in as_completed(futures):
            out.extend(f.result())
            # DART 가 이 IP를 막은 상태로 보이면(초반 실패율이 이미 높음) 남은 종목을 계속
            # 호출하며 수 분을 낭비하지 않도록 아직 시작 안 한 요청은 취소한다.
            if health.failing():
                for pending in futures:
                    pending.cancel()
                break
    health.check("증권담보대출(상속·증여) 스캔")
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


def _collect_esop(stocks: list[dict], key: str, cutoff: str) -> list[dict]:
    """시장 전체 공시 스캔 → 유상증자(300종목 대상)·IPO(상장 전 회사) 리드, 회사별 최신 1건(최신순)."""
    listed_ccs = _listed_corp_codes()
    # 유상증자(이미 상장된 회사 대상)는 증권담보대출 리드와 같은 시가총액 상위
    # 코스피 200·코스닥 100(=stocks)으로 좁힌다. IPO(상장 전 공모)는 애초에 이 목록에
    # 없는 회사들이라 전 시장 그대로 둔다.
    top_ccs = {cc for s in stocks if (cc := corp_code(s.get("code") or ""))}
    esop: list[dict] = []
    seen_rcept: set[str] = set()
    for it in _esop_sweep(key, cutoff):
        title = (it.get("report_nm") or "").strip()
        is_rights = bool(_RIGHTS_KEYWORD_RE.search(title))
        is_ipo_candidate = not is_rights and bool(_EQUITY_REG_RE.search(title))
        if not (is_rights or is_ipo_candidate):
            continue
        cc = (it.get("corp_code") or "").strip()
        if is_ipo_candidate and cc in listed_ccs:
            continue  # 이미 상장된 회사의 증권신고서(지분증권) — 유상증자 계열, 중복 제외
        if is_rights and cc not in top_ccs:
            continue  # 유상증자는 시가총액 상위 코스피 200·코스닥 100 대상만
        rcept_no = (it.get("rcept_no") or "").strip()
        if not rcept_no or rcept_no in seen_rcept:
            continue
        seen_rcept.add(rcept_no)
        name = (it.get("corp_name") or "").strip()
        category = "rights" if is_rights else "ipo"
        esop.append({
            "category": category,
            "code": None,
            "name": name,
            "date": ymd_to_iso(it.get("rcept_dt")),
            "title": title,
            "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + rcept_no,
            "note": (_rights_note if category == "rights" else _ipo_note)(name, title),
        })
    esop = _latest_per_company(esop)
    esop.sort(key=lambda x: x["date"], reverse=True)
    return esop


def _collect() -> dict:
    key = get_settings().dart_api_key
    now = now_kst()
    if not key:
        return {"collateral": [], "esop": [], "esop_monthly": [], "collateral_monthly": [],
                "dart_daily": {}, "universe": 0, "generated_at": now.isoformat()}

    # 종목 스냅샷(data.go.kr)이 실패하면 스캔 대상이 0개가 돼 빈 결과가 '정상 수집'으로
    # 저장된다 — 기존 스냅샷을 덮어쓰지 않도록 중단한다.
    stocks = _scan_universe()
    if not stocks:
        raise RuntimeError("상장종목 스냅샷을 불러오지 못했습니다(스캔 대상 0종목) — 이번 수집은 건너뜁니다.")

    # corp_code 매핑이 안 내려오면 모든 종목이 "매핑 없음"으로 스킵돼 API 콜 자체가 안
    # 나가고, 실패율 감지도 못 걸린다. 그래서 미리 하나만 찍어 확인한다.
    if not corp_code("005930"):
        raise RuntimeError("DART corp_code 매핑을 불러오지 못했습니다(삼성전자 조회 실패) — 이번 수집은 건너뜁니다.")

    cutoff = (today_kst() - timedelta(days=_LOOKBACK_DAYS)).strftime("%Y%m%d")
    collateral = _collect_collateral(stocks, key, cutoff)
    esop = _collect_esop(stocks, key, cutoff)

    return {
        # 목록은 화면 표시용으로 자르고, 건수(월별·일별)는 전체 목록 기준으로 센다.
        "collateral": collateral[:30],
        "esop": esop[:60],
        "esop_monthly": _esop_monthly_summary(esop),
        "collateral_monthly": _collateral_monthly_summary(collateral),
        "dart_daily": _daily_counts(collateral, esop),
        "universe": len(stocks),
        "generated_at": now.isoformat(),
    }


_SCHEMA_V = 7  # v7: 실패율 감지 보정(표본 적어도 전부 실패면 즉시 감지) + 라이브 요청은
                # 재수집을 트리거하지 않고 배치(warmup)만 수집하도록 변경
                # (dart_daily 는 v7 에 추가된 선택 필드 — 없으면 화면이 목록으로 센다)


def get_leads(force: bool = False) -> dict:
    """force=True 는 /internal/warmup 배치 전용 — 이 값 없이는 절대 DART 를 호출하지 않고
    이미 저장된 스냅샷만 읽는다. 수집이 실패하면 예외를 올리고 스냅샷은 그대로 둔다
    (이후 일반 요청은 가장 최근 스냅샷을 stale 로 받는다)."""
    today = today_iso()
    if not force:
        snap = get_snapshot(_TABLE, today)
        if snap is not None and snap.get("v") == _SCHEMA_V:
            return snap

        stale = latest_snapshot(_TABLE)
        if stale is not None:
            return {**stale, "stale": True}

        return {"collateral": [], "esop": [], "esop_monthly": [], "collateral_monthly": [],
                "universe": 0, "generated_at": None, "pending": True, "v": _SCHEMA_V}

    payload = _collect()
    payload["v"] = _SCHEMA_V
    save_snapshot(_TABLE, today, payload)
    return payload
