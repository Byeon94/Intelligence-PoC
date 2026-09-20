"""여신·심사 탭 메인 화면 — 담보대출 수요 레이더 / 우리사주 금융 수요 (실데이터).

대상: 코스피 시가총액 상위 30종목(equity._listed_snapshot 기준).

데이터 소스 (전부 DART OpenAPI 실데이터, 추정치 없음):
  - 담보대출 수요 리드 : majorstock.json(대량보유 상황보고)의 실제 `report_resn`(보고사유)
    필드에 '상속'·'증여'가 포함된 건 → 상속·증여 리드, '담보'가 포함된 건 → 담보계약 리드.
    지분가치는 (보고서상 보유주식 증감수 × 코스피 상위 30 시세 스냅샷 종가)로 계산한 추정치.
  - 우리사주 금융 수요 리드 : list.json(공시검색)에서 report_nm에 '유상증자' 또는
    '증권신고서(지분증권)'가 포함된 최근 공시. 코스피 상위 30종목은 이미 상장돼 있어
    '신규상장(IPO)' 이벤트 자체가 없으므로, 우리사주 수요 신호는 유상증자 공시로만 잡는다.
    (배정 비율·수요예측 금액 등 세부 수치는 공시 원문에만 있어 여기서는 만들어내지 않는다.)

해설(note)은 공시에 실제로 찍힌 값(회사명·보고사유·날짜·지분율)만으로 구성한 고정 문구다.
LLM이 수치를 지어낼 위험을 피하려고 여기서는 Gemini를 호출하지 않는다.

하루 1회 수집해 스냅샷으로 캐시(main.snapshot_store).
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from capital._datago import to_float
from main.config import get_settings
from main.snapshot_store import get_snapshot, save_snapshot

from .corp_map import corp_code
from .equity import listed_snapshot

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

_MAJORSTOCK_URL = "https://opendart.fss.or.kr/api/majorstock.json"
_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
_TABLE = "credit_lead_snapshots"

_UNIVERSE = 30
_MAJORSTOCK_LOOKBACK_DAYS = 60
_FILING_LOOKBACK_DAYS = 60

_INHERIT_RE = re.compile(r"상속|증여")
_PLEDGE_RE = re.compile(r"담보")
_RIGHTS_RE = re.compile(r"유상증자|증권신고서\(지분증권\)")


def _fmt_date(yyyymmdd: str | None) -> str:
    s = str(yyyymmdd or "")
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else s


def _top30_kospi() -> list[dict]:
    snap = [s for s in listed_snapshot() if s.get("market") == "KOSPI" and s.get("market_cap")]
    snap.sort(key=lambda s: s["market_cap"], reverse=True)
    return snap[:_UNIVERSE]


def _majorstock(cc: str, key: str) -> list[dict]:
    try:
        resp = requests.get(_MAJORSTOCK_URL, params={"crtfc_key": key, "corp_code": cc}, timeout=15)
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.info("majorstock 조회 실패(%s): %s", cc, exc)
        return []
    if data.get("status") != "000":
        return []
    return data.get("list") or []


def _filings_scan(cc: str, key: str) -> list[dict]:
    try:
        resp = requests.get(_LIST_URL, params={
            "crtfc_key": key,
            "corp_code": cc,
            "bgn_de": (date.today() - timedelta(days=_FILING_LOOKBACK_DAYS)).strftime("%Y%m%d"),
            "end_de": date.today().strftime("%Y%m%d"),
            "page_no": 1,
            "page_count": 30,
        }, timeout=15)
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.info("list.json 조회 실패(%s): %s", cc, exc)
        return []
    if data.get("status") != "000":
        return []
    return data.get("list") or []


def _inherit_note(name: str, resn: str, stake_pct: float | None, value_won: float | None) -> str:
    bits = [f"{name} 대주주(특수관계인 포함) 지분 변동 공시 — 보고사유 '{resn}'."]
    if stake_pct is not None:
        bits.append(f"이번 신고분 지분율 {stake_pct:g}%.")
    if value_won:
        bits.append(f"현재가 기준 추정 지분가치 약 {_eok_text(value_won)}.")
    bits.append("상속·증여세 재원 마련을 위한 주식담보대출 수요로 이어질 수 있는 이벤트입니다.")
    return " ".join(bits)


def _pledge_note(name: str, resn: str, stake_pct: float | None) -> str:
    bits = [f"{name} 대주주(특수관계인 포함) 지분 관련 공시 — 보고사유 '{resn}'."]
    if stake_pct is not None:
        bits.append(f"이번 신고분 지분율 {stake_pct:g}%.")
    bits.append("담보 설정·변경 이벤트로, 만기 도래 시 리파이낸싱 수요 접점이 될 수 있습니다.")
    return " ".join(bits)


def _esop_note(name: str, title: str) -> str:
    return (
        f"{name} '{title}' 공시. 자본시장법상 유상증자 시 우리사주조합은 배정 물량의 "
        "20% 한도 내에서 우선배정을 받을 수 있어, 조합원 대상 우리사주 취득자금대출 수요로 "
        "이어질 수 있는 이벤트입니다. 실제 배정 여부·비율은 공시 원문 확인이 필요합니다."
    )


def _eok_text(won: float) -> str:
    eok = won / 1e8
    if eok >= 10000:
        return f"{eok / 10000:.1f}조원"
    return f"{eok:,.0f}억원"


def _collect() -> dict:
    key = get_settings().dart_api_key
    stocks = _top30_kospi()
    now = datetime.now(KST)
    if not key or not stocks:
        return {"collateral": [], "esop": [], "universe": len(stocks), "generated_at": now.isoformat()}

    cutoff = (date.today() - timedelta(days=_MAJORSTOCK_LOOKBACK_DAYS)).strftime("%Y%m%d")
    collateral: list[dict] = []
    esop: list[dict] = []
    seen_rcept: set[str] = set()

    for s in stocks:
        code, name, price = s["code"], s["name"], s.get("close")
        cc = corp_code(code)
        if not cc:
            continue

        for it in _majorstock(cc, key):
            rcept_dt = (it.get("rcept_dt") or "").strip()
            if rcept_dt < cutoff:
                continue
            resn = (it.get("report_resn") or "").strip()
            is_inherit = bool(_INHERIT_RE.search(resn))
            is_pledge = bool(_PLEDGE_RE.search(resn))
            if not (is_inherit or is_pledge):
                continue
            rcept_no = (it.get("rcept_no") or "").strip()
            dedup = rcept_no + resn
            if not rcept_no or dedup in seen_rcept:
                continue
            seen_rcept.add(dedup)

            shares = to_float(it.get("stkqy_irds")) or to_float(it.get("stkqy"))
            stake_pct = to_float(it.get("stkrt"))
            value_won = abs(shares) * price if shares and price else None
            kind = "inherit" if is_inherit else "pledge"
            note = (
                _inherit_note(name, resn, stake_pct, value_won)
                if kind == "inherit"
                else _pledge_note(name, resn, stake_pct)
            )
            collateral.append({
                "kind": kind,
                "badge": "리드" if kind == "inherit" else "감지",
                "code": code,
                "name": name,
                "date": _fmt_date(rcept_dt),
                "reporter": (it.get("repror") or "").strip(),
                "reason": resn,
                "stake_pct": stake_pct,
                "value_won": value_won,
                "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + rcept_no,
                "note": note,
            })

        for it in _filings_scan(cc, key):
            title = (it.get("report_nm") or "").strip()
            if not _RIGHTS_RE.search(title):
                continue
            rcept_no = (it.get("rcept_no") or "").strip()
            if not rcept_no or rcept_no in seen_rcept:
                continue
            seen_rcept.add(rcept_no)
            esop.append({
                "code": code,
                "name": name,
                "date": _fmt_date(it.get("rcept_dt")),
                "title": title,
                "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + rcept_no,
                "note": _esop_note(name, title),
            })

    collateral.sort(key=lambda x: x["date"], reverse=True)
    esop.sort(key=lambda x: x["date"], reverse=True)
    return {
        "collateral": collateral[:30],
        "esop": esop[:30],
        "universe": len(stocks),
        "generated_at": now.isoformat(),
    }


_SCHEMA_V = 1


def get_leads(force: bool = False) -> dict:
    today = datetime.now(KST).date().isoformat()
    if not force:
        snap = get_snapshot(_TABLE, today)
        if snap is not None and snap.get("v") == _SCHEMA_V:
            return snap
    payload = _collect()
    payload["v"] = _SCHEMA_V
    save_snapshot(_TABLE, today, payload)
    return payload
