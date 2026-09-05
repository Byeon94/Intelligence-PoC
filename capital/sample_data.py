"""API 키가 없거나 호출이 실패했을 때 쓰는 샘플(mock) 데이터.

값은 2024~2025년 공개 통계의 대략적 수준을 참고한 합성치이며,
화면 레이아웃과 추이 차트를 그대로 확인하기 위한 용도다.
실데이터가 연결되면 응답의 source 필드가 "live"로 바뀐다.
"""
from __future__ import annotations

import math
from datetime import date


def month_labels(n: int) -> list[str]:
    today = date.today()
    y, m = today.year, today.month
    out: list[str] = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(out))


def _series(n: int, base: float, drift: float, wave: float, period: int = 12) -> list[float]:
    """base에서 시작해 drift(총 증감률)만큼 완만히 이동 + 계절성 물결."""
    vals: list[float] = []
    for i in range(n):
        t = i / max(n - 1, 1)
        seasonal = 1 + wave * math.sin(2 * math.pi * i / period)
        vals.append(round(base * (1 + drift * t) * seasonal, 2))
    return vals


def liquidity_trend(months: int = 24) -> dict:
    labels = month_labels(months)
    deposits = _series(months, 50.0, 0.10, 0.05)
    credit = _series(months, 19.5, 0.16, 0.04)
    cma = _series(months, 78.0, 0.13, 0.03)
    return {
        "labels": labels,
        "series": {
            "investor_deposits": deposits,
            "credit_balance": credit,
            "cma_balance": cma,
        },
        "unit": "조원",
        "source": "sample",
    }


def liquidity_summary() -> dict:
    tr = liquidity_trend(3)
    dep = tr["series"]["investor_deposits"]
    cr = tr["series"]["credit_balance"]
    cma = tr["series"]["cma_balance"]
    ratio = round(cr[-1] / dep[-1] * 100, 2)
    prev_ratio = round(cr[-2] / dep[-2] * 100, 2)
    return {
        "as_of": _last_business_day_iso(),
        "unit": "조원",
        "items": {
            "investor_deposits": {"value": dep[-1], "change": round(dep[-1] - dep[-2], 2)},
            "credit_balance": {"value": cr[-1], "change": round(cr[-1] - cr[-2], 2)},
            "cma_balance": {"value": cma[-1], "change": round(cma[-1] - cma[-2], 2)},
            "credit_deposit_ratio": {"value": ratio, "change": round(ratio - prev_ratio, 2), "unit": "%"},
        },
        "source": "sample",
    }


def turnover_trend(months: int = 24) -> dict:
    labels = month_labels(months)
    kospi = _series(months, 210.0, 0.18, 0.12)
    kosdaq = _series(months, 150.0, 0.10, 0.15)
    return {
        "labels": labels,
        "series": {
            "kospi": [round(v, 1) for v in kospi],
            "kosdaq": [round(v, 1) for v in kosdaq],
            "total": [round(a + b, 1) for a, b in zip(kospi, kosdaq)],
        },
        "unit": "조원(월 누계)",
        "source": "sample",
    }


def turnover_summary() -> dict:
    tr = turnover_trend(2)
    kospi_m = tr["series"]["kospi"][-1]
    kosdaq_m = tr["series"]["kosdaq"][-1]
    total_m = round(kospi_m + kosdaq_m, 1)
    trading_days = 20
    return {
        "month": tr["labels"][-1],
        "unit": "조원",
        "items": {
            "kospi_month_total": {"value": kospi_m, "change": round(kospi_m - tr["series"]["kospi"][-2], 1)},
            "kosdaq_month_total": {"value": kosdaq_m, "change": round(kosdaq_m - tr["series"]["kosdaq"][-2], 1)},
            "total_month": {"value": total_m, "change": round(total_m - (tr["series"]["kospi"][-2] + tr["series"]["kosdaq"][-2]), 1)},
            "daily_avg": {"value": round(total_m / trading_days, 2)},
        },
        "trading_days": trading_days,
        "source": "sample",
    }


# ── CMA ─────────────────────────────────────────────────────────────
CMA_MIX = [
    {"type": "RP형", "share": 47.5},
    {"type": "기타(MMW)", "share": 26.0},
    {"type": "발행어음형", "share": 20.5},
    {"type": "MMF형", "share": 4.6},
    {"type": "종금형", "share": 1.4},
]


def cma_summary() -> dict:
    total = round(liquidity_summary()["items"]["cma_balance"]["value"], 1)
    by_type = {m["type"]: round(total * m["share"] / 100, 1) for m in CMA_MIX}
    from .cma_rates import top_rp_rate  # 지연 import (순환 방지)

    top = top_rp_rate()
    return {
        "as_of": _last_business_day_iso(),
        "unit": "조원",
        "items": {
            "total": {"value": total},
            "rp": {"value": by_type["RP형"], "share": 47.5},
            "note": {"value": by_type["발행어음형"], "share": 20.5},
            "rp_top_rate": {"value": top["rate"], "company": top["company"], "unit": "%"},
        },
        "source": "sample",
    }


def cma_mix() -> dict:
    total = round(liquidity_summary()["items"]["cma_balance"]["value"], 1)
    mix = [
        {"type": m["type"], "share": m["share"], "balance": round(total * m["share"] / 100, 1)}
        for m in CMA_MIX
    ]
    return {"as_of": _last_business_day_iso(), "mix": mix, "total": total, "source": "sample"}


def _last_business_day_iso() -> str:
    d = date.today()
    while d.weekday() >= 5:  # 토(5)·일(6)
        d = date.fromordinal(d.toordinal() - 1)
    return d.isoformat()
