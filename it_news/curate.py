"""전사 위젯 > 오늘의 IT·정보보호 뉴스 — AI가 당일 후보 기사에서 상위 건 선별 + 브리핑.

- Naver 뉴스 수집(it_news.sources)은 하루 1회, 스냅샷을 DB에 저장.
- 큐레이션(Gemini)도 스냅샷당 1회. 재생성 버튼은 저장된 후보 풀로 다시 선별.
- IT부 변OO 과장 제작.
"""
from __future__ import annotations

import html as _html
import json
import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from main.config import get_settings
from main.gemini import generate_text
from main.snapshot_store import get_snapshot, latest_snapshot, save_snapshot

from .sources import collect_candidates

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")
_TABLE = "it_news_snapshots"
_N = 5
_SCHEMA_V = 3  # v3: 네이버가 잘라 보내는 제목을 원문 og:title로 보완
CREDIT = "IT부 변OO 과장 제작"

_SYSTEM_PROMPT = (
    "너는 한국증권금융(KSFC) 임직원을 위한 IT·정보보호 뉴스 큐레이터야.\n"
    "아래 후보 기사 중 금융 IT·정보보호·AI·클라우드·빅데이터·UI/UX·생성형 AI·개발 트렌드·"
    "혁신금융서비스·블록체인·차세대 시스템과 관련성·중요도가 가장 높은 5건만 엄선해라.\n"
    "picks 배열은 관련성·중요도가 높은 순서로 정렬해라(1번이 가장 추천하는 기사).\n"
    "그리고 오늘 가장 주목할 흐름을 불릿 3개로 요약한 briefing 을 작성해라 "
    "(각 불릿 '- ' 시작, 한 문장, 업무 시사점 포함).\n"
    "반드시 아래 JSON 형식 텍스트만 출력해. 코드블록·설명 금지.\n"
    '{"briefing": ["...", "...", "..."], '
    '"picks": [{"idx": <후보번호>, "reason": "<관련성 한 문장>"}]}'
)


def _today() -> str:
    return datetime.now(KST).date().isoformat()


def _gemini_curate(candidates: list[dict]) -> dict:
    listing = "\n".join(
        f"{i}. [{c['published']}] ({c['keyword']}) {c['title']} — {c['summary'][:120]}"
        for i, c in enumerate(candidates[:60])
    )
    contents = f"후보 기사 목록:\n\n{listing}\n\n위에서 {_N}건을 선별해 JSON으로 답해줘."
    text = generate_text(contents, system_instruction=_SYSTEM_PROMPT, max_output_tokens=2048)
    return _parse(text)


def _parse(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[4:] if t[:4].lower() == "json" else t
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b < 0:
        raise ValueError("JSON 응답 없음")
    obj = json.loads(t[a : b + 1])
    if not obj.get("picks"):
        raise ValueError("picks 없음")
    return obj


_OG_TITLE_RE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']', re.I
)


def _full_title(url: str) -> str | None:
    """네이버 뉴스 검색 API는 긴 제목을 '...'로 잘라서 준다. 잘린 제목만 원문
    페이지의 og:title(보통 잘리지 않은 전체 제목)로 보완한다. 실패하면 None."""
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        resp.raise_for_status()
        m = _OG_TITLE_RE.search(resp.text)
        if not m:
            return None
        title = _html.unescape(m.group(1)).strip()
        title = re.sub(r"\s*\|\s*[^|]{1,20}$", "", title).strip()  # " | 언론사명" 접미사만 제거(하이픈은 헤드라인 자체에 흔해 건드리지 않음)
        return title or None
    except Exception:  # noqa: BLE001 - 원문 페이지 구조는 사이트마다 달라 실패는 흔함
        return None


def _apply_curation(payload: dict) -> dict:
    cands = payload.get("candidates") or []
    result = _gemini_curate(cands)

    articles = []
    for p in result.get("picks", [])[:_N]:
        try:
            c = cands[int(p["idx"])]
        except (ValueError, KeyError, IndexError, TypeError):
            continue
        title = c["title"]
        if title.endswith("...") or title.endswith("…"):
            title = _full_title(c["url"]) or title
        articles.append({
            "title": title,
            "url": c["url"],
            "keyword": c.get("keyword", ""),
            "published": c["published"],
            "reason": (p.get("reason") or "").strip(),
        })
    if not articles:
        raise ValueError("선별 결과 매핑 실패")

    payload["articles"] = articles
    payload["briefing"] = [b.strip(" -•*") for b in (result.get("briefing") or []) if b.strip()][:3]
    payload["briefing_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    payload["briefing_note"] = None
    return payload


def _maybe_curate(payload: dict, force: bool = False) -> dict:
    s = get_settings()
    has = bool(payload.get("articles"))
    cap = s.policy_max_gemini_calls_per_day

    if has and not force:
        return payload
    if not s.gemini_api_keys:
        if not has:
            payload["briefing_note"] = "AI 선별은 GEMINI_API_KEY 등록 후 제공됩니다."
        return payload
    if not payload.get("candidates"):
        payload["briefing_note"] = "오늘 수집된 관련 기사가 없습니다."
        return payload
    if payload.get("gemini_attempts", 0) >= cap:
        payload["briefing_note"] = (
            f"AI 재생성 일일 한도({cap}회)에 도달했습니다. " +
            ("기존 선별을 표시합니다." if has else "후보 목록만 표시합니다.")
        )
        return payload

    payload["gemini_attempts"] = payload.get("gemini_attempts", 0) + 1
    try:
        return _apply_curation(payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("IT·정보보호 뉴스 큐레이션 실패: %s", exc)
        if not has:
            payload["briefing_note"] = "AI 선별에 실패했습니다. 잠시 후 재생성해주세요."
        return payload


def get_it_news_digest(force: bool = False) -> dict:
    today = _today()

    snap = get_snapshot(_TABLE, today)
    if snap is not None and snap.get("v") != _SCHEMA_V:
        snap = None  # 스키마 변경(5건 선별로 축소) — 재수집
    if snap is not None:
        before = (len(snap.get("articles") or []), snap.get("gemini_attempts", 0))
        snap = _maybe_curate(snap, force=force)
        if (len(snap.get("articles") or []), snap.get("gemini_attempts", 0)) != before:
            save_snapshot(_TABLE, today, snap)
        return {**snap, "cached": not force}

    try:
        candidates = collect_candidates()
    except RuntimeError:
        stale = latest_snapshot(_TABLE)
        if stale:
            return {**stale, "cached": True, "stale": True}
        raise

    payload = {
        "v": _SCHEMA_V,
        "date": today,
        "credit": CREDIT,
        "generated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "candidates": candidates,
        "candidate_count": len(candidates),
        "articles": [],
        "briefing": None,
        "briefing_at": None,
        "briefing_note": None,
        "gemini_attempts": 0,
    }
    save_snapshot(_TABLE, today, payload)   # 수집 결과 먼저 저장 → 오늘 재수집 방지
    payload = _maybe_curate(payload)
    save_snapshot(_TABLE, today, payload)
    return {**payload, "cached": False}
