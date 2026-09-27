"""심사·리스크 > 리스크 시그널 — DART 거래소공시 기반 담보가치 리스크 시그널 + 급락 종목.

데이터 (전부 실데이터, 추정·AI 해설 없음)
  - 공시 시그널 : DART list.json 을 corp_code 없이 거래소공시(pblntf_ty=I) 최근 7일 전체로
    훑어(≈ 8~10페이지), 공시 제목(report_nm)으로 분류한다. 코스피·코스닥만, 스팩은 제외.
      ALERT — 상장폐지(결정·사유발생·정리매매·기준 해당), 회생·파산·부도, 감사의견(거절·부적정·
              한정), 횡령·배임, 매매거래정지(액면병합·분할 등 기술적 정지는 제외)
      WARN  — 관리종목(지정·우려), 시가총액 미달 상장폐지 우려, 불성실공시법인, 투자유의·경고,
              풍문 조회공시
    회사별로 묶어 가장 심각한 등급과 최근 공시를 대표로 보여준다. 해설(note)은 분류별 고정
    문구다 — 목업의 "AI 해설"은 근거 데이터 없이 수치를 지어낼 위험이 있어 쓰지 않는다.
  - 급락 종목 : data.go.kr 전 종목 시세(credit.equity.listed_snapshot) 중 등락률 −8% 이하,
    시가총액 1,000억 원 이상. 시세는 공공데이터포털 특성상 1~2영업일 늦다(기준일 표시).

DART 호출은 수집 1회당 10건 안팎이라 여신 리드(300종목 개별 조회)와 달리 부담이 작다. 그래도
화면 요청마다 부르지 않도록 오늘자 스냅샷을 저장하고, 수집 후 _REFRESH_MINUTES 가 지났을 때만
다시 훑는다(실패하면 직전 스냅샷 유지, _RETRY_AFTER_FAIL 동안 재시도 안 함).
"""
from __future__ import annotations

import logging
import re
import time
from datetime import timedelta

import requests

from credit.equity import listed_snapshot, listed_snapshot_as_of
from main.config import get_settings
from main.daily_snapshot import table_lock
from main.snapshot_store import get_snapshot, latest_snapshot, save_snapshot
from main.utils import now_kst, stamp, today_iso, today_kst, ymd_to_iso

logger = logging.getLogger(__name__)

_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
_VIEW_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
_TABLE = "risk_signal_snapshots"

_LOOKBACK_DAYS = 7
_MAX_PAGES = 20            # 7일치 거래소공시는 보통 10페이지 이내 — 무한 루프 방지용 상한
_REFRESH_MINUTES = 60
_RETRY_AFTER_FAIL = 600    # 초
_CALL_INTERVAL = 0.3       # DART 남용 방지(여신 리드와 같은 취지)
_MAX_ITEMS = 60
_MARKETS = {"Y": "코스피", "K": "코스닥"}

_DROP_PCT = -8.0
_DROP_MIN_CAP = 1000e8     # 1,000억 원

# (등급, 분류, 제목 패턴) — 위에서부터 먼저 맞는 규칙 하나만 적용. 제목은 공백을 지우고 비교한다.
RULES: list[tuple[str, str, re.Pattern]] = [
    ("ALERT", "상장폐지", re.compile(r"상장폐지결정|상장폐지사유|정리매매|상장폐지기준해당|상장적격성")),
    ("ALERT", "회생·부도", re.compile(r"회생절차|파산|부도|워크아웃|채권금융기관.*관리")),
    ("ALERT", "감사의견", re.compile(r"감사의견|의견거절|부적정의견|한정의견")),
    ("ALERT", "횡령·배임", re.compile(r"횡령|배임")),
    ("WARN", "관리종목", re.compile(r"관리종목")),
    ("WARN", "상폐 우려", re.compile(r"상장폐지우려")),
    ("WARN", "불성실공시", re.compile(r"불성실공시")),
    ("WARN", "조회공시", re.compile(r"풍문|조회공시")),
    ("WARN", "투자유의", re.compile(r"투자유의|투자주의환기|투자경고|투자위험")),
    ("ALERT", "거래정지", re.compile(r"매매거래정지(?!해제)")),
]
# 거래정지 중 액면병합·분할·합병 등 기술적 정지, 정지 해제 공시는 리스크가 아니다.
_TECHNICAL_HALT = re.compile(r"액면병합|액면분할|주식의병합|주식병합|주식분할|전자등록|변경상장|합병|분할|해제")
_LEVEL_RANK = {"ALERT": 0, "WARN": 1}

