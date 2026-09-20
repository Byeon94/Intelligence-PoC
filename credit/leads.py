"""여신·심사 탭 메인 화면 — 담보대출 수요 레이더 / 우리사주 금융 수요 (실데이터).

대상: 코스피+코스닥 전체 상장종목(equity._listed_snapshot 기준). 시가총액 상위
30종목만, 코스피만으로 차례로 좁혀봤더니 상속·증여 이벤트 자체가 원래 드물어 리드가
거의 안 잡혀, 코스피·코스닥 전체로 확대했다.

데이터 소스 (전부 DART OpenAPI 실데이터, 추정치 없음):
  - 담보대출 수요 리드 : majorstock.json(대량보유 상황보고)의 실제 `report_resn`(보고사유)
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

담보대출 리드는 코스피 전 종목(~900개)마다 majorstock.json을 호출해야 해서 스레드풀로
병렬 조회해도 수 분이 걸릴 수 있다. 그래서 당일 스냅샷이 없으면(즉시 응답이 필요한 웹
요청 도중) 가장 최근 스냅샷을 먼저 반환하고, 실제 재수집은 백그라운드 스레드에서 진행한다
(요청이 몇 분씩 붙잡혀 타임아웃 나는 것을 방지). force=True(수동 갱신)일 때만 동기 실행.
"""
from __future__ import annotations

import logging
import re
import threading
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

_MAX_WORKERS = 20
_LOOKBACK_DAYS = 60
_session = requests.Session()

_INHERIT_RE = re.compile(r"상속|증여")
_RIGHTS_KEYWORD_RE = re.compile(r"유상증자")
_EQUITY_REG_RE = re.compile(r"증권신고서\(지분증권\)")


def _fmt_date(yyyymmdd: str | None) -> str:
    s = str(yyyymmdd or "")
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else s


def _scan_universe() -> list[dict]:
    return [s for s in listed_snapshot() if s.get("market") in ("KOSPI", "KOSDAQ")]


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


def _majorstock(cc: str, key: str) -> list[dict]:
    try:
        resp = _session.get(_MAJORSTOCK_URL, params={"crtfc_key": key, "corp_code": cc}, timeout=15)
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.info("majorstock 조회 실패(%s): %s", cc, exc)
        return []
    if data.get("status") != "000":
        return []
    return data.get("list") or []


def _esop_sweep(key: str, bgn_de: str) -> list[dict]:
    """corp_code 없이 시장 전체 주요사항보고(B)·발행공시(C)를 페이지 단위로 훑는다.

    corp_cls 를 지정하지 않는다 — IPO(공모) 후보 회사는 아직 코스피·코스닥 어느
    시장에도 속하지 않아 corp_cls=Y 등으로 좁히면 애초에 조회 대상에서 빠진다.
    """
    end_de = date.today().strftime("%Y%m%d")
    rows: list[dict] = []
    for pblntf_ty in ("B", "C"):
        page = 1
        while page <= 50:  # 안전장치 — 정상 상황에서 60일치가 이 이상 나오진 않는다
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
                break
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
    bits.append("상속·증여세 재원 마련을 위한 주식담보대출 수요로 이어질 수 있는 이벤트입니다.")
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


def _scan_inherit(s: dict, key: str, cutoff: str) -> list[dict]:
    code, name, price = s["code"], s["name"], s.get("close")
    cc = corp_code(code)
    if not cc:
        return []

    seen: set[str] = set()
    out: list[dict] = []
    for it in _majorstock(cc, key):
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


def _collect() -> dict:
    key = get_settings().dart_api_key
    stocks = _scan_universe()
    now = datetime.now(KST)
    if not key or not stocks:
        return {"collateral": [], "esop": [], "esop_monthly": [], "universe": len(stocks),
                "generated_at": now.isoformat()}

    cutoff = (date.today() - timedelta(days=_LOOKBACK_DAYS)).strftime("%Y%m%d")

    collateral: list[dict] = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
        futures = [ex.submit(_scan_inherit, s, key, cutoff) for s in stocks]
        for f in as_completed(futures):
            collateral.extend(f.result())

    listed_ccs = _listed_corp_codes()
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

    esop = _latest_per_company(esop)

    collateral.sort(key=lambda x: x["date"], reverse=True)
    esop.sort(key=lambda x: x["date"], reverse=True)
    return {
        "collateral": collateral[:30],
        "esop": esop[:60],
        "esop_monthly": _esop_monthly_summary(esop),
        "universe": len(stocks),
        "generated_at": now.isoformat(),
    }


_SCHEMA_V = 5  # v5: 상속·증여 스캔 대상을 코스피 → 코스피+코스닥으로 확대

_refresh_lock = threading.Lock()


def _background_refresh() -> None:
    if not _refresh_lock.acquire(blocking=False):
        return
    try:
        payload = _collect()
        payload["v"] = _SCHEMA_V
        save_snapshot(_TABLE, datetime.now(KST).date().isoformat(), payload)
    except Exception:  # noqa: BLE001
        logger.exception("여신·심사 리드 백그라운드 갱신 실패")
    finally:
        _refresh_lock.release()


def get_leads(force: bool = False) -> dict:
    today = datetime.now(KST).date().isoformat()
    if not force:
        snap = get_snapshot(_TABLE, today)
        if snap is not None and snap.get("v") == _SCHEMA_V:
            return snap

        # 코스피 전 종목 스캔은 수 분 걸릴 수 있어, 웹 요청은 붙잡지 않는다.
        # 예전 스냅샷이 있으면 그걸 즉시 돌려주고 실제 재수집은 백그라운드로 미룬다.
        stale = latest_snapshot(_TABLE)
        if stale is not None:
            if not _refresh_lock.locked():
                threading.Thread(target=_background_refresh, daemon=True).start()
            return {**stale, "stale": True}

        # 스냅샷이 아예 없는 최초 실행 — 백그라운드로 수집을 시작하고 "수집 중" 상태를 반환.
        if not _refresh_lock.locked():
            threading.Thread(target=_background_refresh, daemon=True).start()
        return {"collateral": [], "esop": [], "esop_monthly": [], "universe": 0, "generated_at": None,
                "pending": True, "v": _SCHEMA_V}

    payload = _collect()
    payload["v"] = _SCHEMA_V
    save_snapshot(_TABLE, today, payload)
    return payload
