import logging
import time
from datetime import datetime

import requests
import yfinance as yf

logger = logging.getLogger(__name__)

# KRX 공식 API는 로그인 세션이 필요해 계정 없이 쓸 수 없으므로,
# 코스피/코스닥은 로그인 없이 열람 가능한 네이버 금융 공개 엔드포인트를 사용한다.
NAVER_INDEX_URL = "https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI,KOSDAQ"

KRX_INDICES = [
    {"code": "KOSPI", "name": "코스피", "market": "KR"},
    {"code": "KOSDAQ", "name": "코스닥", "market": "KR"},
]

US_INDICES = [
    {"ticker": "^IXIC", "name": "나스닥", "market": "US"},
    {"ticker": "^GSPC", "name": "S&P 500", "market": "US"},
    {"ticker": "^DJI", "name": "다우존스", "market": "US"},
]

# yfinance 조회가 지수당 1초 안팎 걸려 페이지 로드마다 다시 부르면 느리므로 짧게 캐시한다.
CACHE_TTL_SECONDS = 300
_cache: dict[str, object] = {"data": None, "ts": 0.0}


def _fetch_krx_indices() -> dict[str, tuple[float, float, float, str]]:
    response = requests.get(
        NAVER_INDEX_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=10
    )
    response.raise_for_status()
    payload = response.json()

    result = {}
    for item in payload.get("datas", []):
        as_of = datetime.fromisoformat(item["localTradedAt"]).date().isoformat()
        result[item["itemCode"]] = (
            float(item["closePriceRaw"]),
            float(item["compareToPreviousClosePriceRaw"]),
            float(item["fluctuationsRatioRaw"]),
            as_of,
        )
    return result


def _fetch_us_index(ticker: str) -> tuple[float, float, float, str]:
    hist = yf.Ticker(ticker).history(period="5d")
    if len(hist) < 2:
        raise ValueError(f"미국 지수 데이터가 부족합니다: {ticker}")

    latest_close = float(hist.iloc[-1]["Close"])
    prev_close = float(hist.iloc[-2]["Close"])
    change = latest_close - prev_close
    change_pct = change / prev_close * 100
    as_of = hist.index[-1].date().isoformat()
    return latest_close, change, change_pct, as_of


def get_market_indices(use_cache: bool = True) -> list[dict]:
    now = time.time()
    if use_cache and _cache["data"] is not None and now - _cache["ts"] < CACHE_TTL_SECONDS:
        return _cache["data"]

    results = []

    try:
        krx_data = _fetch_krx_indices()
    except (requests.exceptions.RequestException, KeyError, ValueError):
        logger.exception("KRX 지수(코스피/코스닥) 조회 실패")
        krx_data = {}

    for idx in KRX_INDICES:
        if idx["code"] not in krx_data:
            continue
        value, change, change_pct, as_of = krx_data[idx["code"]]
        results.append(
            {
                "name": idx["name"],
                "market": idx["market"],
                "value": value,
                "change": change,
                "change_pct": change_pct,
                "as_of": as_of,
            }
        )

    for idx in US_INDICES:
        try:
            value, change, change_pct, as_of = _fetch_us_index(idx["ticker"])
        except Exception:
            logger.exception("미국 지수 조회 실패: %s", idx["ticker"])
            continue
        results.append(
            {
                "name": idx["name"],
                "market": idx["market"],
                "value": value,
                "change": change,
                "change_pct": change_pct,
                "as_of": as_of,
            }
        )

    if results:
        _cache["data"] = results
        _cache["ts"] = now
    return results