NOTES = {   # 분류별 고정 해설 — 공시 제목 이상의 사실을 덧붙이지 않는다
    "상장폐지": "상장폐지 절차 관련 공시 — 해당 종목 담보 취급·평가 시 거래 가능 여부 확인 필요",
    "회생·부도": "회생·부도 관련 공시 — 발행사 신용위험 급변, 담보가치 재평가 필요",
    "감사의견": "감사의견 관련 공시 — 비적정 의견은 상장폐지 사유가 될 수 있음",
    "횡령·배임": "횡령·배임 혐의 공시 — 거래정지·실질심사로 이어질 수 있음",
    "거래정지": "매매거래정지 공시 — 정지 기간 중 담보 처분 불가",
    "관리종목": "관리종목 지정(우려) 공시 — 요건 미해소 시 상장폐지 가능",
    "상폐 우려": "시가총액 미달 등 상장폐지 우려 안내 — 기준일까지 요건 충족 여부 주시",
    "불성실공시": "불성실공시법인 지정(예고) — 누적 벌점에 따라 관리종목 지정 가능",
    "조회공시": "풍문·보도 관련 조회공시 — 답변 공시 내용 확인 필요",
    "투자유의": "거래소 투자유의·경고 안내 — 가격 변동성 확대 구간",
}

_last_fail = [0.0]   # 마지막 수집 실패 시각(테이블 락 안에서만 읽고 씀)


def classify(report_nm: str) -> tuple[str, str] | None:
    """공시 제목 → (등급, 분류) 또는 None(리스크 아님)."""
    t = re.sub(r"\s+", "", report_nm or "")
    for level, category, pat in RULES:
        if pat.search(t):
            if category == "거래정지" and _TECHNICAL_HALT.search(t):
                return None
            return level, category
    return None


def _list_page(key: str, bgn: str, end: str, page: int) -> dict:
    """list.json 한 페이지. 통신 오류는 1회 재시도, DART 오류 상태면 예외."""
    params = {"crtfc_key": key, "pblntf_ty": "I", "bgn_de": bgn, "end_de": end,
              "page_no": page, "page_count": 100}
    for i in range(2):
        try:
            time.sleep(_CALL_INTERVAL)
            data = requests.get(_LIST_URL, params=params, timeout=20).json()
            break
        except (requests.RequestException, ValueError):
            if i == 1:
                raise
    status = data.get("status")
    if status == "013":        # 조회 결과 없음
        return {"list": [], "total_page": 0}
    if status != "000":
        raise RuntimeError(f"DART 거래소공시 조회 오류({status}): {data.get('message')}")
    return data


def _sweep(key: str) -> list[dict]:
    """최근 _LOOKBACK_DAYS 일 거래소공시 전체 중 리스크 공시만(최신순)."""
    end = today_kst()
    bgn, end_s = (end - timedelta(days=_LOOKBACK_DAYS)).strftime("%Y%m%d"), end.strftime("%Y%m%d")
    out: list[dict] = []
    page = 1
    while page <= _MAX_PAGES:
        data = _list_page(key, bgn, end_s, page)
        for x in data.get("list") or []:
            if x.get("corp_cls") not in _MARKETS or "스팩" in (x.get("corp_name") or ""):
                continue
            hit = classify(x.get("report_nm", ""))
            if not hit:
                continue
            out.append({
                "level": hit[0], "category": hit[1],
                "corp_code": x.get("corp_code"), "stock_code": x.get("stock_code") or None,
                "name": x.get("corp_name"), "market": _MARKETS[x["corp_cls"]],
                "title": re.sub(r"\s{2,}", " ", (x.get("report_nm") or "").strip()),
                "date": ymd_to_iso(x.get("rcept_dt")), "rcept_no": x.get("rcept_no"),
                "url": _VIEW_URL + str(x.get("rcept_no")),
            })
        if page >= int(data.get("total_page") or 0):
            break
        page += 1
    out.sort(key=lambda f: (f["date"], f["rcept_no"] or ""), reverse=True)
    return out


