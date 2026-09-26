"""DATA_GO_KR_API_KEY / DART_API_KEY 가 없거나 호출이 실패했을 때 쓰는 기업분석 샘플.

값은 2023~2025년 공개 자료의 대략적 수준을 참고한 합성치이며, 화면 레이아웃·차트를
확인하기 위한 용도다. 샘플은 _SAMPLES 에 등록된 종목(has())에만 쓰고 응답에 항상
source="sample" 을 단다 — 임의 종목에 지어낸 숫자를 실데이터처럼 보여주지 않기 위함.
"""
from __future__ import annotations

from main.utils import today_iso, today_kst

_SAMPLES: dict[str, dict] = {
    "005930": {
        "name": "삼성전자", "market": "KOSPI", "sector": "반도체와반도체장비",
        "close": 78_500, "change": 1_200, "change_pct": 1.55,
        "market_cap": 468_000_000_000_000, "trade_value": 780_000_000_000,
        "volume": 12_400_000, "shares": 5_969_782_550,
        "est_year": "1969", "settle_month": "12", "rank": 1, "rank_in_market": 1,
        "per": 13.8, "pbr": 1.3, "lo52": 70_980, "hi52": 88_800,
    },
    "000660": {
        "name": "SK하이닉스", "market": "KOSPI", "sector": "반도체와반도체장비",
        "close": 178_000, "change": -2_500, "change_pct": -1.39,
        "market_cap": 129_000_000_000_000, "trade_value": 640_000_000_000,
        "volume": 3_600_000, "shares": 728_002_365,
        "est_year": "1983", "settle_month": "12", "rank": 3, "rank_in_market": 3,
        "per": 9.1, "pbr": 1.6, "lo52": 108_000, "hi52": 248_500,
    },
}


def has(code: str) -> bool:
    """샘플이 준비된 종목인지."""
    return code in _SAMPLES


def _rng(low: float, high: float, cur: float) -> dict:
    pos = round((cur - low) / (high - low) * 100) if high > low else 0
    return {"low": low, "high": high, "current": cur, "pos_pct": max(0, min(100, pos))}


def basics(code: str) -> dict:
    """샘플 기초정보 — has(code) 인 종목만 호출할 것."""
    s = _SAMPLES[code]
    cur = s["close"]
    fin = financials(code)
    revenue = next((v for v in reversed(fin["revenue"]) if v), None)
    return {
        "code": code, "name": s["name"], "market": s["market"], "sector": s["sector"],
        "as_of": today_iso(),
        "close": s["close"], "change": s["change"], "change_pct": s["change_pct"],
        "market_cap": s["market_cap"],
        "market_cap_rank": s["rank"], "market_cap_rank_in_market": s["rank_in_market"],
        "market_cap_total": 2870,
        "trade_value": s["trade_value"],
        "trade_value_pct": round(s["trade_value"] / s["market_cap"] * 100, 2),
        "volume": s["volume"], "shares": s["shares"],
        "est_year": s["est_year"], "settle_month": s["settle_month"],
        "valuation": {
            "per": s["per"], "pbr": s["pbr"],
            "psr": round(s["market_cap"] / revenue, 2) if revenue else None,
        },
        "ranges": {
            "w52": _rng(s["lo52"], s["hi52"], cur),
            "w20": _rng(round(cur * 0.88), round(cur * 1.14), cur),
            "w10": _rng(round(cur * 0.93), round(cur * 1.08), cur),
        },
        "source": "sample",
    }


def financials(code: str) -> dict:
    """샘플 재무 — has(code) 인 종목만 호출할 것(삼성전자 외는 완만한 성장 곡선 합성치)."""
    from .financials import block, recent_quarters  # 순환 import 방지(financials 가 이 모듈을 씀)

    y0 = today_kst().year - 1
    ylabels = [str(y0 - 2), str(y0 - 1), str(y0)]

    if code == "005930":
        rev = [258_935_494_000_000, 300_870_903_000_000, 322_000_000_000_000]
        opi = [6_566_976_000_000, 32_725_961_000_000, 40_200_000_000_000]
        ni = [15_487_100_000_000, 34_451_351_000_000, 42_000_000_000_000]
        assets = [455_905_980_000_000, 514_531_948_000_000, 545_000_000_000_000]
        liab = [92_228_115_000_000, 112_339_878_000_000, 118_000_000_000_000]
        eq = [363_677_865_000_000, 402_192_070_000_000, 427_000_000_000_000]
    else:
        base = 1_200_000_000_000
        rev = [base, round(base * 1.09), round(base * 1.18)]
        opi = [round(v * 0.088) for v in rev]
        ni = [round(v * 0.065) for v in rev]
        assets = [round(base * 2.4), round(base * 2.6), round(base * 2.8)]
        liab = [round(a * 0.44) for a in assets]
        eq = [a - l for a, l in zip(assets, liab)]

    annual = block(ylabels, rev, opi, ni, assets, liab, eq)

    # 분기: 최신 연도 값을 4등분해 완만한 성장 곡선으로 합성
    qs = list(reversed(recent_quarters(4)))
    qr = round(rev[-1] / 4)
    q_rev = [round(qr * (0.90 + 0.07 * i)) for i in range(4)]
    q_opi = [round(v * (opi[-1] / rev[-1] if rev[-1] else 0.1)) for v in q_rev]
    q_ni = [round(v * (ni[-1] / rev[-1] if rev[-1] else 0.08)) for v in q_rev]
    q_ass = [round(assets[-1] * (0.94 + 0.02 * i)) for i in range(4)]
    q_liab = [round(assets[-1] * (liab[-1] / assets[-1] if assets[-1] else 0.24) * (0.94 + 0.02 * i))
              for i in range(4)]
    q_eq = [a - l for a, l in zip(q_ass, q_liab)]
    quarters = block([f"{y} {q}Q" for y, q in qs], q_rev, q_opi, q_ni, q_ass, q_liab, q_eq)

    return {
        "code": code, "unit": "원", "fiscal_year": str(y0),
        **annual,
        "annual": annual,
        "quarters": quarters,
        "source": "sample",
    }
