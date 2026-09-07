"""여신·심사 > 기업분석: 특정 종목의 기초정보.

데이터
  - 시세/시총/거래대금/거래량/상장주식수/가격범위
      : data.go.kr 「금융위원회_주식시세정보」
        GetStockSecuritiesInfoService/getStockPriceInfo
        fields: basDt, srtnCd, itmsNm, mrktCtg, clpr(종가), vs(전일대비),
                fltRt(등락률), mkp/hipr/lopr, trqu(거래량), trPrc(거래대금, 원),
                lstgStCnt(상장주식수), mrktTotAmt(시가총액, 원)
      · 일별 400일치를 받아 최신일 = 기준일, hipr/lopr 로 52·20·10주 범위 계산
      · 전체 종목 스냅샷으로 시가총액 순위 계산
  - 설립연도/결산월 : 금융감독원 DART 기업개황 company.json
  - 업종·PER·PBR : 네이버 금융 종목 페이지 (참고용)
  - PSR : 시가총액 ÷ 최근 연간 매출액(DART)

키가 없거나 호출이 실패하면 해당 항목은 비우고, 시세 자체가 실패하면 sample 로 폴백.
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta

import requests

from capital._cache import ttl_cache
from capital._datago import DataGoError, get_json, pick, to_float
from main.config import get_settings

from . import sample_data
from .corp_map import corp_code

logger = logging.getLogger(__name__)

_PRICE_SVC, _PRICE_OP = "GetStockSecuritiesInfoService", "getStockPriceInfo"
_NAVER_URL = "https://finance.naver.com/item/main.naver"


def _fmt_date(yyyymmdd: str | None) -> str:
    s = str(yyyymmdd or "")
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else s


def _daily_rows(code: str, days: int) -> list[dict]:
    rows = get_json(_PRICE_SVC, _PRICE_OP, {
        "likeSrtnCd": code,
        "beginBasDt": (date.today() - timedelta(days=days)).strftime("%Y%m%d"),
        "endBasDt": date.today().strftime("%Y%m%d"),
    })
    rows = [r for r in rows if str(pick(r, "srtnCd", "SRTN_CD")) == code]
    rows.sort(key=lambda r: str(pick(r, "basDt", "BAS_DT")))
    if not rows:
        raise DataGoError(f"{code} 시세 응답 없음")
    return rows


def _range(rows: list[dict], win_days: int) -> dict | None:
    cutoff = (date.today() - timedelta(days=win_days)).strftime("%Y%m%d")
    sub = [r for r in rows if str(pick(r, "basDt", "BAS_DT")) >= cutoff] or rows
    lows = [v for v in (to_float(pick(r, "lopr", "LOPR")) for r in sub) if v]
    highs = [v for v in (to_float(pick(r, "hipr", "HIPR")) for r in sub) if v]
    cur = to_float(pick(rows[-1], "clpr", "CLPR"))
    if not lows or not highs or cur is None:
        return None
    lo, hi = min(lows), max(highs)
    pos = round((cur - lo) / (hi - lo) * 100) if hi > lo else 0
    return {"low": lo, "high": hi, "current": cur, "pos_pct": max(0, min(100, pos))}


@ttl_cache(60 * 60 * 12)
def _dart_company(code: str) -> dict:
    """DART 기업개황 — 설립연도·결산월. 키 없거나 실패 시 빈 dict."""
    key = get_settings().dart_api_key
    cc = corp_code(code) if key else None
    if not cc:
        return {}
    try:
        resp = requests.get(
            "https://opendart.fss.or.kr/api/company.json",
            params={"crtfc_key": key, "corp_code": cc},
            timeout=15,
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.info("DART company 조회 실패(%s): %s", code, exc)
        return {}
    if data.get("status") != "000":
        return {}
    est = (data.get("est_dt") or "").strip()
    return {
        "est_year": est[:4] if len(est) == 8 else None,
        "settle_month": (data.get("acc_mt") or "").strip() or None,
    }


@ttl_cache(60 * 60)
def _naver_snapshot(code: str) -> dict:
    """네이버 금융 종목 페이지에서 업종·PER·PBR 를 긁어온다(참고용). 실패 시 빈 dict."""
    try:
        resp = requests.get(
            _NAVER_URL, params={"code": code},
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10,
        )
        resp.raise_for_status()
        html = resp.content.decode("utf-8", "replace")
    except requests.RequestException as exc:
        logger.info("네이버 금융 조회 실패(%s): %s", code, exc)
        return {}

    def _find(pattern: str) -> float | None:
        m = re.search(pattern, html)
        return to_float(m.group(1)) if m else None

    sector = None
    m = re.search(r"업종명\s*:\s*<a[^>]*>([^<]+)</a>", html)
    if m:
        sector = m.group(1).strip()
    return {
        "sector": sector,
        "per": _find(r'id="_per"[^>]*>\s*([\d,.\-]+)\s*<'),
        "pbr": _find(r'id="_pbr"[^>]*>\s*([\d,.\-]+)\s*<'),
    }


@ttl_cache(60 * 30)
def _listed_snapshot() -> list[dict]:
    """최근 거래일 전체 상장종목 1스냅샷 (검색 부분일치 + 시가총액 순위용).

    data.go.kr 의 likeItmsNm 은 접두어 매칭이라 '하이닉스' 같은 중간어가 안 걸린다.
    그래서 한 거래일 전체(코스피+코스닥 ≈ 2,900건)를 받아 파이썬에서 처리한다.
    """
    for back in range(3, 12):
        d = (date.today() - timedelta(days=back)).strftime("%Y%m%d")
        try:
            rows = get_json(_PRICE_SVC, _PRICE_OP, {"basDt": d})
        except DataGoError:
            continue
        out: dict[str, dict] = {}
        for r in rows:
            code = str(pick(r, "srtnCd", "SRTN_CD") or "")
            if len(code) != 6:
                continue
            out[code] = {
                "code": code,
                "name": pick(r, "itmsNm", "ITMS_NM"),
                "market": pick(r, "mrktCtg", "MRKT_CTG"),
                "close": to_float(pick(r, "clpr", "CLPR")),
                "market_cap": to_float(pick(r, "mrktTotAmt", "MRKT_TOT_AMT")),
            }
        if out:
            return list(out.values())
    logger.info("종목 스냅샷 조회 실패")
    return []


def _market_cap_rank(code: str, market: str | None) -> dict:
    """전체 / 동일시장(코스피·코스닥) 내 시가총액 순위."""
    snap = [s for s in _listed_snapshot() if s.get("market_cap")]
    if not snap:
        return {}
    all_sorted = sorted(snap, key=lambda s: s["market_cap"], reverse=True)
    mkt_sorted = [s for s in all_sorted if s.get("market") == market] if market else []
    out: dict = {"total_count": len(all_sorted)}
    for i, s in enumerate(all_sorted, 1):
        if s["code"] == code:
            out["overall"] = i
            break
    for i, s in enumerate(mkt_sorted, 1):
        if s["code"] == code:
            out["in_market"] = i
            out["market_count"] = len(mkt_sorted)
            break
    return out


@ttl_cache(600)
def get_stock_basics(code: str) -> dict:
    try:
        rows = _daily_rows(code, 400)
    except (DataGoError, ValueError, TypeError) as exc:
        logger.info("기초정보 폴백(sample) %s: %s", code, exc)
        return sample_data.basics(code)

    last = rows[-1]
    g = lambda *keys: to_float(pick(last, *keys))
    market = pick(last, "mrktCtg", "MRKT_CTG")

    comp = _dart_company(code)
    nav = _naver_snapshot(code)
    rank = _market_cap_rank(code, market)

    mcap = g("mrktTotAmt", "MRKT_TOT_AMT")
    tval = g("trPrc", "TR_PRC")

    revenue = None
    try:
        from .financials import annual_revenue
        revenue = annual_revenue(code)
    except Exception:  # noqa: BLE001 - PSR 없으면 그냥 비움
        logger.debug("PSR용 매출 조회 실패 %s", code, exc_info=True)

    return {
        "code": code,
        "name": pick(last, "itmsNm", "ITMS_NM"),
        "market": market,
        "sector": nav.get("sector"),
        "as_of": _fmt_date(pick(last, "basDt", "BAS_DT")),
        "close": g("clpr", "CLPR"),
        "change": g("vs", "VS"),
        "change_pct": g("fltRt", "FLT_RT"),
        "market_cap": mcap,
        "market_cap_rank": rank.get("overall"),
        "market_cap_rank_in_market": rank.get("in_market"),
        "market_cap_total": rank.get("total_count"),
        "trade_value": tval,
        "trade_value_pct": round(tval / mcap * 100, 2) if tval and mcap else None,
        "volume": g("trqu", "TRQU"),
        "shares": g("lstgStCnt", "LSTG_ST_CNT"),
        "est_year": comp.get("est_year"),
        "settle_month": comp.get("settle_month"),
        "valuation": {
            "per": nav.get("per"),
            "pbr": nav.get("pbr"),
            "psr": round(mcap / revenue, 2) if mcap and revenue else None,
        },
        "ranges": {
            "w52": _range(rows, 365),
            "w20": _range(rows, 140),
            "w10": _range(rows, 70),
        },
        "source": "live",
    }


@ttl_cache(300)
def search_stocks(q: str) -> list[dict]:
    """종목명(부분일치) 또는 종목코드(접두어) 검색."""
    q = q.strip()
    if len(q) < 2:
        return []
    pool = _listed_snapshot()
    if q.isdigit():
        hits = [s for s in pool if s["code"].startswith(q)]
    else:
        low = q.lower()
        hits = [s for s in pool if low in (s["name"] or "").lower()]
    hits.sort(key=lambda s: (
        not (s["name"] or "").lower().startswith(q.lower()),  # 접두어 일치 우선
        len(s["name"] or ""),
        s["name"] or "",
    ))
    return [{k: s[k] for k in ("code", "name", "market", "close")} for s in hits[:12]]