def _group(filings: list[dict]) -> list[dict]:
    """회사별로 묶기 — 가장 심각한 등급의 최신 공시가 대표, 나머지는 filings 로(최대 5건)."""
    by_corp: dict[str, list[dict]] = {}
    for f in filings:   # filings 가 최신순이라 회사별 목록도 최신순
        by_corp.setdefault(f["corp_code"], []).append(f)
    items = []
    for fs in by_corp.values():
        head = min(fs, key=lambda f: _LEVEL_RANK[f["level"]])   # 동률이면 앞(=최신) 것
        others = [f for f in fs if f is not head]
        items.append({
            **{k: head[k] for k in ("level", "category", "name", "market", "stock_code", "title", "date", "url")},
            "note": NOTES[head["category"]],
            "count": len(fs),
            "others": [{k: f[k] for k in ("level", "category", "title", "date", "url")} for f in others[:5]],
        })
    items.sort(key=lambda it: it["date"], reverse=True)   # 등급순, 같은 등급 안에서는 최신순
    items.sort(key=lambda it: _LEVEL_RANK[it["level"]])
    return items


def _drops() -> dict:
    """급락 종목 — 전 종목 시세 스냅샷(ttl 캐시) 재사용, DART 와 무관."""
    rows = [s for s in listed_snapshot()
            if s.get("market") in ("KOSPI", "KOSDAQ") and s.get("change_pct") is not None
            and s["change_pct"] <= _DROP_PCT and (s.get("market_cap") or 0) >= _DROP_MIN_CAP]
    rows.sort(key=lambda s: s["change_pct"])
    return {"as_of": listed_snapshot_as_of(), "count": len(rows),
            "items": [{"code": s["code"], "name": s["name"],
                       "market": "코스피" if s["market"] == "KOSPI" else "코스닥",
                       "close": s["close"], "change_pct": s["change_pct"],
                       "market_cap_eok": round(s["market_cap"] / 1e8)} for s in rows[:20]]}


def _collect(key: str) -> dict:
    filings = _sweep(key)
    items = _group(filings)
    return {
        "generated_at": stamp(), "collected_ts": time.time(),
        "range": {"from": (today_kst() - timedelta(days=_LOOKBACK_DAYS)).isoformat(), "to": today_iso()},
        "alert_count": sum(1 for it in items if it["level"] == "ALERT"),
        "warn_count": sum(1 for it in items if it["level"] == "WARN"),
        "delist_count": sum(1 for it in items if it["category"] in ("상장폐지", "관리종목", "상폐 우려")),
        "filing_count": len(filings),
        "items": items[:_MAX_ITEMS],
    }


def _fresh(snap: dict | None) -> bool:
    ts = (snap or {}).get("collected_ts")
    return bool(ts) and time.time() - ts < _REFRESH_MINUTES * 60


def get_signals(force: bool = False) -> dict:
    """공시 시그널(스냅샷) + 급락 종목(실시간 계산). force=True 는 배치용(신선도 무시하고 재수집)."""
    key = get_settings().dart_api_key
    today = today_iso()
    with table_lock(_TABLE):
        snap = get_snapshot(_TABLE, today)
        cooling = time.time() - _last_fail[0] < _RETRY_AFTER_FAIL
        if key and (force or (not _fresh(snap) and not cooling)):
            try:
                snap = _collect(key)
                save_snapshot(_TABLE, today, snap)
            except Exception as exc:  # noqa: BLE001 - DART 장애 → 직전 스냅샷
                _last_fail[0] = time.time()
                logger.warning("심사·리스크 공시 시그널 수집 실패: %s", exc)
                if force:
                    raise
        if snap is None:
            stale = latest_snapshot(_TABLE)
            snap = {**stale, "stale": True} if stale else None

    out = {k: v for k, v in (snap or {}).items() if k != "collected_ts"}
    if not snap:
        out = {"items": [], "alert_count": None, "warn_count": None, "delist_count": None,
               "pending": True, "note": None if key else "DART_API_KEY 등록 후 제공됩니다."}
    try:
        out["drops"] = _drops()
    except Exception as exc:  # noqa: BLE001
        logger.warning("급락 종목 계산 실패: %s", exc)
        out["drops"] = {"as_of": None, "count": None, "items": [], "error": True}
    out["checked_at"] = now_kst().strftime("%H:%M")
    return out


def latest_signal_items() -> list[dict]:
    """저장된 최신 시그널 목록만 읽는다(수집 없음) — 워치 유니버스 상태 판정용."""
    snap = get_snapshot(_TABLE, today_iso()) or latest_snapshot(_TABLE) or {}
    return snap.get("items") or []
