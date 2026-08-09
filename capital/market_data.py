import logging
import time
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

# KRX 공식 API는 로그인 세션이 필요해 계정 없이 쓸 수 없고, 미국 지수에 쓰던 yfinance(Yahoo
# Finance)는 Render 같은 클라우드 호스팅 IP를 자주 rate-limit 해서(YFRateLimitError) 지수가
# 누락되는 문제가 있었다. 그래서 국내외 지수 모두 로그인 없이 열람 가능한 네이버 금융의 공개
# 폴링 엔드포인트로 통일했다 (국내: domestic/index, 해외: worldstock/index).
NAVER_DOMESTIC_INDEX_URL = "https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI,KOSDAQ"
NAVER_WORLD_INDEX_URL = "https://polling.finance.naver.com/api/realtime/worldstock/index/.DJI,.IXIC,.INX"

KRX_INDICES = [
    {"code": "KOSPI", "name": "코스피", "market": "KR"},
    {"code": "KOSDAQ", "name": "코스닥", "market": "KR"},
]

US_INDICES = [
    {"code": ".IXIC", "name": "나스닥", "market": "US"},
    {"code": ".INX", "name": "S&P 500", "market": "US"},
    {"code": ".DJI", "name": "다우존스", "market": "US"},
]

# 지수 조회가 매번 새로 부르면 느리므로 짧게 캐시한다.
CACHE_TTL_SECONDS = 300
_cache: dict[str, object] = {"data": None, "ts": 0.0}


def _fetch_naver_indices(url: str) -> dict[str, tuple[float, float, float, str]]:
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    response.raise_for_status()
    payload = response.json()

    result = {}
    for item in payload.get("datas", []):
        code = item.get("itemCode") or item.get("reutersCode")
        as_of = datetime.fromisoformat(item["localTradedAt"]).date().isoformat()
        result[code] = (
            float(item["closePriceRaw"]),
            float(item["compareToPreviousClosePriceRaw"]),
            float(item["fluctuationsRatioRaw"]),
            as_of,
        )
    return result


def _build_results(indices: list[dict], data: dict) -> list[dict]:
    results = []
    for idx in indices:
        if idx["code"] not in data:
            continue
        value, change, change_pct, as_of = data[idx["code"]]
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
    return results


def get_market_indices(use_cache: bool = True) -> list[dict]:
    now = time.time()
    if use_cache and _cache["data"] is not None and now - _cache["ts"] < CACHE_TTL_SECONDS:
        return _cache["data"]

    results = []

    try:
        krx_data = _fetch_naver_indices(NAVER_DOMESTIC_INDEX_URL)
    except (requests.exceptions.RequestException, KeyError, ValueError):
        logger.exception("KRX 지수(코스피/코스닥) 조회 실패")
        krx_data = {}
    results.extend(_build_results(KRX_INDICES, krx_data))

    try:
        us_data = _fetch_naver_indices(NAVER_WORLD_INDEX_URL)
    except (requests.exceptions.RequestException, KeyError, ValueError):
        logger.exception("미국 지수 조회 실패")
        us_data = {}
    results.extend(_build_results(US_INDICES, us_data))

    if results:
        _cache["data"] = results
        _cache["ts"] = now
    return results
