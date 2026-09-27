"""한국은행 ECOS Open API 클라이언트(StatisticSearch).

통계표 코드만 주고 항목 코드를 비우면 그 통계표의 전 항목을 한 번에 돌려준다 — 원화 시장금리
27종·환율 53종을 각각 1회 호출로 받기 위해 이 방식을 쓴다. 반환값은 항목코드별 시계열:

    {"010101000": [("2026-09-22", 2.508), ...], ...}   # 날짜 오름차순

키 미설정·API 오류면 예외를 올린다(단기자금 탭은 샘플 데이터 없이 실데이터만 보여준다).
"""
from __future__ import annotations

import time
from datetime import timedelta

import requests

from main.cache import ttl_cache
from main.config import get_settings
from main.utils import today_kst, ymd_to_iso

_BASE = "https://ecos.bok.or.kr/api/StatisticSearch"
_MAX_ROWS = 10000


class EcosError(RuntimeError):
    pass


def _period(cycle: str, days_back: int) -> tuple[str, str]:
    end = today_kst()
    start = end - timedelta(days=days_back)
    if cycle == "M":
        return start.strftime("%Y%m"), end.strftime("%Y%m")
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _time_to_iso(t: str) -> str:
    """'20260922' → '2026-09-22', '202608' → '2026-08'."""
    return ymd_to_iso(t) if len(t) == 8 else (f"{t[:4]}-{t[4:6]}" if len(t) == 6 else t)


def _get_json(url: str, attempts: int = 3) -> dict:
    """ECOS 는 연속 호출 시 가끔 연결을 끊는다(ConnectionReset) — 짧게 쉬었다가 최대 2회 재시도."""
    for i in range(attempts):
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except (requests.ConnectionError, requests.Timeout):
            if i == attempts - 1:
                raise
            time.sleep(0.8 * (i + 1))
    raise EcosError("unreachable")


@ttl_cache(60 * 60)
def fetch_series(stat_code: str, cycle: str, days_back: int, item_code: str = "") -> dict[str, list[tuple[str, float]]]:
    """최근 days_back일 구간의 시계열. 1시간 캐시(ECOS 일별 통계는 하루 한 번 갱신)."""
    key = get_settings().ecos_api_key
    if not key:
        raise EcosError("ECOS_API_KEY 미설정")
    start, end = _period(cycle, days_back)
    url = f"{_BASE}/{key}/json/kr/1/{_MAX_ROWS}/{stat_code}/{cycle}/{start}/{end}"
    if item_code:
        url += f"/{item_code}"
    body = _get_json(url)
    rows = (body.get("StatisticSearch") or {}).get("row")
    if not rows:
        raise EcosError(f"ECOS {stat_code} 응답 없음: {(body.get('RESULT') or {}).get('MESSAGE', '')}")

    out: dict[str, list[tuple[str, float]]] = {}
    for r in rows:
        try:
            v = float(r["DATA_VALUE"])
        except (KeyError, TypeError, ValueError):
            continue
        out.setdefault(r["ITEM_CODE1"], []).append((_time_to_iso(r["TIME"]), v))
    for series in out.values():
        series.sort()
    return out
