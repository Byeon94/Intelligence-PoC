"""여신 > 기업분석 > 리포트: 종목별 증권사 리포트 + 목표주가 컨센서스.
그리고 전사 위젯용 시장 전체 리포트 동향(get_market_report_digest).

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
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from capital._cache import ttl_cache
from main.config import get_settings
from main.gemini import generate_text
from main.snapshot_store import get_snapshot, save_snapshot

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

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
        "list_url": f"{_LIST_URL}?report_type=CO&search_text={code}",
        "source": "live",
    }


# ── 전사 위젯: 시장 전체 리포트 동향(종목 무관, 조회 기준일 전체) ────────────
_MARKET_TABLE = "market_report_snapshots"
_MARKET_MAX_PAGES = 8     # 하루치 페이지 상한(과도한 스크랩 방지) — 넘으면 total_capped=True
_MARKET_MAX_BACK_DAYS = 5  # 오늘부터 최대 이만큼 거슬러 올라가며 '전영업일' 탐색
_MARKET_SCHEMA_V = 3  # v3: category_counts(유형별 건수 집계) 추가

_MARKET_BRIEF_SYSTEM_PROMPT = (
    "너는 한국증권금융(KSFC) 임직원을 위한 증권사 리서치 리포트 브리핑 어시스턴트야.\n"
    "아래는 오늘(조회 기준일) 국내 증권사들이 발간한 리서치 리포트의 유형(시장/산업/기업/경제 등)·"
    "제목·증권사 목록이다.\n"
    "이 중 업무상 눈에 띄는 흐름(특정 업종·종목 쏠림, 여러 증권사가 다룬 공통 이슈, 주목할 "
    "이슈)을 불릿 3개로 정리해.\n"
    "- 각 불릿은 '- '로 시작, 70자 이내 한 문장. 소제목·서두 없이 불릿 3개만 출력."
)


def _fetch_market_rows(page: int, date_str: str) -> list[dict]:
    # report_type=""(전체): 기업(CO) 리포트만이 아니라 시장·산업·경제 등 그 날 발간된
    # 모든 리포트를 센다. 이 뷰는 CO 전용 목록과 테이블 컬럼 구성이 달라
    # (목표주가·투자의견 컬럼이 없음) 파싱도 별도로 한다.
    # 컬럼: [0]날짜 [1]유형(시장/산업/기업/경제…) [2]제목(PDF 링크) [3]애널리스트 [4]증권사 [5]첨부
    resp = requests.get(_LIST_URL, params={
        "sdate": date_str, "edate": date_str, "report_type": "",
        "order_type": "", "now_page": page,
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
        tds = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
        if len(tds) < 5:
            continue
        strip = lambda s: _html.unescape(re.sub(r"<[^>]+>", "", s)).strip()
        a = re.search(r'<a href="(/analysis/downpdf\?report_idx=\d+)"[^>]*>(.*?)</a>', tds[2], re.S)
        pdf = _PDF_BASE + a.group(1) if a else None
        title = strip(a.group(2)) if a else strip(tds[2])
        out.append({
            "date": strip(tds[0]),
            "category": strip(tds[1]) or None,
            "title": title,
            "broker": strip(tds[4]) or None,
            "url": pdf,
        })
    return out


def _find_market_reference_date() -> tuple[str, list[dict]]:
    """오늘부터 거슬러 올라가며 리포트가 실제로 있는 첫 날짜(=전영업일)를 찾는다."""
    d = datetime.now(KST).date()
    for _ in range(_MARKET_MAX_BACK_DAYS):
        ds = d.isoformat()
        rows = _fetch_market_rows(1, ds)
        if rows:
            return ds, rows
        d -= timedelta(days=1)
    return datetime.now(KST).date().isoformat(), []


def _market_briefing(items: list[dict]) -> list[str]:
    lines = "\n".join(
        f"- [{it.get('category') or ''}/{it.get('broker') or ''}] {it.get('title', '')}"
        for it in items[:60]
    )
    text = generate_text(
        f"오늘 발간된 증권사 리포트 목록:\n\n{lines}\n\n브리핑 3줄을 작성해줘.",
        system_instruction=_MARKET_BRIEF_SYSTEM_PROMPT,
        max_output_tokens=1200,
    )
    bullets = [b.strip(" -•*") for b in text.split("\n") if b.strip(" -•*")]
    if not bullets:
        raise RuntimeError("빈 응답")
    return bullets[:3]


def _maybe_brief_market(payload: dict, force: bool = False) -> dict:
    s = get_settings()
    has = bool(payload.get("briefing"))
    cap = s.policy_max_gemini_calls_per_day
    if has and not force:
        return payload
    if not s.gemini_api_keys:
        if not has:
            payload["briefing_note"] = "AI 브리핑은 GEMINI_API_KEY 등록 후 제공됩니다."
        return payload
    if not payload.get("items"):
        payload["briefing_note"] = "브리핑을 만들 리포트가 없습니다."
        return payload
    if payload.get("gemini_attempts", 0) >= cap:
        payload["briefing_note"] = (
            f"AI 재생성 일일 한도({cap}회)에 도달했습니다." + (" 기존 브리핑을 표시합니다." if has else "")
        )
        return payload
    payload["gemini_attempts"] = payload.get("gemini_attempts", 0) + 1
    try:
        payload["briefing"] = _market_briefing(payload["items"])
        payload["briefing_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
        payload["briefing_note"] = None
    except Exception as exc:  # noqa: BLE001
        logger.warning("시장 리포트 브리핑 실패: %s", exc)
        if not has:
            payload["briefing_note"] = "AI 브리핑 생성에 실패했습니다."
    return payload


def get_market_report_digest(force: bool = False) -> dict:
    """조회 기준일(비영업일이면 전영업일)의 시장 전체 증권사 리포트 건수 + AI 브리핑.

    특정 종목이 아니라 한경컨센서스 전체 목록(report_type="", 시장·산업·기업·경제 등 전 유형)
    기준. 하루 1회만 수집하고 스냅샷으로 재사용(force=True 인 재생성 버튼은 브리핑만 다시
    만든다). 브리핑은 노출용 상위 20건(items, 제목 중복 제거됨)을 근거로 생성한다(전체
    수백 건을 매번 다 실어 나르지 않기 위함). total 은 사이트에서 세는 값과 맞추기 위해
    중복 제거 전 원본 건수다.
    """
    today = datetime.now(KST).date().isoformat()
    snap = get_snapshot(_MARKET_TABLE, today)
    if snap is not None and snap.get("v") != _MARKET_SCHEMA_V:
        snap = None  # 스키마 변경(전체 유형 반영) — 재수집
    if snap is not None:
        before = (bool(snap.get("briefing")), snap.get("gemini_attempts", 0))
        snap = _maybe_brief_market(snap, force=force)
        if (bool(snap.get("briefing")), snap.get("gemini_attempts", 0)) != before:
            save_snapshot(_MARKET_TABLE, today, snap)
        return {**snap, "cached": not force}

    try:
        ref_date, first_page = _find_market_reference_date()
    except requests.RequestException as exc:
        logger.info("한경컨센서스 전체 조회 실패: %s", exc)
        return {"date": today, "as_of": None, "items": [], "total": 0, "total_capped": False,
                "briefing": None, "briefing_note": "리포트를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.",
                "list_url": _LIST_URL, "source": "none"}

    items = list(first_page)
    capped = False
    if items:
        for page in range(2, _MARKET_MAX_PAGES + 1):
            batch = _fetch_market_rows(page, ref_date)
            if not batch:
                break
            items.extend(batch)
        else:
            capped = True  # for-else: 상한까지 다 돌았는데도 빈 페이지를 못 만남

    # 표시/브리핑용은 제목 중복을 제거(원본 목록에 같은 리포트가 중복 게재되는 경우가 있음).
    # '총 건수'는 실제 사이트에서 세는 값과 맞추기 위해 중복 제거 전 원본 건수를 쓴다.
    seen_titles: set[str] = set()
    deduped: list[dict] = []
    for it in items:
        key = (it.get("title") or "").strip()
        if key and key in seen_titles:
            continue
        if key:
            seen_titles.add(key)
        deduped.append(it)

    # 건수 옆에 "27건(기업 18·산업 5·시장 3·경제 1)"처럼 바로 보여줄 수 있게, AI 호출
    # 없이 이미 파싱해둔 category 필드만으로 집계한다(total과 합이 맞도록 dedup 전
    # 원본 items 기준 — total도 같은 기준).
    category_counts: dict[str, int] = {}
    for it in items:
        cat = it.get("category") or "기타"
        category_counts[cat] = category_counts.get(cat, 0) + 1

    payload = {
        "v": _MARKET_SCHEMA_V,
        "date": today,
        "as_of": ref_date,
        "items": deduped[:20],
        "total": len(items),
        "total_capped": capped,
        "category_counts": category_counts,
        "generated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "briefing": None,
        "briefing_at": None,
        "briefing_note": None,
        "gemini_attempts": 0,
        "list_url": f"{_LIST_URL}?sdate={ref_date}&edate={ref_date}",
        "source": "live" if items else "none",
    }
    if not items:
        payload["briefing_note"] = "최근 발간된 리포트가 없습니다."
    save_snapshot(_MARKET_TABLE, today, payload)
    payload = _maybe_brief_market(payload)
    save_snapshot(_MARKET_TABLE, today, payload)
    return {**payload, "cached": False}
