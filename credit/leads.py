"""여신 탭 메인 화면 — 증권담보대출 수요 레이더 / 우리사주 금융 수요 (실데이터).

대상(증권담보대출 리드, _scan_universe): 시가총액 기준 코스피 상위 200종목 + 코스닥
상위 100종목(equity.listed_snapshot 기준). 처음엔 상위 30종목만, 그다음 코스피만으로
좁혀봤더니 상속·증여 이벤트 자체가 원래 드물어 리드가 거의 안 잡혀 코스피·코스닥
전체(~2,500종목)로 확대했었는데, 종목 수만큼 DART를 호출하다 보니 수집이 수 분씩
걸리고 opendart 쪽 남용 방지 차단까지 유발한 적이 있어(2026-09-20) 중대형주 위주로
다시 좁혔다. 우리사주(유상증자·IPO) 리드는 corp_code 없이 시장 전체를 페이지 단위로
훑는 방식(_esop_sweep)이라 이 종목 수 제한과 무관하다 — 특히 신규 IPO(공모) 후보는
아직 코스피·코스닥 어느 시장에도 속하지 않아(listed_snapshot에 없음) 애초에
_scan_universe 로는 잡을 수도 없는 대상이라, IPO 리드만큼은 처음부터 전 시장(상장
전 회사 포함) 대상으로 스캔해야 한다. _listed_corp_codes()(우리사주 리드의 IPO/유상증자
중복 판별용)도 _scan_universe가 아니라 listed_snapshot() 전체를 그대로 쓴다.

데이터 소스 (전부 DART OpenAPI 실데이터, 추정치 없음):
  - 증권담보대출 수요 리드 : majorstock.json(대량보유 상황보고)의 실제 `report_resn`(보고사유)
    필드에 '상속'·'증여'가 포함된 건만 잡는다(회사마다 조회해야 하는 API라 종목 수만큼
    호출한다).
    지분가치는 (보고서상 보유주식 증감수 × 시세 스냅샷 종가)로 계산한 추정치.
  - 우리사주 금융 수요 리드 : list.json(공시검색)을 corp_code 없이 시장 전체를 페이지
    단위로 훑어(주요사항보고 B, 발행공시 C) 두 갈래로 분류한다.
      · report_nm에 '유상증자'가 포함 → 이미 상장된 회사의 유상증자(코스피·코스닥 등
        전 시장 대상 — 코스피로만 좁히면 데이터가 왜곡돼 전 시장으로 확대).
      · report_nm에 '증권신고서(지분증권)'만 포함되고, 그 회사가 현재 상장사 목록에
        없으면 → 아직 상장 전인 IPO(공모) 건으로 분류(상장사가 같은 서류를 내는 경우는
        유상증자 계열로 이미 잡히므로 중복 방지 차원에서 제외).
    (배정 비율·수요예측 금액 등 세부 수치는 공시 원문에만 있어 여기서는 만들어내지 않는다.)
  - 상속·증여 뉴스 동향(참고용) : DART 신고 의무 기준(5% 대량보유·1%p 변동) 미만이거나
    아직 공시 전인 건을 보완하려고 네이버 뉴스에서 '오너 지분 상속/증여' 관련 기사를 모아
    Gemini로 관련 없는 기사(상속세 정책 등)를 걸러낸다(credit/inherit_news.py, 별도 API).

해설(note)은 공시에 실제로 찍힌 값(회사명·보고사유·날짜·지분율)만으로 구성한 고정 문구다.
LLM이 수치를 지어낼 위험을 피하려고 여기서는 Gemini를 호출하지 않는다.

증권담보대출 리드는 코스피·코스닥 전 종목(~2,500개)마다 majorstock.json을 호출해야 해서
스레드풀로 병렬 조회해도 수 분이 걸린다. 정책·뉴스 브리핑 등 다른 스냅샷과 동일하게,
실제 수집(_collect)은 /internal/warmup 배치(하루 1회, GitHub Actions cron)에서만
force=True 로 수행하고, 일반 웹 요청(get_leads(force=False))은 절대 DART를 직접
호출하지 않고 이미 저장된 스냅샷만 읽는다(오늘자가 없으면 가장 최근 스냅샷을
"stale"로, 그마저 없으면 "pending" 상태를 반환). 라이브 요청에서 즉석으로 재수집을
트리거하던 이전 방식은, 짧은 시간에 캐시가 여러 번 무효화될 때마다 배치 밖에서도
수천 건씩 DART를 호출하게 돼 opendart.fss.or.kr 쪽 남용 방지 차단을 실제로 유발한
적이 있어(2026-09-20) 제거했다.

호출 속도 제한: 종목 수가 많다 보니 스레드 동시성만 믿고 짧은 시간에 수천 건을 몰아
보내면 opendart.fss.or.kr 쪽에서 해당 IP의 연결 자체를 끊어버리는(비공식 남용 방지)
현상이 실제로 발생했다. 그래서 배치 수집 중에도 전체 요청을 초당 몇 건으로 강제
제한하는 스로틀을 둔다.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from capital._datago import to_float
from main.config import get_settings
from main.snapshot_store import get_snapshot, latest_snapshot, save_snapshot

from .corp_map import corp_code
from .equity import listed_snapshot

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

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
    """DART 호출 성공/실패 건수를 스레드 안전하게 센다.

    실패율이 너무 높으면(=DART 쪽에서 이 IP를 일시 차단한 상태) _collect() 가 텅 빈
    결과를 '정상 수집 결과'로 착각해 저장하지 않도록 예외를 던져 막는다. 실제로
    호출량이 많다 보니(코스피·코스닥 전체 조회) DART가 연결 자체를 끊어버리는 현상이
    있었고, 그때 빈 리스트를 그대로 저장하면 기존 정상 데이터가 빈 값으로 덮어써진다.
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

    def check(self, label: str) -> None:
        total = self.ok + self.fail
        # 시도한 호출이 하나라도 있는데 전부 실패 → 표본이 적어도(예: esop 스윕은 유형당
        # 딱 1번씩만 시도) 명백한 장애 신호. 호출량이 많은 스캔(예: 종목별 majorstock)은
        # 일부 종목만 실패할 수 있어 표본이 충분할 때(10건 이상)만 70% 기준을 본다.
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


