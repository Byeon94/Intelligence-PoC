"""전사 위젯 > 국내 업종별 시가총액 맵.

credit.equity.listed_snapshot()(data.go.kr 「금융위원회_주식시세정보」 전 종목 실시간
스냅샷) 전체를, sector.classify.get_cached_classification()이 미리 분류해 저장해둔
{종목코드: 업종명}(Gemini, 배치 전용)에 따라 업종별로 묶어 시가총액을 합산한다.
분류가 없는 종목(신규 상장 등)은 "기타"로 묶는다.
"""
from __future__ import annotations

from capital._cache import ttl_cache
from credit.equity import listed_snapshot, listed_snapshot_as_of

from .classify import get_cached_classification

_UNCLASSIFIED = "기타"
_MAX_CONSTITUENTS = 15  # 응답 크기 억제용(업종당 상위 N개만) — 화면은 현재 top_name만 사용

_NOTE = (
    "KRX 업종분류를 무료로 제공하는 곳이 없어, Google Gemini가 전 상장종목을 업종으로 "
    "분류한 결과입니다(배치로 주기 갱신, 참고용). "
    "시세는 공공데이터포털(data.go.kr) 금융위원회 주식시세정보 기준."
)


@ttl_cache(60 * 30)
def get_sector_map() -> dict:
    stocks = [s for s in listed_snapshot() if s.get("market_cap")]
    as_of = listed_snapshot_as_of()
    classification = get_cached_classification()

    groups: dict[str, list[dict]] = {}
    for s in stocks:
        sector = classification.get(s["code"]) or _UNCLASSIFIED
        groups.setdefault(sector, []).append(s)

    sectors = []
    for name, items in groups.items():
        cap_sum = sum(x["market_cap"] for x in items)
        chg_items = [x for x in items if x.get("change_pct") is not None]
        chg_cap = sum(x["market_cap"] for x in chg_items)
        weighted_chg = sum(x["market_cap"] * x["change_pct"] for x in chg_items)
        items_sorted = sorted(items, key=lambda x: x["market_cap"], reverse=True)
        sectors.append({
            "sector": name,
            "market_cap": cap_sum,
            "change_pct": round(weighted_chg / chg_cap, 2) if chg_cap else None,
            "top_name": items_sorted[0]["name"],
            "count": len(items),
            "constituents": [
                {"code": x["code"], "name": x["name"], "market_cap": x["market_cap"], "change_pct": x.get("change_pct")}
                for x in items_sorted[:_MAX_CONSTITUENTS]
            ],
        })

    sectors.sort(key=lambda s: s["market_cap"], reverse=True)
    total = sum(s["market_cap"] for s in sectors)
    # "기타"는 특정 업종을 나타내지 않는 캐치올(분류 실패·미분류 종목 묶음)이라, 맵·순위에는
    # 의미 있는 정보를 주지 못해 화면에서 제외한다(전체 시가총액 total_market_cap 집계에는
    # 그대로 포함해 합계 자체는 왜곡하지 않는다).
    sectors = [s for s in sectors if s["sector"] != _UNCLASSIFIED]
    return {
        "sectors": sectors,
        "total_market_cap": total,
        "as_of": as_of,
        "classified": bool(classification),
        "source": "live" if sectors else "sample",
        "note": _NOTE,
    }
