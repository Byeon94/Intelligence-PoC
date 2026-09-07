"""여신·심사 > 기업분석 > 리포트: 종목별 증권사 리포트 + 목표주가 컨센서스.

소스: 한경컨센서스 (consensus.hankyung.com/analysis/list) — 6자리 종목코드로 검색.
  컬럼: 발간일 · 제목 · 목표주가 · 투자의견 · 애널리스트 · 증권사 · PDF(report_idx)
  · 목표주가 '변동'(상향/하향/유지)은 같은 증권사의 직전 목표주가와 비교해 계산.
  · 컨센서스 요약(평균/최저/최고 목표주가, 리포트·증권사 수)은 리스트에서 집계.
시계열 컨센서스 밴드는 무료 소스가 없어, 주가(data.go.kr) + 평균 목표주가 라인으로 근사.
"""
from __future__ import annotations

import html as _html
import logging
import re
from datetime import date, timedelta

import requests

from capital._cache import ttl_cache

from .equity import _daily_rows

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


def _price_series(code: str, points: int = 26) -> list[dict]:
    try:
        rows = _daily_rows(code, 220)
    except Exception:  # noqa: BLE001
        return []
    rows = rows[-min(len(rows), 130):]
    if not rows:
        return []
    step = max(1, len(rows) // points)
    from capital._datago import pick, to_float
    out = []
    for r in rows[::step]:
        d = str(pick(r, "basDt", "BAS_DT") or "")
        c = to_float(pick(r, "clpr", "CLPR"))
        if len(d) == 8 and c is not None:
            out.append({"label": f"{d[2:4]}.{d[4:6]}", "close": c})
    return out


@ttl_cache(60 * 60)
def get_reports(code: str, limit: int = 40) -> dict:
    edate = date.today().strftime("%Y-%m-%d")
    sdate = (date.today() - timedelta(days=420)).strftime("%Y-%m-%d")

    items: list[dict] = []
    try:
        for page in range(1, 5):
            batch = _fetch_rows(code, page, sdate, edate)
            if not batch:
                break
            items.extend(batch)
            if len(items) >= limit:
                break
    except requests.RequestException as exc:
        logger.info("한경컨센서스 조회 실패(%s): %s", code, exc)
        return {"code": code, "reports": [], "consensus": None, "price_series": [],
                "source": "none", "note": "리포트를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."}

    items = items[:limit]
    if not items:
        return {"code": code, "reports": [], "consensus": None, "price_series": [],
                "source": "live", "note": "최근 증권사 리포트가 없습니다."}

    _mark_changes(items)
    items.sort(key=lambda x: x["date"], reverse=True)

    targets = [it["target"] for it in items[:24] if it["target"]]
    brokers = {it["broker"] for it in items[:24] if it["broker"] and it["target"]}
    op_counts: dict[str, int] = {}
    for it in items[:24]:
        if it["opinion"]:
            op_counts[it["opinion"]] = op_counts.get(it["opinion"], 0) + 1

    consensus = None
    if targets:
        consensus = {
            "avg": round(sum(targets) / len(targets)),
            "low": min(targets),
            "high": max(targets),
            "n_reports": len(targets),
            "n_brokers": len(brokers),
            "opinions": op_counts,
        }

    return {
        "code": code,
        "reports": items,
        "consensus": consensus,
        "price_series": _price_series(code),
        "source": "live",
    }
