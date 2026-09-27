"""오늘의 브리핑 > 오늘의 시장 한눈에 — 국내 지수·해외 지수·환율·미국채 금리.

- 국내(코스피·코스닥): data.go.kr 「금융위원회_지수시세정보」(capital._datago.index_daily)의
  최근 2거래일 clpr(종가)를 비교해 "지수 레벨 + 전일 대비 등락률"과 당일 거래대금을 낸다.
- 해외·환율·금리: Yahoo Finance 비공식 chart API.
- 스파크라인용 1년치 일별 종가(get_*_history_1y)는 별도 함수·별도 캐시.

모두 라이브 HTTP 조회이고 Gemini 호출은 없다(ttl_cache로 반복 호출만 줄인다). 실패하면
{"source": "unavailable"}. 외국인/기관/개인 순매수는 이 API로 얻을 수 없어(별도 서비스 필요,
미연동) 포함하지 않는다 — 실제로 없는 데이터를 지어내지 않는다는 원칙.
"""
from __future__ import annotations

from datetime import datetime, timezone

import requests

from main.cache import ttl_cache
from ._datago import JO, DataGoError, index_daily


# 추석·설 연휴(최장 9~10일)에도 비교할 2거래일이 남도록 20일 구간을 본다.
def _fetch_recent(idx_nm: str, days: int = 20, rows: int = 100) -> list[dict]:
    """[{date, close, turnover}] 날짜 오름차순 — 종가가 없는 행은 뺀다."""
    return [r for r in index_daily(idx_nm, days=days, num_rows=rows) if r["close"] is not None]


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
        "turnover": round(cur["turnover"] / JO, 1) if cur.get("turnover") else None,
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


# 시장 한눈에 스파크라인용 — 코스피·코스닥 1년치 일별 종가. 장중에는 당일 확정치가
# 아직 안 올라와 최신 값이 자주 안 바뀌므로, 스냅샷(30분)보다 훨씬 길게 캐시한다.
@ttl_cache(3600 * 6)
def get_market_history_1y() -> dict:
    try:
        kospi = _fetch_recent("코스피", days=380, rows=400)
        kosdaq = _fetch_recent("코스닥", days=380, rows=400)
        return {
            "source": "live",
            "kospi": {"labels": [r["date"] for r in kospi], "values": [r["close"] for r in kospi]},
            "kosdaq": {"labels": [r["date"] for r in kosdaq], "values": [r["close"] for r in kosdaq]},
        }
    except (DataGoError, KeyError, TypeError, ValueError) as exc:
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
_FX_PAIRS = [("USD/KRW", "KRW=X", 1), ("JPY100/KRW", "JPYKRW=X", 100), ("EUR/KRW", "EURKRW=X", 1),
             ("CNY/KRW", "CNYKRW=X", 1)]
# CBOE ^TNX는 미국채 10년물 금리를 그대로 %(예: 4.25 = 4.25%)로 준다 — 10을 곱한 값이
# 아니라 실제 확인 결과 그대로 퍼센트였음(오배수 주의).
_US_BOND_SYMBOL = "%5ETNX"
# 금리 카드(키, 표시명, 심볼) — ^TYX 도 ^TNX 처럼 %를 그대로 준다. 미국채 3년물은 Yahoo 에 없어 뺐다.
_US_BONDS = [("bond_us10y", "미국채10년", _US_BOND_SYMBOL), ("bond_us30y", "미국채30년", "%5ETYX")]