def _fmt_date(yyyymmdd: str | None) -> str:
    s = str(yyyymmdd or "")
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else s


_KOSPI_TOP_N = 200
_KOSDAQ_TOP_N = 100


def _scan_universe() -> list[dict]:
    """증권담보대출(상속·증여) 리드 스캔 대상 — 시가총액 상위 코스피 200·코스닥
    100종목만(모듈 docstring 참고). 시가총액이 없는(데이터 누락) 종목은 정렬·상위
    N 선정에서 제외한다."""
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


def _esop_sweep(key: str, bgn_de: str, health: _CallHealth) -> list[dict]:
    """corp_code 없이 시장 전체 주요사항보고(B)·발행공시(C)를 페이지 단위로 훑는다.

    corp_cls 를 지정하지 않는다 — IPO(공모) 후보 회사는 아직 코스피·코스닥 어느
    시장에도 속하지 않아 corp_cls=Y 등으로 좁히면 애초에 조회 대상에서 빠진다.
    """
    end_de = date.today().strftime("%Y%m%d")
    rows: list[dict] = []
    for pblntf_ty in ("B", "C"):
        page = 1
        while page <= 50:  # 안전장치 — 정상 상황에서 60일치가 이 이상 나오진 않는다
            _throttle()
            try:
                resp = _session.get(_LIST_URL, params={
                    "crtfc_key": key,
                    "pblntf_ty": pblntf_ty,
                    "bgn_de": bgn_de,
                    "end_de": end_de,
                    "page_no": page,
                    "page_count": 100,
                }, timeout=20)
                data = resp.json()
            except (requests.RequestException, ValueError) as exc:
                logger.info("공시 전체 스캔 실패(pblntf_ty=%s, page=%s): %s", pblntf_ty, page, exc)
                health.record(False)
                break
            health.record(True)
            if data.get("status") != "000":
                break
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
            "date": _fmt_date(rcept_dt),
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


