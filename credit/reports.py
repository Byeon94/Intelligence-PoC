"""여신·심사 > 기업분석 > 리포트: 종목별 증권사 리포트 + 목표주가 컨센서스.

소스: 한경컨센서스 (consensus.hankyung.com/analysis/list) — 6자리 종목코드로 검색.
  컬럼: 발간일 · 제목 · 목표주가 · 투자의견 · 애널리스트 · 증권사 · PDF(report_idx)
  · 목표주가 '변동'(상향/하향/유지)은 같은 증권사의 직전 목표주가와 비교해 계산.
  · 컨센서스 요약(평균/최저/최고 목표주가, 리포트·증권사 수)은 리스트에서 집계.
당해 연도 리포트만, 최신 20건.
"""
from __future__ import annotations

import html as _html
import logging
import re
from datetime import date

import requests

from capital._cache import ttl_cache

logger = logging.getLogger(__name__)

_LIST_URL = "https://consensus.hankyung.com/analysis/list"
_PDF_BASE = "https://consensus.hankyung.com"
_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://consensus.hankyung.com/"}

_OPINION_MAP = {
    "strong buy": "Strong Buy", "buy": "Buy", "매수": "Buy", "적극매수": "Strong Buy",
    "outperform": "Buy", "overweight": "Buy",
    "hold": "Hold", "중립": "Hold", "neutral": "Hold", "marketperform": "Hold",
    "sell": "Sell", "매도": "Sell", "reduce": "Sell", "underweight": "Sell",
}


def _norm_opinion(raw: str) -> str | None:
    key = (raw or "").strip().lower()
    if not key or key in ("n/a", "투자의견없음", "-", "na"):
        return None
    return _OPINION_MAP.get(key, raw.strip())


def _fetch_rows(code: str, page: int, sdate: str, edate: str) -> list[dict]:
    resp = requests.get(_LIST_URL, params={
        "sdate": sdate, "edate": edate, "report_type": "CO",
        "order_type": "", "now_page": page, "search_text": code,
    }, headers=_HEADERS, timeout=12)
    resp.raise_for_status()
    t = resp.text
    i, j = t.find("<tbody>"), t.find("</tbody>")
    if i < 0:
        return []
    out: list[dict] = []
    for r in re.split(r"(?=<tr)", t[i:j]):
        if "<td" not in r:
            continue
        bc = re.search(r"business_code=(\d{6})", r)
        if not bc or bc.group(1) != code:          # '삼성전자' 언급된 타 종목 리포트 제외
            continue
        tds = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
        if len(tds) < 6:
            continue
        strip = lambda s: _html.unescape(re.sub(r"<[^>]+>", "", s)).strip()
        a = re.search(r'<a href="(/analysis/downpdf\?report_idx=\d+)"[^>]*>(.*?)</a>', tds[1], re.S)
        pdf = _PDF_BASE + a.group(1) if a else None
        title = strip(a.group(2)) if a else strip(tds[1])
        title = re.sub(r"^\S+\(\d{6}\)\s*", "", title)   # '삼성전자(005930) ' 접두 제거
        tp = strip(tds[2]).replace(",", "")
        try:
            target = int(tp) or None
        except ValueError:
            target = None
        out.append({
            "date": strip(tds[0]),
            "title": title,
            "target": target,
            "opinion": _norm_opinion(strip(tds[3])),
            "analyst": strip(tds[4]) or None,
            "broker": strip(tds[5]) or None,
            "url": pdf,
        })
    return out


def _mark_changes(items: list[dict]) -> None:
    """items 를 발간일 오름차순으로 훑어 증권사별 직전 목표주가 대비 상향/하향/유지 표시."""
    last: dict[str, int] = {}
    for it in sorted(items, key=lambda x: x["date"]):
        b, tp = it.get("broker"), it.get("target")
        if not b or not tp:
            it["change"] = None
            continue
        prev = last.get(b)
        it["change"] = ("up" if tp > prev else "down" if tp < prev else "flat") if prev else "new"
        last[b] = tp


@ttl_cache(60 * 60)
def get_reports(code: str, limit: int = 20) -> dict:
    year = date.today().year
    sdate = f"{year}-01-01"
    edate = date.today().strftime("%Y-%m-%d")

    items: list[dict] = []
    try:
        for page in range(1, 6):
            batch = _fetch_rows(code, page, sdate, edate)
            if not batch:
                break
            items.extend(batch)
            if len(items) >= 100:
                break
    except requests.RequestException as exc:
        logger.info("한경컨센서스 조회 실패(%s): %s", code, exc)
        return {"code": code, "year": str(year), "reports": [], "consensus": None,
                "source": "none", "note": "리포트를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."}

    items = [it for it in items if it["date"][:4] == str(year)]   # 당해 연도만
    if not items:
        return {"code": code, "year": str(year), "reports": [], "consensus": None,
                "source": "live", "note": f"{year}년 발간된 증권사 리포트가 없습니다."}

    _mark_changes(items)
    items.sort(key=lambda x: x["date"], reverse=True)

    # 컨센서스: 당해 연도에 목표주가를 제시한 '증권사별 최신 리포트 1건'의 평균/최저/최고
    latest_by_broker: dict[str, dict] = {}
    for it in items:                       # items 는 최신순 → 각 증권사 첫 등장 = 최신
        if it["target"] and it["broker"] and it["broker"] not in latest_by_broker:
            latest_by_broker[it["broker"]] = it
    targets = [it["target"] for it in latest_by_broker.values()]

    op_counts: dict[str, int] = {}
    for it in items:
        if it["opinion"]:
            op_counts[it["opinion"]] = op_counts.get(it["opinion"], 0) + 1

    consensus = None
    if targets:
        consensus = {
            "avg": round(sum(targets) / len(targets)),
            "low": min(targets),
            "high": max(targets),
            "n_brokers": len(targets),      # 평균에 들어간 증권사(값) 수
            "n_reports": len(items),         # 당해 연도 전체 리포트 수
            "opinions": op_counts,
        }

    return {
        "code": code,
        "year": str(year),
        "reports": items[:limit],
        "consensus": consensus,
        "source": "live",
    }