def _yf_quote(symbol: str) -> dict:
    resp = requests.get(_YF_CHART + symbol, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
    resp.raise_for_status()
    meta = resp.json()["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice")
    chg_pct = meta.get("regularMarketChangePercent")
    if price is None:
        raise ValueError(f"{symbol} 시세 없음")
    # 기본 range(1d)의 chartPreviousClose = 전영업일 종가 → 전영업일 대비 변동폭
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    return {"price": price, "change_pct": chg_pct, "change": price - prev if prev else None}


def _rnd(v, n: int = 2):
    return round(v, n) if v is not None else None


@ttl_cache(1800)
def get_global_market_snapshot() -> dict:
    try:
        us = []
        for name, sym in _US_INDICES:
            q = _yf_quote(sym)
            us.append({
                "name": name, "close": round(q["price"], 2), "change": _rnd(q["change"]),
                "change_pct": round(q["change_pct"], 2) if q["change_pct"] is not None else None,
            })
        fx = []
        for name, sym, mult in _FX_PAIRS:
            q = _yf_quote(sym)
            fx.append({
                "name": name, "value": round(q["price"] * mult, 2),
                "change": _rnd(q["change"] * mult if q["change"] is not None else None),
                "change_pct": round(q["change_pct"], 2) if q["change_pct"] is not None else None,
            })
        # 금리는 전영업일 대비 변동을 %p(change)로 — 금리의 등락률(%)은 의미가 약하다.
        bonds = []
        for key, name, sym in _US_BONDS:
            try:
                qb = _yf_quote(sym)
            except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
                continue  # 지수·환율은 살아있는데 금리만 실패해도 나머지는 그대로 보여준다.
            bonds.append({
                "key": key, "name": name, "value": round(qb["price"], 3), "change": _rnd(qb["change"], 3),
                "change_pct": round(qb["change_pct"], 2) if qb["change_pct"] is not None else None,
            })
        bond_us10y = next((b for b in bonds if b["key"] == "bond_us10y"), None)   # 시장 브리핑 프롬프트용
        return {"source": "live", "us_indices": us, "fx": fx, "bonds": bonds, "bond_us10y": bond_us10y}
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
        return {"source": "unavailable", "error": str(exc)}


# 시장 한눈에 스파크라인용 — 다우/나스닥/S&P500/환율/미국채10·30년 1년치 일별 종가(Yahoo chart
# API의 timestamp[]+close[] 배열을 그대로 씀. get_global_market_snapshot과 별도 캐시라,
# 스파크라인 요청이 실시간 시세 캐시를 밀어내지 않는다).
def _yf_history(symbol: str) -> dict:
    resp = requests.get(
        _YF_CHART + symbol, params={"range": "1y", "interval": "1d"},
        headers={"User-Agent": "Mozilla/5.0"}, timeout=8,
    )
    resp.raise_for_status()
    result = resp.json()["chart"]["result"][0]
    ts = result.get("timestamp") or []
    closes = (result.get("indicators") or {}).get("quote", [{}])[0].get("close") or []
    labels, values = [], []
    for t, c in zip(ts, closes):
        if c is None:
            continue
        labels.append(datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d"))
        values.append(round(c, 2))
    if not values:
        raise ValueError(f"{symbol} 히스토리 없음")
    return {"labels": labels, "values": values}


def _cny_krw_history() -> dict:
    """CNYKRW=X 는 현재가만 주고 1년 일별 이력이 비어 온다 — 원/달러(KRW=X) ÷ 위안/달러(CNY=X)
    교차환율로 같은 날짜끼리 계산한다."""
    krw, cny = _yf_history("KRW=X"), _yf_history("CNY=X")
    cny_by_day = dict(zip(cny["labels"], cny["values"]))
    labels, values = [], []
    for d, v in zip(krw["labels"], krw["values"]):
        c = cny_by_day.get(d)
        if c:
            labels.append(d)
            values.append(round(v / c, 2))
    if len(values) < 2:
        raise ValueError("CNY/KRW 히스토리 없음")
    return {"labels": labels, "values": values}


@ttl_cache(3600 * 6)
def get_global_market_history_1y() -> dict:
    try:
        out = {"source": "live"}
        for name, sym in _US_INDICES:
            out[name] = _yf_history(sym)
        for key, _name, sym in _US_BONDS:
            out[key] = _yf_history(sym)
        # 환율 스파크라인 — 한 통화가 실패해도 지수 그래프는 살린다(해당 카드만 그래프 없음)
        for name, sym, mult in _FX_PAIRS:
            try:
                h = _cny_krw_history() if name == "CNY/KRW" else _yf_history(sym)
                out[name] = {"labels": h["labels"], "values": [round(v * mult, 2) for v in h["values"]]}
            except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
                pass
        return out
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
        return {"source": "unavailable", "error": str(exc)}