def _collect() -> dict:
    key = get_settings().dart_api_key
    stocks = _scan_universe()
    now = datetime.now(KST)
    if not key or not stocks:
        return {"collateral": [], "esop": [], "esop_monthly": [], "collateral_monthly": [],
                "universe": len(stocks), "generated_at": now.isoformat()}

    # corp_code 매핑(코스피·코스닥 종목코드 → DART corp_code) 자체가 안 내려오면 모든
    # 종목이 "매핑 없음"으로 스킵돼 API 콜 자체가 안 나가고, 그러면 실패율 감지도 못 걸려
    # 빈 결과가 '정상 수집'으로 저장될 수 있다. 그래서 미리 하나만 찍어 확인한다.
    if not corp_code("005930"):
        raise RuntimeError("DART corp_code 매핑을 불러오지 못했습니다(삼성전자 조회 실패) — 이번 수집은 건너뜁니다.")

    cutoff = (date.today() - timedelta(days=_LOOKBACK_DAYS)).strftime("%Y%m%d")

    inherit_health = _CallHealth()
    collateral: list[dict] = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
        futures = [ex.submit(_scan_inherit, s, key, cutoff, inherit_health) for s in stocks]
        for i, f in enumerate(as_completed(futures)):
            collateral.extend(f.result())
            # DART가 이 IP를 막은 상태로 보이면(초반 실패율이 이미 높음) 남은 종목을 계속
            # 순서대로 호출하며 수 분을 낭비하지 않도록 아직 시작 안 한 요청은 취소한다.
            if i >= 20 and inherit_health.fail / max(1, inherit_health.ok + inherit_health.fail) > 0.7:
                for pending in futures:
                    pending.cancel()
                break
    inherit_health.check("증권담보대출(상속·증여) 스캔")

    esop_health = _CallHealth()
    listed_ccs = _listed_corp_codes()
    # 유상증자(이미 상장된 회사 대상)는 증권담보대출 리드와 같은 시가총액 상위
    # 코스피 200·코스닥 100(=stocks, _scan_universe 결과)으로 좁힌다. IPO(상장 전
    # 공모)는 애초에 이 목록에 없는 회사들이라 전 시장 그대로 둔다.
    top_ccs = {cc for s in stocks if (cc := corp_code(s.get("code") or ""))}
    esop: list[dict] = []
    seen_rcept: set[str] = set()
    for it in _esop_sweep(key, cutoff, esop_health):
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
            "date": _fmt_date(it.get("rcept_dt")),
            "title": title,
            "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + rcept_no,
            "note": (_rights_note if category == "rights" else _ipo_note)(name, title),
        })

    esop_health.check("우리사주(유상증자·IPO) 스캔")
    esop = _latest_per_company(esop)

    collateral.sort(key=lambda x: x["date"], reverse=True)
    esop.sort(key=lambda x: x["date"], reverse=True)
    return {
        "collateral": collateral[:30],
        "esop": esop[:60],
        "esop_monthly": _esop_monthly_summary(esop),
        "collateral_monthly": _collateral_monthly_summary(collateral),
        "universe": len(stocks),
        "generated_at": now.isoformat(),
    }


_SCHEMA_V = 7  # v7: 실패율 감지 보정(표본 적어도 전부 실패면 즉시 감지) + 라이브 요청은
                # 재수집을 트리거하지 않고 배치(warmup)만 수집하도록 변경


def get_leads(force: bool = False) -> dict:
    """force=True 는 /internal/warmup 배치 전용 — 이 값 없이는 절대 DART 를 호출하지 않고
    이미 저장된 스냅샷만 읽는다(정책·뉴스 등 다른 브리핑과 동일한 '배치 수집 + 스냅샷
    조회' 방식)."""
    today = datetime.now(KST).date().isoformat()
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
