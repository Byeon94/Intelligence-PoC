"""심사·리스크 > 워치·섹터 — 워치 유니버스(시총 상위 30) · 섹터 리스크 히트.

데이터 (전부 실데이터)
  - 워치 유니버스 : data.go.kr 전 종목 시세에서 코스피+코스닥 시가총액 상위 30개 보통주
    (우선주 제외 — 종목코드 끝자리가 0이 아닌 코드). 종목별 일별 시세(약 5개월)로
      등락률(최근일) · 20일 수익률 · 거래량배율(최근일 ÷ 직전 20일 평균) · 60일 변동성(일간
      로그수익률 표준편차 × √252, 연율 %)을 계산하고, 리스크 시그널(risk.signals)의 DART 공시
      등급을 붙인다. 상태 기준은 STATUS_RULE 문구 그대로(화면에도 표시).
    종목당 1회 호출(30회)이라 하루 1회 스냅샷으로 저장하고, 시세 기준일이 바뀌면 다시 만든다.
  - 섹터 리스크 히트 : data.go.kr 「금융위원회_지수시세정보」의 KRX 코스피 업종지수(건설·증권·
    화학 등 23개) 1일·20일 등락률. 업종 분류를 AI 로 추정하지 않고 거래소 공식 지수를 쓴다.
"""
from __future__ import annotations

import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from capital._datago import INDEX_OP, INDEX_SERVICE, get_json, pick, to_float
from credit.equity import _daily_rows, listed_snapshot, listed_snapshot_as_of
from main.cache import ttl_cache
from main.daily_snapshot import table_lock
from main.snapshot_store import get_snapshot, latest_snapshot, save_snapshot
from main.utils import stamp, today_iso, today_kst, ymd_to_iso

logger = logging.getLogger(__name__)

_TABLE = "risk_watch_snapshots"
_UNIVERSE = 30
_RETRY_AFTER_FAIL = 600      # 초 — 생성 실패 후 이 시간 동안은 화면 요청이 재시도하지 않음
_last_fail = [0.0]           # 테이블 락 안에서만 읽고 씀
_HISTORY_DAYS = 150          # 달력일 — 60거래일 변동성 + 20일 평균에 충분
STATUS_RULE = ("ALERT: 등락률 −8% 이하 또는 DART 리스크 공시(ALERT) · "
               "WARN: 등락률 −4% 이하, 20일 수익률 −15% 이하, 거래량배율 3배 이상 또는 DART 공시(WARN)")


# ── 워치 유니버스 ─────────────────────────────────────────────────────────
def _universe() -> list[dict]:
    rows = [s for s in listed_snapshot()
            if s.get("market") in ("KOSPI", "KOSDAQ") and s.get("market_cap") and s["code"].endswith("0")]
    rows.sort(key=lambda s: s["market_cap"], reverse=True)
    return rows[:_UNIVERSE]


def _metrics(code: str) -> dict:
    rows = _daily_rows(code, _HISTORY_DAYS)
    closes = [to_float(pick(r, "clpr")) for r in rows]
    vols = [to_float(pick(r, "trqu")) for r in rows]
    closes = [c for c in closes if c]
    out = {"date": ymd_to_iso(str(pick(rows[-1], "basDt"))),
           "change_pct": to_float(pick(rows[-1], "fltRt")),
           "ret20": None, "vol_ratio": None, "volatility60": None}
    if len(closes) > 20:
        out["ret20"] = round((closes[-1] / closes[-21] - 1) * 100, 2)
    prev = [v for v in vols[-21:-1] if v]
    if vols and vols[-1] and len(prev) >= 10:
        out["vol_ratio"] = round(vols[-1] / (sum(prev) / len(prev)), 1)
    rets = [math.log(b / a) for a, b in zip(closes[-61:-1], closes[-60:]) if a and b]
    if len(rets) >= 40:
        mean = sum(rets) / len(rets)
        sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))
        out["volatility60"] = round(sd * math.sqrt(252) * 100, 1)
    return out


def _status(m: dict, signal: str | None) -> str:
    chg, r20, vr = m.get("change_pct"), m.get("ret20"), m.get("vol_ratio")
    if (chg is not None and chg <= -8) or signal == "ALERT":
        return "ALERT"
    if ((chg is not None and chg <= -4) or (r20 is not None and r20 <= -15)
            or (vr is not None and vr >= 3) or signal == "WARN"):
        return "WARN"
    return "정상"


def _build_watch(as_of: str | None) -> dict:
    stocks = _universe()
    if not stocks:
        raise RuntimeError("상장종목 시세 스냅샷을 불러오지 못했습니다.")
    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(lambda s: _safe_metrics(s["code"]), stocks))
    failed = sum(1 for r in results if r is None)
    if failed > len(stocks) * 0.3:
        raise RuntimeError(f"워치 유니버스 시세 조회 실패가 많습니다({failed}/{len(stocks)}).")
    items = []
    for rank, (s, m) in enumerate(zip(stocks, results), 1):
        if m is None:
            continue
        items.append({"rank": rank, "code": s["code"], "name": s["name"],
                      "market": "코스피" if s["market"] == "KOSPI" else "코스닥",
                      "close": s["close"], "market_cap_jo": round(s["market_cap"] / 1e12, 1), **m})
    return {"as_of": as_of, "generated_at": stamp(), "items": items}


