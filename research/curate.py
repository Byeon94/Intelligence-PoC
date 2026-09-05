"""리서치/뉴스 탭 — 당일 후보 기사에서 AI가 10건 선별 + 부서/업무 태그 + 브리핑.

- Naver 뉴스 수집(research.sources)은 하루 1회, 스냅샷을 DB에 저장.
- 큐레이션(Gemini)도 스냅샷당 1회. 재생성 버튼은 저장된 후보 풀로 다시 선별.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from main.config import get_settings
from main.snapshot_store import get_snapshot, latest_snapshot, save_snapshot

from .sources import collect_candidates

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")
_TABLE = "research_snapshots"
_N = 10

TAGS = [
    "증권담보/신용공여", "증권대차", "수탁", "유통금융/자금조달", "우리사주",
    "투자자예탁금", "디지털/AI", "자본시장/제도", "리스크/심사", "일반",
]

_SYSTEM_PROMPT = (
    "너는 한국증권금융(KSFC) 임직원을 위한 뉴스 큐레이터야. "
    "한국증권금융은 증권담보대출·신용공여, 증권대차, 우리사주 취득자금 대출, 투자자예탁금 운용, "
    "수탁, 유통금융(증권시장 자금공급), 단기금융을 담당하는 기관이다.\n"
    "아래 후보 기사 중 KSFC 업무와 관련성이 높은 순으로 정확히 10건을 골라라.\n"
    f"각 기사에 다음 태그 중 하나를 붙여라: {', '.join(TAGS)}.\n"
    "그리고 오늘 가장 주목할 흐름을 불릿 3개로 요약한 briefing 을 작성해라 "
    "(각 불릿 '- ' 시작, 한 문장, KSFC 업무 시사점 포함).\n"
    "반드시 아래 JSON 형식 텍스트만 출력해. 코드블록·설명 금지.\n"
    '{"briefing": ["...", "...", "..."], '
    '"picks": [{"idx": <후보번호>, "tag": "<태그>", "reason": "<관련성 한 문장>"}]}'
)


def _today() -> str:
    return datetime.now(KST).date().isoformat()


def _gemini_curate(candidates: list[dict]) -> dict:
    from google.genai import Client
    from google.genai import errors as genai_errors

    s = get_settings()
    keys = [k for k in (s.gemini_api_key, s.gemini_api_key_2) if k]
    if not keys:
        raise RuntimeError("GEMINI_API_KEY 미설정")
    clients = [Client(api_key=k) for k in keys]

    listing = "\n".join(
        f"{i}. [{c['published']}] {c['title']} — {c['summary'][:120]}"
        for i, c in enumerate(candidates[:60])
    )
    contents = f"후보 기사 목록:\n\n{listing}\n\n위에서 10건을 선별해 JSON으로 답해줘."

    last_err: Exception | None = None
    for i, client in enumerate(clients):
        try:
            resp = client.models.generate_content(
                model=s.gemini_model,
                config={
                    "system_instruction": _SYSTEM_PROMPT,
                    "thinking_config": {"thinking_budget": 0},
                    "max_output_tokens": 2048,
                },
                contents=contents,
            )
            return _parse(resp.text or "")
        except genai_errors.APIError as exc:
            last_err = exc
            if getattr(exc, "code", None) == 429 and i < len(clients) - 1:
                continue
            raise
    raise last_err or RuntimeError("큐레이션 실패")


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


def _apply_curation(payload: dict) -> dict:
    """payload['candidates'] 에 Gemini 큐레이션을 적용해 articles/briefing 채움."""
    cands = payload.get("candidates") or []
    result = _gemini_curate(cands)

    articles = []
    for p in result.get("picks", [])[:_N]:
        try:
            c = cands[int(p["idx"])]
        except (ValueError, KeyError, IndexError, TypeError):
            continue
        tag = p.get("tag") if p.get("tag") in TAGS else "일반"
        articles.append({
            "title": c["title"],
            "url": c["url"],
            "source": c.get("keyword", ""),
            "published": c["published"],
            "tag": tag,
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
    if not (s.gemini_api_key or s.gemini_api_key_2):
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
        logger.warning("뉴스 큐레이션 실패: %s", exc)
        if not has:
            payload["briefing_note"] = "AI 선별에 실패했습니다. 잠시 후 재생성해주세요."
        return payload


def get_research_digest(force: bool = False) -> dict:
    today = _today()

    snap = get_snapshot(_TABLE, today)
    if snap is not None:
        before = (len(snap.get("articles") or []), snap.get("gemini_attempts", 0))
        snap = _maybe_curate(snap, force=force)
        if (len(snap.get("articles") or []), snap.get("gemini_attempts", 0)) != before:
            save_snapshot(_TABLE, today, snap)
        return {**snap, "cached": not force}

    try:
        candidates = collect_candidates()
    except RuntimeError as exc:  # 키 미설정 등
        stale = latest_snapshot(_TABLE)
        if stale:
            return {**stale, "cached": True, "stale": True}
        raise

    payload = {
        "date": today,
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
