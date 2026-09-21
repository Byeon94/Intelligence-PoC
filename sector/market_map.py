"""전사 위젯 > 국내 업종별 시가총액 맵.

credit.equity.listed_snapshot()(data.go.kr 「금융위원회_주식시세정보」 전 종목
실시간 스냅샷)에서 SECTOR_MAP(큐레이션)의 종목코드만 뽑아 업종별로 시가총액을
합산한다. 전 상장종목의 공식 업종분류를 무료로 주는 API가 없어, 업종별 시가총액
상위 대표 종목 중심의 근사치다.
"""
from __future__ import annotations

from capital._cache import ttl_cache
from credit.equity import listed_snapshot

from .constituents import SECTOR_MAP

_NOTE = (
    "공공데이터포털(data.go.kr) 금융위원회 주식시세정보 실시간 기준 · "
    "업종별 시가총액 상위 대표 종목 중심 근사치(전 상장종목 대상 아님)"
)


@ttl_cache(60 * 30)
def get_sector_map() -> dict:
    snap = {s["code"]: s for s in listed_snapshot()}
    as_of = None
    sectors = []
    for name, codes in SECTOR_MAP.items():
        items = []
        cap_sum = 0.0
        weighted_chg = 0.0
        for code in codes:
            s = snap.get(code)
            if not s or not s.get("market_cap"):
                continue
            cap = s["market_cap"]
            chg = s.get("change_pct")
            items.append({
                "code": code,
                "name": s.get("name"),
                "market_cap": cap,
                "change_pct": chg,
            })
            cap_sum += cap
            if chg is not None:
                weighted_chg += cap * chg
        if not items:
            continue
        items.sort(key=lambda x: x["market_cap"], reverse=True)
        sectors.append({
            "sector": name,
            "market_cap": cap_sum,
            "change_pct": round(weighted_chg / cap_sum, 2) if cap_sum else None,
            "top_name": items[0]["name"],
            "constituents": items,
        })

    sectors.sort(key=lambda s: s["market_cap"], reverse=True)
    total = sum(s["market_cap"] for s in sectors)
    return {
        "sectors": sectors,
        "total_market_cap": total,
        "source": "live" if sectors else "sample",
        "note": _NOTE,
    }