def _safe_metrics(code: str) -> dict | None:
    try:
        return _metrics(code)
    except Exception as exc:  # noqa: BLE001 - 한 종목 실패는 건너뜀(전체 실패율은 호출부에서 판단)
        logger.info("워치 유니버스 %s 시세 실패: %s", code, exc)
        return None


def _signal_levels() -> dict[str, str]:
    """종목코드 → DART 리스크 공시 등급(스냅샷만 읽음 — 여기서 재수집하지 않는다)."""
    from .signals import latest_signal_items
    return {it["stock_code"]: it["level"] for it in latest_signal_items() if it.get("stock_code")}


def get_watch() -> dict:
    as_of = listed_snapshot_as_of()
    today = today_iso()
    with table_lock(_TABLE):
        snap = get_snapshot(_TABLE, today)
        needs = snap is None or (as_of and snap.get("as_of") != as_of)
        cooling = time.time() - _last_fail[0] < _RETRY_AFTER_FAIL
        if needs and snap is not None and cooling:
            snap = {**snap, "stale": True}     # 직전 실패 직후 — 30종목 재조회로 요청을 붙잡지 않음
        elif needs:
            try:
                snap = _build_watch(as_of)
                save_snapshot(_TABLE, today, snap)
            except Exception as exc:  # noqa: BLE001
                _last_fail[0] = time.time()
                logger.warning("워치 유니버스 생성 실패: %s", exc)
                snap = snap or latest_snapshot(_TABLE)
                if snap is None:
                    raise
                snap = {**snap, "stale": True}
    levels = _signal_levels()
    items = []
    for it in snap["items"]:
        sig = levels.get(it["code"])
        items.append({**it, "signal": sig, "status": _status(it, sig)})
    return {**snap, "items": items, "rule": STATUS_RULE,
            "alert": sum(1 for i in items if i["status"] == "ALERT"),
            "warn": sum(1 for i in items if i["status"] == "WARN")}


# ── 섹터 리스크 히트(KRX 코스피 업종지수) ─────────────────────────────────
KOSPI_SECTORS = [
    "건설", "증권", "금융", "보험", "부동산", "화학", "금속", "비금속", "기계·장비", "전기전자",
    "IT 서비스", "통신", "운송장비·부품", "운송·창고", "유통", "음식료·담배", "섬유·의류",
    "종이·목재", "제약", "의료·정밀기기", "전기·가스", "오락·문화", "일반서비스",
]
SECTOR_RULE = "고위험: 20일 −10% 이하 또는 당일 −4% 이하 · 주의: 20일 −5% 이하 또는 당일 −2% 이하"


def _sector_level(d1: float | None, d20: float | None) -> str:
    if (d20 is not None and d20 <= -10) or (d1 is not None and d1 <= -4):
        return "고위험"
    if (d20 is not None and d20 <= -5) or (d1 is not None and d1 <= -2):
        return "주의"
    return "안정"


@ttl_cache(60 * 60)
def get_sector_heat() -> dict:
    today = today_kst()
    rows = get_json(INDEX_SERVICE, INDEX_OP, {
        "beginBasDt": (today - timedelta(days=40)).strftime("%Y%m%d"),   # 20영업일 + 휴장 여유
        "endBasDt": today.strftime("%Y%m%d"),
    })
    series: dict[str, list[tuple[str, float, float | None]]] = {}
    for r in rows:
        name = pick(r, "idxNm")
        if pick(r, "idxCsf") != "KOSPI시리즈" or name not in KOSPI_SECTORS:
            continue
        close = to_float(pick(r, "clpr"))
        if close:
            series.setdefault(name, []).append((str(pick(r, "basDt")), close, to_float(pick(r, "fltRt"))))
    if not series:
        raise RuntimeError("KRX 업종지수 응답 없음")
    if len(rows) >= 10000:   # get_json 한 페이지 상한 — 넘으면 오래된 날짜가 잘렸을 수 있음
        logger.warning("KRX 지수시세 응답이 한 페이지 상한(10,000행)에 닿음 — 20일 등락률이 비을 수 있음")
    sectors, as_of = [], None
    for name in KOSPI_SECTORS:
        s = sorted(series.get(name) or [])
        if not s:
            continue
        d1 = s[-1][2]
        d20 = round((s[-1][1] / s[-21][1] - 1) * 100, 2) if len(s) > 20 else None
        as_of = max(as_of or "", s[-1][0])
        sectors.append({"name": name, "d1": d1, "d20": d20, "level": _sector_level(d1, d20)})
    rank = {"고위험": 0, "주의": 1, "안정": 2}
    sectors.sort(key=lambda x: (rank[x["level"]], x["d20"] if x["d20"] is not None else 0))
    return {"as_of": ymd_to_iso(as_of), "sectors": sectors, "rule": SECTOR_RULE}


def get_watch_sector() -> dict:
    """워치·섹터 탭 한 번에 — 한쪽이 실패해도 나머지는 보여준다."""
    out: dict = {}
    for key, fn in (("watch", get_watch), ("sectors", get_sector_heat)):
        try:
            out[key] = fn()
        except Exception:  # noqa: BLE001
            logger.exception("심사·리스크 %s 조회 실패", key)
            out[key] = {"error": "데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."}
    return out
