"""여신 상속·증여 / 우리사주 뉴스 동향 공용 흐름 — 후보 수집 → Gemini 제목 관련도 판단.

inherit_news.py·esop_news.py 는 키워드와 시스템 프롬프트만 다르고 흐름은 같다:

    오늘 스냅샷 조회 → 없으면 후보 기사 수집 후 저장 → AI 판단이 안 됐으면
    시도 상한(main.daily_snapshot.try_ai) 안에서 1회 시도 → 결과 저장

- AI 판단이 끝나면 ai_done=True 로 저장한다 — "전부 무관 판정(빈 목록)"을 "아직 판단 전"으로
  오인해 매 요청마다 Gemini 를 다시 부르지 않도록.
- 네이버 검색이 통째로 실패하면(NewsFetchError) 빈 후보를 오늘 스냅샷으로 굳히지 않고,
  가장 최근 스냅샷을 stale 로 돌려준다(없으면 예외를 그대로 올림).
- Gemini 는 기사 '제목'만 보고 판단하며, 제목에 없는 사실을 지어내지 않도록 프롬프트로 제약한다.
"""
from __future__ import annotations

import logging
import re
from typing import Callable

from main.daily_snapshot import table_lock, try_ai
from main.gemini import generate_text
from main.naver_news import NewsFetchError, enrich_title
from main.snapshot_store import get_snapshot, latest_snapshot, save_snapshot
from main.utils import today_iso

logger = logging.getLogger(__name__)

_MAX_ITEMS = 15


def slim(article: dict) -> dict:
    """naver_news 기사 dict → 스냅샷 저장용(화면은 published 를 날짜만 표시한다)."""
    return {"title": article["title"], "url": article["url"], "published": article["published_date"]}


def filter_titles(candidates: list[dict], system_prompt: str) -> list[dict]:
    """번호 매긴 제목 목록을 Gemini 에 보내 관련 있다고 판단한 기사만 ai_note 와 함께 돌려준다.

    Gemini 호출 자체가 실패하면(네트워크·쿼터 등) 예외를 그대로 올린다 — 호출자(try_ai)가
    "전부 무관 판정"과 "호출 실패"를 구분해 실패일 때만 재시도하도록 하기 위함.
    잘린 제목 보완(enrich_title)은 통과한 소수(최대 15건)에만 한다.
    """
    if not candidates:
        return []
    listing = "\n".join(f"{i + 1}. {c['title']}" for i, c in enumerate(candidates))
    resp = generate_text(
        f"뉴스 제목 목록:\n{listing}",
        system_instruction=system_prompt,
        max_output_tokens=1024,
    )
    verdicts: dict[int, str] = {}
    for line in resp.splitlines():
        m = re.match(r"\s*(\d+)\.\s*(.+)", line)
        if m:
            verdicts[int(m.group(1))] = m.group(2).strip()

    picked = []
    for i, c in enumerate(candidates, 1):
        note = verdicts.get(i)
        if note and "관련 없음" not in note:
            picked.append({**c, "ai_note": note})
    return [enrich_title(it) for it in picked[:_MAX_ITEMS]]


def _judge(payload: dict, system_prompt: str) -> None:
    """try_ai 콜백 — 후보 제목을 판단해 items 와 ai_done 을 한 번에 채운다(실패 시 payload 불변)."""
    items = filter_titles(payload.get("candidates") or [], system_prompt)
    payload["items"], payload["ai_done"] = items, True


def daily_filtered_news(
    table: str,
    schema_v: int,
    collect: Callable[[], list[dict]],
    system_prompt: str,
    label: str,
    rebuild: bool = False,
) -> dict:
    """오늘자 스냅샷 기준 {"items": [...], "v": schema_v} (네이버 장애 시 이전 스냅샷 + stale).

    rebuild=True(07:00 아침 배치)면 오늘 스냅샷이 있어도 후보를 다시 모아 새로 판단한다 —
    02:00 배치엔 당일 기사가 거의 없기 때문. 재수집·판단이 실패하면 기존 스냅샷을 그대로 둔다.
    """
    today = today_iso()
    with table_lock(table):
        snap = get_snapshot(table, today)
        if snap is not None and snap.get("v") != schema_v:
            snap = None

        if snap is not None and rebuild:
            try:
                candidates = collect()
            except NewsFetchError as exc:
                logger.warning("%s 아침 재수집 실패 — 새벽 스냅샷 유지: %s", label, exc)
                return {"items": snap.get("items") or [], "v": schema_v}
            fresh = {"v": schema_v, "candidates": candidates, "items": [],
                     "ai_done": False, "gemini_attempts": 0}
            if candidates:   # 0건이면 새벽 결과를 빈 목록으로 덮지 않는다
                try_ai(fresh, lambda p: _judge(p, system_prompt), label)
            if fresh["ai_done"]:
                save_snapshot(table, today, fresh)
                snap = fresh
            return {"items": snap.get("items") or [], "v": schema_v}

        if snap is None:
            try:
                candidates = collect()
            except NewsFetchError as exc:
                logger.warning("%s 후보 수집 실패 — 오늘 스냅샷을 만들지 않음: %s", label, exc)
                stale = latest_snapshot(table)
                if stale is not None and stale.get("v") == schema_v:
                    return {"items": stale.get("items") or [], "v": schema_v, "stale": True}
                raise
            snap = {"v": schema_v, "candidates": candidates, "items": [],
                    "ai_done": not candidates, "gemini_attempts": 0}
            save_snapshot(table, today, snap)  # 후보 먼저 저장(재수집 방지, AI 판단은 아래에서)

        # ai_done 이 없는 이전 스냅샷은 items 유무로 판단 여부를 추정한다.
        done = snap.get("ai_done", bool(snap.get("items")))
        if not done:
            before = snap.get("gemini_attempts", 0)
            try_ai(snap, lambda p: _judge(p, system_prompt), label)
            if snap.get("gemini_attempts", 0) != before:
                save_snapshot(table, today, snap)

    return {"items": snap.get("items") or [], "v": schema_v}
