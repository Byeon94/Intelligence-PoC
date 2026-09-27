"""전사 위젯 > 오늘의 IT·정보보호 뉴스 — AI가 당일 후보 기사에서 5건 선별 + 브리핑.

흐름(테이블 락 안에서 한 번에): 오늘 스냅샷 조회 → 없거나 구버전이면 Naver 뉴스 후보 수집
(it_news.sources) 후 저장 → 선별 결과가 없으면 Gemini 큐레이션을 스냅샷당 시도 상한 안에서
1회 시도(선별된 기사 중 '...'로 잘린 제목은 원문 og:title 로 보완) → 저장.
Naver 장애·후보 0건이면 빈 스냅샷을 굳히지 않고 직전 스냅샷(stale)을 돌려준다.
- IT부 변OO 과장 제작.
"""
from __future__ import annotations

import time

from main.config import get_settings
from main.daily_snapshot import (
    AI_CAPPED, AI_FAILED, AI_NO_KEY, parse_json_obj, table_lock, try_ai,
)
from main.gemini import generate_text
from main.naver_news import NewsFetchError, enrich_title
from main.snapshot_store import get_snapshot, latest_snapshot, save_snapshot
from main.utils import stamp, today_iso

from .sources import collect_candidates

_TABLE = "it_news_snapshots"
_N = 5
_MAX_CANDIDATES = 60    # Gemini 프롬프트에 넣는 후보 수(idx 유효 범위)
_SCHEMA_V = 4  # v4: 검색 키워드 '차세대'→'금융 차세대', '한국증권금융' 추가(오늘자 재수집)
_RETRY_AFTER = 600      # 수집 실패 후 재수집까지 대기(초) — 요청마다 Naver 를 두드리지 않게
_fail_at = 0.0          # 마지막 수집 실패 시각(time.monotonic), 락 안에서만 갱신
_fail_exc: Exception | None = None  # 그때의 예외(0건이면 None)
CREDIT = "IT부 변OO 과장 제작"

_SYSTEM_PROMPT = (
    "너는 한국증권금융(KSFC) 임직원을 위한 IT·정보보호 뉴스 큐레이터야.\n"
    "아래 후보 기사 중 금융 IT·정보보호·AI·클라우드·빅데이터·UI/UX·생성형 AI·개발 트렌드·"
    "혁신금융서비스·블록체인·금융권 차세대 시스템·한국증권금융과 관련성·중요도가 가장 높은 "
    "5건만 엄선해라. 검색 키워드와 우연히 겹칠 뿐 주제와 무관한 기사(예: 자동차·가전 등 "
    "비금융권 '차세대' 제품 기사)는 제외해라.\n"
    "picks 배열은 관련성·중요도가 높은 순서로 정렬해라(1번이 가장 추천하는 기사).\n"
    "그리고 오늘 가장 주목할 흐름을 불릿 3개로 요약한 briefing 을 작성해라 "
    "(각 불릿 '- ' 시작, 한 문장, 업무 시사점 포함).\n"
    "반드시 아래 JSON 형식 텍스트만 출력해. 코드블록·설명 금지.\n"
    '{"briefing": ["...", "...", "..."], '
    '"picks": [{"idx": <후보번호>, "reason": "<관련성 한 문장>"}]}'
)


def _gemini_curate(candidates: list[dict]) -> dict:
    listing = "\n".join(
        f"{i}. [{c['published']}] ({c['keyword']}) {c['title']} — {c['summary'][:120]}"
        for i, c in enumerate(candidates[:_MAX_CANDIDATES])
    )
    contents = f"후보 기사 목록:\n\n{listing}\n\n위에서 {_N}건을 선별해 JSON으로 답해줘."
    text = generate_text(contents, system_instruction=_SYSTEM_PROMPT, max_output_tokens=2048)
    return parse_json_obj(text)


def _text(v) -> str:
    return v.strip() if isinstance(v, str) else ""


def _bullets(raw) -> list[str]:
    """briefing 응답(보통 문자열 리스트, 가끔 문자열 하나) → 불릿 최대 3개."""
    if isinstance(raw, str):
        raw = raw.splitlines()
    if not isinstance(raw, list):
        return []
    return [b for b in (_text(x).strip(" -•*") for x in raw) if b][:3]


