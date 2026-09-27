"""뉴욕 연준(NY Fed) Markets API — 미국 연방기금 목표금리 범위(일별, 키 불필요).

ECOS 902Y006(국제 주요국 정책금리, 월별)의 미국 값은 한 달 이상 늦게 반영되고 목표 범위의
중간값이라(예: 3.50~3.75% → 3.625%), 국내 보도에서 쓰는 "상단 기준" 한·미 금리차와 맞지 않았다.
EFFR 일별 응답에 실린 targetRateFrom/To(목표 범위 하단/상단)를 쓴다.
"""
from __future__ import annotations

import time
from datetime import timedelta

import requests

from main.cache import ttl_cache
from main.utils import today_kst

_URL = "https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json"


@ttl_cache(60 * 60)
def fed_target_range(days_back: int = 800) -> list[dict]:
    """[{"date": 'YYYY-MM-DD', "lower": 3.75, "upper": 4.0}, ...] 날짜 오름차순. 실패 시 예외."""
    end = today_kst()
    params = {"startDate": (end - timedelta(days=days_back)).isoformat(), "endDate": end.isoformat()}
    for i in range(3):   # 일시적 연결 끊김만 짧게 재시도
        try:
            resp = requests.get(_URL, params=params, timeout=20)
            resp.raise_for_status()
            break
        except (requests.ConnectionError, requests.Timeout):
            if i == 2:
                raise
            time.sleep(0.8 * (i + 1))
    out = []
    for r in resp.json().get("refRates") or []:
        lo, hi = r.get("targetRateFrom"), r.get("targetRateTo")
        if r.get("effectiveDate") and lo is not None and hi is not None:
            out.append({"date": r["effectiveDate"], "lower": float(lo), "upper": float(hi)})
    if not out:
        raise RuntimeError("NY Fed 목표금리 응답 없음")
    out.sort(key=lambda x: x["date"])
    return out
