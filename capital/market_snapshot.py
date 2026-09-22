"""오늘의 브리핑 > 오늘의 시장 한눈에.

capital.turnover 와 같은 data.go.kr 「금융위원회_지수시세정보」를 쓰되, turnover.py는
trPrc(거래대금)만 뽑아 월별로 합산하는 반면 여기서는 최근 2거래일의 clpr(지수 종가)를
비교해 코스피·코스닥 "지수 레벨 + 전일 대비 등락률"을 보여준다(라이브 HTTP 조회,
Gemini 호출 없음 — ttl_cache로 반복 호출만 줄인다).

외국인/기관/개인 순매수는 이 API로 얻을 수 없어(별도 서비스 필요, 미연동) 포함하지
않는다 — 실제로 없는 데이터를 지어내지 않는다는 원칙.
"""
from __future__ import annotations

from datetime import date, timedelta

from ._cache import ttl_cache
from ._datago import DataGoError, get_json, pick, to_float

_SERVICE = "GetMarketIndexInfoService"
_OP = "getStockMarketIndex"
_JO = 1_000_000_000_000  # 원 → 조원


def _fetch_recent(idx_nm: str, days: int = 10) -> list[dict]:
    begin = (date.today() - timedelta(days=days)).strftime("%Y%m%d")
    end = date.today().strftime("%Y%m%d")
    rows = get_json(_SERVICE, _OP, {
        "idxNm": idx_nm, "beginBasDt": begin, "endBasDt": end, "numOfRows": 100,
    })
    out = []
    for r in rows:
        if pick(r, "idxNm") not in (idx_nm, None):  # '코스피 200' 등 하위지수 제외
            continue
        d = pick(r, "basDt", "BAS_DT")
        clpr = to_float(pick(r, "clpr", "CLPR"))
        trprc = to_float(pick(r, "trPrc", "TR_PRC"))
        if d and clpr is not None:
            out.append({"date": str(d), "close": clpr, "turnover": trprc})
    out.sort(key=lambda x: x["date"])
    return out


def _index_snapshot(idx_nm: str) -> dict:
    rows = _fetch_recent(idx_nm)
    if len(rows) < 2:
        raise DataGoError(f"{idx_nm} 지수 데이터 부족")
    cur, prev = rows[-1], rows[-2]
    chg = cur["close"] - prev["close"]
    chg_pct = round(chg / prev["close"] * 100, 2) if prev["close"] else None
    return {
        "as_of": cur["date"],
        "close": cur["close"],
        "change": round(chg, 2),
        "change_pct": chg_pct,
        "turnover": round(cur["turnover"] / _JO, 1) if cur.get("turnover") else None,
    }


@ttl_cache(1800)
def get_market_snapshot() -> dict:
    try:
        kospi = _index_snapshot("코스피")
        kosdaq = _index_snapshot("코스닥")
        total_turnover = None
        if kospi.get("turnover") is not None and kosdaq.get("turnover") is not None:
            total_turnover = round(kospi["turnover"] + kosdaq["turnover"], 1)
        return {
            "source": "live",
            "as_of": kospi["as_of"],
            "kospi": kospi,
            "kosdaq": kosdaq,
            "total_turnover": total_turnover,
        }
    except (DataGoError, KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        return {"source": "unavailable", "error": str(exc)}