def _apply_curation(payload: dict) -> None:
    """payload['candidates'] 에 Gemini 큐레이션을 적용해 articles/briefing 채움.

    idx 는 프롬프트에 보인 범위(0 ~ 후보 수-1)만 인정하고 중복은 버린다.
    결과를 전부 만든 뒤 마지막에 한 번에 대입한다(실패 시 payload 불변).
    """
    cands = (payload.get("candidates") or [])[:_MAX_CANDIDATES]
    result = _gemini_curate(cands)
    picks = result.get("picks")
    if not isinstance(picks, list) or not picks:
        raise ValueError("picks 없음")

    articles: list[dict] = []
    used: set[int] = set()
    for p in picks:
        if len(articles) >= _N:
            break
        if not isinstance(p, dict):
            continue
        try:
            idx = int(p.get("idx"))
        except (TypeError, ValueError):
            continue
        if not 0 <= idx < len(cands) or idx in used:
            continue
        used.add(idx)
        c = enrich_title(cands[idx])   # 검색 API가 '...'로 자른 제목만 원문 제목으로 보완
        articles.append({
            "title": c["title"],
            "url": c["url"],
            "keyword": c.get("keyword", ""),
            "published": c["published"],
            "reason": _text(p.get("reason")),
        })
    if not articles:
        raise ValueError("선별 결과 매핑 실패")

    payload.update(
        articles=articles,
        briefing=_bullets(result.get("briefing")),
        briefing_at=stamp(),
        briefing_note=None,
    )


def _maybe_curate(payload: dict) -> None:
    """선별 결과가 없으면 상한 안에서 1회 시도하고, 결과에 맞는 안내문을 남긴다."""
    if payload.get("articles"):
        return
    if not payload.get("candidates"):
        payload["briefing_note"] = "오늘 수집된 관련 기사가 없습니다."
        return
    status = try_ai(payload, _apply_curation, "IT·정보보호 뉴스 큐레이션")
    if status == AI_NO_KEY:
        payload["briefing_note"] = "AI 선별은 GEMINI_API_KEY 등록 후 제공됩니다."
    elif status == AI_CAPPED:
        cap = get_settings().ai_retries_per_snapshot
        payload["briefing_note"] = f"AI 재생성 일일 한도({cap}회)에 도달했습니다. 후보 목록만 표시합니다."
    elif status == AI_FAILED:
        payload["briefing_note"] = "AI 선별에 실패했습니다. 잠시 후 재생성해주세요."


def _fallback(today: str, exc: Exception | None) -> dict:
    """오늘 스냅샷을 만들 수 없을 때: 직전 스냅샷(stale) → 없으면 exc 를 올리거나(장애) 빈 결과(0건)."""
    stale = latest_snapshot(_TABLE)
    if stale:
        return {**stale, "cached": True, "stale": True}
    if exc is not None:
        raise exc
    return {"date": today, "credit": CREDIT, "generated_at": stamp(), "articles": [],
            "candidate_count": 0, "briefing": None,
            "briefing_note": "오늘 수집된 관련 기사가 없습니다.", "cached": False}


def get_it_news_digest(rebuild: bool = False) -> dict:
    """rebuild=True(07:00 아침 배치)면 오늘 스냅샷이 있어도 후보를 다시 수집해 새로 선별한다
    — 05:00 배치에는 당일 기사가 거의 없기 때문. 재수집·선별이 실패하면 기존 스냅샷을 그대로 둔다."""
    global _fail_at, _fail_exc
    with table_lock(_TABLE):
        today = today_iso()
        snap = get_snapshot(_TABLE, today)
        if snap is not None and snap.get("v") != _SCHEMA_V:
            snap = None  # 구버전 스냅샷(키워드·구조 변경 전) → 오늘자 재수집
        if snap is not None and not rebuild:
            before = snap.get("gemini_attempts", 0)
            _maybe_curate(snap)
            if snap.get("gemini_attempts", 0) != before:
                save_snapshot(_TABLE, today, snap)
            return {**snap, "cached": True}

        if snap is None and _fail_at and time.monotonic() - _fail_at < _RETRY_AFTER:
            return _fallback(today, _fail_exc)
        try:
            candidates = collect_candidates()
            exc = None
        except NewsFetchError as e:   # 키 미설정·전 키워드 실패
            candidates, exc = [], e
        if not candidates and snap is not None:
            return {**snap, "cached": True}   # 아침 재수집 실패 → 새벽 스냅샷 유지
        if not candidates:
            # 빈 스냅샷을 오늘자로 굳히면 이후 기사가 올라와도 하루 종일 비므로 저장하지 않는다.
            _fail_at, _fail_exc = time.monotonic(), exc
            return _fallback(today, exc)
        _fail_at, _fail_exc = 0.0, None

        payload = {
            "v": _SCHEMA_V,
            "date": today,
            "credit": CREDIT,
            "generated_at": stamp(),
            "candidates": candidates,
            "candidate_count": len(candidates),
            "articles": [],
            "briefing": None,
            "briefing_at": None,
            "briefing_note": None,
            "gemini_attempts": 0,
        }
        if snap is not None:
            # 아침 재생성: 선별까지 성공했을 때만 교체(실패하면 새벽 결과를 계속 보여준다).
            _maybe_curate(payload)
            if payload.get("articles"):
                save_snapshot(_TABLE, today, payload)
                return {**payload, "cached": False}
            return {**snap, "cached": True}
        save_snapshot(_TABLE, today, payload)   # 수집 결과 먼저 저장 → 오늘 재수집 방지
        _maybe_curate(payload)
        save_snapshot(_TABLE, today, payload)
        return {**payload, "cached": False}
