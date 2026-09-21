"""전사 위젯 > 업종별 밸류체인(반도체·2차전지·바이오·자동차 4개).

VALUE_CHAIN(큐레이션 구성)의 각 단계별 종목코드에 credit.equity.listed_snapshot()
실시간 시세(시가총액·등락률)를 덧입혀 보여준다.
"""
from __future__ import annotations

from capital._cache import ttl_cache
from credit.equity import listed_snapshot, listed_snapshot_as_of

from .constituents import VALUE_CHAIN

_NOTE = (
    "주요 기업 예시로 구성한 밸류체인이며(큐레이션, KRX 업종분류 무료 API가 없어 수기 선별), "
    "실제 공급망은 더 많은 기업을 포함할 수 있습니다."
)


@ttl_cache(60 * 30)
def get_value_chain() -> dict:
    snap = {s["code"]: s for s in listed_snapshot()}
    chains = []
    for key, chain in VALUE_CHAIN.items():
        stages = []
        for stage in chain["stages"]:
            companies = []
            for code in stage["codes"]:
                s = snap.get(code) or {}
                companies.append({
                    "code": code,
                    "name": s.get("name") or code,
                    "close": s.get("close"),
                    "market_cap": s.get("market_cap"),
                    "change_pct": s.get("change_pct"),
                })
            stages.append({"name": stage["name"], "companies": companies})
        chains.append({"key": key, "label": chain["label"], "stages": stages})
    return {"chains": chains, "as_of": listed_snapshot_as_of(), "note": _NOTE}
