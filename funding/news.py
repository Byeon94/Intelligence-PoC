"""단기자금 탭 — 원화/외화 주제별 관련 뉴스 3건 추천.

네이버 뉴스에서 주제 키워드로 최근 2일 기사를 모으고(main.naver_news), Gemini 가 주제와
가장 관련 깊은 3건을 골라 한 줄 이유를 붙인다. AI 를 못 쓰면(키 없음·한도·실패) 최신순 3건으로
대신 보여준다. 하루 1회 스냅샷(funding_news_snapshots, 원화·외화를 한 행에), 07:00 아침 배치에서
rebuild=True 로 다시 만든다(01:00 엔 당일 기사가 거의 없음).
"""
from __future__ import annotations

import logging
from datetime import timedelta

from main.daily_snapshot import AI_OK, parse_json_obj, table_lock, try_ai
from main.gemini import generate_text
from main.naver_news import NewsFetchError, collect
from main.snapshot_store import get_snapshot, save_snapshot
from main.utils import stamp, today_iso, today_kst

logger = logging.getLogger(__name__)

_TABLE = "funding_news_snapshots"
_PICK = 3
_MAX_CANDIDATES = 40

TOPICS = {
    "won": {
        "keywords": ["단기자금시장", "콜금리", "CD금리", "CP금리", "전단채", "MMF 자금", "RP 매각"],
        "desc": "원화 단기자금시장(콜·RP·CD·CP·전단채·MMF·통안채 단기물, 증권사·금융기관 단기조달)",
    },
    "fx": {
        "keywords": ["외환스왑", "외화자금시장", "달러 유동성", "외화 조달", "원달러 환율 마감", "한미 금리차"],
        "desc": "외화자금시장(원/달러 환율, FX스왑·CRS, 달러 유동성, 금융기관 외화조달, 한·미 금리차)",
    },
}


def _candidates(topic: str) -> list[dict]:
    cutoff = (today_kst() - timedelta(days=2)).isoformat()
    pool = collect(TOPICS[topic]["keywords"], display=15, cutoff_date=cutoff)
    pool.sort(key=lambda x: x["published"], reverse=True)
    return [{"title": it["title"], "url": it["url"], "published": it["published"],
             "summary": it["summary"][:120]} for it in pool[:_MAX_CANDIDATES]]


def _pick_with_ai(topic: str, part: dict) -> None:
    """try_ai 콜백 — 후보 중 3건 선택 + 이유. 전부 만든 뒤 한 번에 대입."""
    cands = part["candidates"]
    listing = "\n".join(f"{i}. [{c['published']}] {c['title']} — {c['summary']}" for i, c in enumerate(cands))
    raw = generate_text(
        f"주제: {TOPICS[topic]['desc']}\n\n후보 기사:\n{listing}\n\n"
        f"이 주제와 가장 관련 깊고 한국증권금융 단기자금 담당자에게 유용한 기사 {_PICK}건을 골라라. "
        "같은 사건을 다룬 기사는 1건만. 각 기사에 관련 이유를 25자 이내로 붙여라. "
        '반드시 JSON으로만: {"picks": [{"idx": 0, "reason": "..."}]}',
        max_output_tokens=2048,   # thinking 토큰도 이 예산을 써서 1024면 JSON 이 잘리곤 했다
    )
    items, used = [], set()
    for p in parse_json_obj(raw).get("picks") or []:
        try:
            idx = int(p.get("idx"))
        except (TypeError, ValueError, AttributeError):
            continue
        if 0 <= idx < len(cands) and idx not in used:
            used.add(idx)
            reason = p.get("reason") if isinstance(p.get("reason"), str) else ""
            items.append({**cands[idx], "reason": reason.strip()})
        if len(items) >= _PICK:
            break
    if not items:
        raise ValueError("선별 결과 없음")
    part.update(items=items, picked_by="ai")


def _select(topic: str, part: dict) -> bool:
    """AI 선별 1회 시도(상한은 try_ai) — 실패하면 최신순 3건으로 채운다. 변경 여부를 돌려준다."""
    before = part.get("gemini_attempts", 0)
    if try_ai(part, lambda p: _pick_with_ai(topic, p), f"단기자금 뉴스({topic})") != AI_OK and not part.get("items"):
        part.update(items=[{**c, "reason": ""} for c in part["candidates"][:_PICK]], picked_by="latest")
    return part.get("gemini_attempts", 0) != before


def _build(topic: str) -> dict:
    """주제 1개 — 후보 수집 → AI 선별(실패 시 최신순). 네이버 전면 장애면 NewsFetchError."""
    part = {"candidates": _candidates(topic), "items": [], "picked_by": None, "gemini_attempts": 0}
    if part["candidates"]:
        _select(topic, part)
    return part


def get_funding_news(rebuild: bool = False) -> dict:
    today = today_iso()
    with table_lock(_TABLE):
        snap = get_snapshot(_TABLE, today)
        if snap is None or rebuild:
            fresh = {"generated_at": stamp()}
            for topic in TOPICS:
                try:
                    fresh[topic] = _build(topic)
                except NewsFetchError as exc:
                    logger.warning("단기자금 뉴스(%s) 수집 실패: %s", topic, exc)
                    # 아침 재생성 실패 시 새벽 결과 유지, 첫 수집 실패면 빈 목록(저장하지 않음)
                    fresh[topic] = (snap or {}).get(topic) or {"items": [], "picked_by": None}
            if any(fresh[t].get("items") for t in TOPICS):
                save_snapshot(_TABLE, today, fresh)
            snap = fresh
        else:
            # 앞서 AI 선별이 실패해 최신순으로 대체된 주제는 상한 안에서 다시 선별해 본다.
            changed = False
            for topic in TOPICS:
                part = snap.get(topic) or {}
                if part.get("picked_by") == "latest" and part.get("candidates"):
                    changed = _select(topic, part) or changed   # 시도 횟수가 바뀌었으면 저장
            if changed:
                save_snapshot(_TABLE, today, snap)
    return {
        "generated_at": snap.get("generated_at"),
        **{t: {"items": (snap.get(t) or {}).get("items") or [],
               "picked_by": (snap.get(t) or {}).get("picked_by")} for t in TOPICS},
    }
