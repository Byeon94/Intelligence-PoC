"""국내 주식시장 거래대금 (코스피 / 코스닥).

데이터: data.go.kr 「금융위원회_지수시세정보」
  GET /1160100/service/GetMarketIndexInfoService/getStockMarketIndex
  params: idxNm=코스피|코스닥, beginBasDt, endBasDt
  fields: basDt(기준일자), idxNm, clpr(종가), trqu(거래량), trPrc(거래대금, 원)

일별 trPrc 를 월별로 합산 → 월 거래대금, 거래일수로 나눠 일평균.
키가 없거나 실패하면 sample_data 로 폴백.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta

from . import sample_data
from ._cache import ttl_cache
from ._datago import DataGoError, get_json, pick, to_float

logger = logging.getLogger(__name__)

_SERVICE = "GetMarketIndexInfoService"
_OP = "getStockMarketIndex"
_JO = 1_000_000_000_000  # 원 → 조원


def _fetch_daily(idx_nm: str, months: int) -> list[tuple[str, float]]:
    begin = (date.today() - timedelta(days=int(months * 31) + 40)).strftime("%Y%m%d")
    end = date.today().strftime("%Y%m%d")
    rows = get_json(_SERVICE, _OP, {
        "idxNm": idx_nm,
        "beginBasDt": begin,
        "endBasDt": end,
        "numOfRows": 10000,
    })
    out: list[tuple[str, float]] = []
    for r in rows:
        if pick(r, "idxNm") not in (idx_nm, None):  # '코스피 200' 등 하위지수 제외
            continue
        d = pick(r, "basDt", "BAS_DT")
        v = to_float(pick(r, "trPrc", "TR_PRC"))
        if d and v is not None:
            out.append((str(d), v))
    if not out:
        raise DataGoError(f"{idx_nm} 거래대금 응답 없음")
    return out


_CUR_YM = date.today().strftime("%Y-%m")


def _monthly_totals(daily: list[tuple[str, float]]) -> tuple[list[str], dict[str, float], dict[str, int]]:
    total: dict[str, float] = defaultdict(float)
    days: dict[str, int] = defaultdict(int)
    for d, v in daily:
        ym = f"{d[:4]}-{d[4:6]}"
        total[ym] += v
        days[ym] += 1
    # 진행 중인 당월은 '월 누계'가 미완성이라 제외한다.
    total.pop(_CUR_YM, None)
    days.pop(_CUR_YM, None)
    labels = sorted(total)
    return labels, total, days


def _live_trend(months: int) -> dict:
    kospi_labels, kospi_tot, _ = _monthly_totals(_fetch_daily("코스피", months))
    kosdaq_labels, kosdaq_tot, _ = _monthly_totals(_fetch_daily("코스닥", months))
    labels = sorted(set(kospi_labels) & set(kosdaq_labels))[-months:]
    if not labels:
        raise DataGoError("거래대금 월별 라벨 없음")
    kospi = [round(kospi_tot[k] / _JO, 1) for k in labels]
    kosdaq = [round(kosdaq_tot[k] / _JO, 1) for k in labels]
    return {
        "labels": labels,
        "series": {
            "kospi": kospi,
            "kosdaq": kosdaq,
            "total": [round(a + b, 1) for a, b in zip(kospi, kosdaq)],
        },
        "unit": "조원(월 누계)",
        "source": "live",
    }


def _live_summary(months: int = 3) -> dict:
    k_labels, k_tot, k_days = _monthly_totals(_fetch_daily("코스피", months))
    q_labels, q_tot, q_days = _monthly_totals(_fetch_daily("코스닥", months))
    labels = sorted(set(k_labels) & set(q_labels))
    if len(labels) < 2:
        raise DataGoError("거래대금 summary 월 부족")
    cur, prev = labels[-1], labels[-2]

    k_cur, k_prev = k_tot[cur] / _JO, k_tot[prev] / _JO
    q_cur, q_prev = q_tot[cur] / _JO, q_tot[prev] / _JO
    tot_cur, tot_prev = k_cur + q_cur, k_prev + q_prev
    tdays = max(k_days[cur], q_days[cur], 1)
    return {
        "month": cur,
        "unit": "조원",
        "items": {
            "kospi_month_total": {"value": round(k_cur, 1), "change": round(k_cur - k_prev, 1)},
            "kosdaq_month_total": {"value": round(q_cur, 1), "change": round(q_cur - q_prev, 1)},
            "total_month": {"value": round(tot_cur, 1), "change": round(tot_cur - tot_prev, 1)},
            "daily_avg": {"value": round(tot_cur / tdays, 2)},
        },
        "trading_days": tdays,
        "source": "live",
    }


@ttl_cache(1800)
def get_turnover_summary() -> dict:
    try:
        return _live_summary()
    except (DataGoError, KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        logger.info("거래대금 summary 폴백(sample): %s", exc)
        return sample_data.turnover_summary()


@ttl_cache(1800)
def get_turnover_trend(months: int = 24) -> dict:
    try:
        return _live_trend(months)
    except (DataGoError, KeyError, TypeError, ValueError) as exc:
        logger.info("거래대금 trend 폴백(sample): %s", exc)
        return sample_data.turnover_trend(months)
