"""자본시장 > CMA·단기수신 지표.

- 잔고 / 유형별 점유율 : data.go.kr getCMAStatus (실패 시 sample)
- 증권사별 금리 / RP형 최고금리 : capital/cma_rates.py (증권사 공식 홈페이지, 매일 새벽 확인)
"""
from __future__ import annotations

import logging

from . import sample_data
from main.cache import ttl_cache
from main.utils import ymd_to_iso
from ._datago import JO, DataGoError, date_of, kofia_rows, pick, to_float
from .cma_rates import rate_table, top_rp_rate

logger = logging.getLogger(__name__)

# getCMAStatus 의 mngInvTgt 값 → 화면 표기
_TYPE_LABEL = {
    "RP형": "RP형",
    "기타형": "기타(MMW)",
    "발행어음형": "발행어음형",
    "MMF형": "MMF형",
    "종금형": "종금형",
}
_TYPE_ORDER = ["RP형", "기타(MMW)", "발행어음형", "MMF형", "종금형"]


def _latest_breakdown(rows: list[dict]) -> dict:
    """가장 최근 basDt 기준 유형별 잔고(조원) + 총잔고."""
    dated = [r for r in rows if date_of(r)]
    if not dated:
        raise DataGoError("CMA 응답 없음")
    last = max(date_of(r) for r in dated)
    by_type: dict[str, float] = {}
    total_hab = 0.0
    for r in dated:
        if date_of(r) != last:
            continue
        tgt = pick(r, "mngInvTgt")
        bal = to_float(pick(r, "actBal")) or 0.0
        if tgt == "합계":
            total_hab += bal
        elif tgt in _TYPE_LABEL:
            label = _TYPE_LABEL[tgt]
            by_type[label] = by_type.get(label, 0.0) + bal

    if not by_type:
        raise DataGoError("CMA 유형별 행 없음")
    total = total_hab or sum(by_type.values())
    mix = []
    for label in _TYPE_ORDER:
        if label in by_type:
            bal = round(by_type[label] / JO, 1)
            mix.append({"type": label, "balance": bal,
                        "share": round(by_type[label] / total * 100, 1)})
    return {
        "as_of": ymd_to_iso(last),
        "total": round(total / JO, 1),
        "mix": mix,
    }


def _live_mix() -> dict:
    bd = _latest_breakdown(kofia_rows("cma", 2))
    return {"as_of": bd["as_of"], "mix": bd["mix"], "total": bd["total"], "source": "live"}


def _live_summary() -> dict:
    bd = _latest_breakdown(kofia_rows("cma", 2))
    by = {m["type"]: m for m in bd["mix"]}
    rp, note = by.get("RP형", {}), by.get("발행어음형", {})
    top = top_rp_rate()
    return {
        "as_of": bd["as_of"],
        "unit": "조원",
        "items": {
            "total": {"value": bd["total"]},
            "rp": {"value": rp.get("balance"), "share": rp.get("share")},
            "note": {"value": note.get("balance"), "share": note.get("share")},
            "rp_top_rate": {"value": top["rate"], "company": top["company"], "unit": "%",
                            "source": top["source"]},
        },
        "source": "live",
    }


@ttl_cache(600)
def get_cma_summary() -> dict:
    try:
        return _live_summary()
    except (DataGoError, KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        logger.info("CMA summary 폴백(sample): %s", exc)
        return sample_data.cma_summary()


@ttl_cache(600)
def get_cma_mix() -> dict:
    try:
        return _live_mix()
    except (DataGoError, KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        logger.info("CMA mix 폴백(sample): %s", exc)
        return sample_data.cma_mix()


def get_cma_rates(force: bool = False) -> dict:
    """force=True 는 새벽 배치용 — 오늘 스냅샷이 있어도 증권사 페이지를 다시 확인."""
    return rate_table(force=force)
