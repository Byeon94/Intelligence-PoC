"""증시자금 / 유동성 지표.

data.go.kr 「금융위원회_금융투자협회종합통계정보」(GetKofiaStatisticsInfoService)
  - getSecuritiesMarketTotalCapitalInfo : 증시자금 추이 (투자자예탁금 등, 일자별)
  - getCMAStatus                        : 일자별 CMA 현황 (운용대상×투자자구분)
  - getGrantingOfCreditBalanceInfo      : 신용공여 잔고 추이 (일자별)

금액 원자료 단위: 원.  키가 없거나 호출/파싱 실패 시 sample_data 로 폴백.
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import date, timedelta

from . import sample_data
from ._cache import ttl_cache
from ._datago import DataGoError, get_json, pick, to_float

logger = logging.getLogger(__name__)

_SERVICE = "GetKofiaStatisticsInfoService"
_OPS = {
    "stock_fund": "getSecuritiesMarketTotalCapitalInfo",
    "cma": "getCMAStatus",
    "credit": "getGrantingOfCreditBalanceInfo",
}
_JO = 1_000_000_000_000  # 원 → 조원


def _jo(raw) -> float | None:
    v = to_float(raw)
    return None if v is None else round(v / _JO, 2)


def _range_params(months: int) -> dict:
    begin = date.today() - timedelta(days=int(months * 31) + 45)
    return {
        "beginBasDt": begin.strftime("%Y%m%d"),
        "endBasDt": date.today().strftime("%Y%m%d"),
        "numOfRows": 20000,
    }


def _rows(op_key: str, months: int) -> list[dict]:
    return get_json(_SERVICE, _OPS[op_key], _range_params(months))


def _date_of(row: dict) -> str | None:
    return pick(row, "basDt", "BAS_DT", "stdDt", "trdDt")


def _sorted_by_date(rows: list[dict]) -> list[dict]:
    return sorted((r for r in rows if _date_of(r)), key=_date_of)


def _ym(basdt: str) -> str:
    return f"{basdt[:4]}-{basdt[4:6]}"


# ── 원자료 → 지표값 ────────────────────────────────────────────────
def _investor_deposits(row: dict) -> float | None:
    return _jo(pick(row, "invrDpsgAmt", "invrDpsAmt"))


def _credit_total(row: dict) -> float | None:
    """신용공여 잔고 = 신용거래융자 + 신용거래대주 + 청약자금대출 + 예탁증권담보융자."""
    parts = [
        to_float(pick(row, "crdTrFingWhl")),
        to_float(pick(row, "crdTrLndrWhl")),
        to_float(pick(row, "sbscCapLn")),
        to_float(pick(row, "dpsgScrtMogFing")),
    ]
    vals = [p for p in parts if p is not None]
    if not vals:
        return None
    return round(sum(vals) / _JO, 2)


def _cma_total_by_day(cma_rows: list[dict]) -> "OrderedDict[str, float]":
    """basDt → CMA 총잔고(조원).  mngInvTgt=='합계' 행의 개인+기관 합."""
    acc: dict[str, float] = {}
    for r in cma_rows:
        if pick(r, "mngInvTgt") != "합계":
            continue
        d = _date_of(r)
        bal = to_float(pick(r, "actBal"))
        if d and bal is not None:
            acc[d] = acc.get(d, 0.0) + bal
    return OrderedDict((d, round(v / _JO, 2)) for d, v in sorted(acc.items()))


def _monthly_last(rows: list[dict], value_fn) -> "OrderedDict[str, float]":
    """월별 마지막(월말) 값."""
    out: "OrderedDict[str, float]" = OrderedDict()
    for r in _sorted_by_date(rows):
        v = value_fn(r)
        if v is not None:
            out[_ym(_date_of(r))] = v
    return out


def _monthly_from_daymap(daymap: "OrderedDict[str, float]") -> "OrderedDict[str, float]":
    out: "OrderedDict[str, float]" = OrderedDict()
    for d, v in daymap.items():
        out[_ym(d)] = v
    return out


# ── 라이브 구현 ───────────────────────────────────────────────────
def _live_trend(months: int) -> dict:
    n = max(months, 1)
    fund = _rows("stock_fund", n)
    credit = _rows("credit", n)
    cma = _rows("cma", n)
    if not fund or not cma:
        raise DataGoError("증시자금/CMA 응답 비어 있음")

    dep = _monthly_last(fund, _investor_deposits)
    cr = _monthly_last(credit, _credit_total)
    cm = _monthly_from_daymap(_cma_total_by_day(cma))

    labels = sorted(set(dep) & set(cm))[-n:]
    if not labels:
        raise DataGoError("월별 라벨 산출 실패")
    return {
        "labels": labels,
        "series": {
            "investor_deposits": [dep.get(k) for k in labels],
            "credit_balance": [cr.get(k) for k in labels],
            "cma_balance": [cm.get(k) for k in labels],
        },
        "unit": "조원",
        "source": "live",
    }


def _live_summary() -> dict:
    fund = _sorted_by_date(_rows("stock_fund", 3))
    credit = _sorted_by_date(_rows("credit", 3))
    cma_daymap = _cma_total_by_day(_rows("cma", 3))
    if not fund or not cma_daymap:
        raise DataGoError("summary 응답 비어 있음")

    def last2(rows, fn):
        vals = [fn(r) for r in rows]
        vals = [v for v in vals if v is not None]
        if not vals:
            return None, None
        return vals[-1], (vals[-2] if len(vals) > 1 else vals[-1])

    dep, dep0 = last2(fund, _investor_deposits)
    cr, cr0 = last2(credit, _credit_total)
    cma_vals = list(cma_daymap.values())
    cm, cm0 = cma_vals[-1], (cma_vals[-2] if len(cma_vals) > 1 else cma_vals[-1])
    if None in (dep, cr, cm):
        raise DataGoError("summary 필드 매핑 실패")

    ratio = round(cr / dep * 100, 2)
    ratio0 = round(cr0 / dep0 * 100, 2) if dep0 else ratio
    as_of = _date_of(fund[-1]) or ""
    return {
        "as_of": f"{as_of[:4]}-{as_of[4:6]}-{as_of[6:]}" if len(as_of) == 8 else as_of,
        "unit": "조원",
        "items": {
            "investor_deposits": {"value": dep, "change": round(dep - dep0, 2)},
            "credit_balance": {"value": cr, "change": round(cr - cr0, 2)},
            "cma_balance": {"value": cm, "change": round(cm - cm0, 2)},
            "credit_deposit_ratio": {"value": ratio, "change": round(ratio - ratio0, 2), "unit": "%"},
        },
        "source": "live",
    }


# ── 공개 함수 ─────────────────────────────────────────────────────
@ttl_cache(600)
def get_liquidity_summary() -> dict:
    try:
        return _live_summary()
    except (DataGoError, KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        logger.info("유동성 summary 폴백(sample): %s", exc)
        return sample_data.liquidity_summary()


@ttl_cache(600)
def get_liquidity_trend(months: int = 24) -> dict:
    try:
        return _live_trend(months)
    except (DataGoError, KeyError, TypeError, ValueError) as exc:
        logger.info("유동성 trend 폴백(sample): %s", exc)
        return sample_data.liquidity_trend(months)
