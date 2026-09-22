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

import requests

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


# ── 해외증시·환율(Yahoo Finance 비공식 chart API) ──
# 네이버 증권이 Next.js SPA로 개편되면서 페이지를 그대로 긁어서는 값을 못 가져와(값이
# 클라이언트 쪽 내부 API 호출로 채워짐), 같은 값을 주는 공개 엔드포인트로 대체했다.
# data.go.kr에는 미국지수·환율 서비스가 없어 이 방법을 쓴다 — 비공식 API라 실패하면
# (레이트리밋·구조변경 등) 그냥 "해외 데이터를 불러오지 못했습니다"로 표시하고,
# 국내 지수(get_market_snapshot)는 별도 함수라 영향받지 않는다.
_YF_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/"
_US_INDICES = [("다우존스", "%5EDJI"), ("나스닥", "%5EIXIC"), ("S&P500", "%5EGSPC")]
# (표시명, 심볼, 심볼값에 곱할 배수) — 엔화는 관행상 100엔 기준으로 표기.
_FX_PAIRS = [("USD/KRW", "KRW=X", 1), ("JPY100/KRW", "JPYKRW=X", 100), ("EUR/KRW", "EURKRW=X", 1)]


def _yf_quote(symbol: str) -> dict:
    resp = requests.get(_YF_CHART + symbol, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
    resp.raise_for_status()
    meta = resp.json()["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice")
    chg_pct = meta.get("regularMarketChangePercent")
    if price is None:
        raise ValueError(f"{symbol} 시세 없음")
    return {"price": price, "change_pct": chg_pct}


@ttl_cache(1800)
def get_global_market_snapshot() -> dict:
    try:
        us = []
        for name, sym in _US_INDICES:
            q = _yf_quote(sym)
            us.append({
                "name": name, "close": round(q["price"], 2),
                "change_pct": round(q["change_pct"], 2) if q["change_pct"] is not None else None,
            })
        fx = []
        for name, sym, mult in _FX_PAIRS:
            q = _yf_quote(sym)
            fx.append({
                "name": name, "value": round(q["price"] * mult, 2),
                "change_pct": round(q["change_pct"], 2) if q["change_pct"] is not None else None,
            })
        return {"source": "live", "us_indices": us, "fx": fx}
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
        return {"source": "unavailable", "error": str(exc)}
