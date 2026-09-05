"""발행시장 다이제스트: 이번 달 캘린더 이벤트 + 동향 리스트 + AI 브리핑.

하루 1회 수집·생성하고 issuance_snapshots 스냅샷으로 재사용. force=True(재생성) 시 브리핑만 다시.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from main.config import get_settings
from main.snapshot_store import get_snapshot, latest_snapshot, save_snapshot

from .sources import collect_ipo, collect_rights

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")
_TABLE = "issuance_snapshots"

_SYSTEM_PROMPT = (
    "너는 한국증권금융(KSFC) 임직원을 위한 발행시장 브리핑 어시스턴트야. "
    "아래는 이번 달 IPO 수요예측·청약·상장 일정과 유상증자 공시 목록이다.\n"
    "KSFC 업무 관점에서 이번 달에 챙겨야 할 포인트를 불릿 3개로 정리해.\n"
    "- 각 불릿은 '- '로 시작, 60자 이내 한 문장.\n"
    "- 예: 우리사주 배정 IPO의 취득자금 대출 수요, 청약일 집중에 따른 투자자예탁금·증거금 유입 변동, "
    "대형 IPO 상장일의 유통금융 수요, 유상증자에 따른 담보가치 영향 등.\n"
    "- 소제목·서두 없이 불릿 3개만."
)


def _today() -> str:
    return datetime.now(KST).date().isoformat()


def _month_label() -> str:
    d = datetime.now(KST)
    return f"{d.year}년 {d.month}월"


def _this_month_events(events: list[dict]) -> list[dict]:
    ym = datetime.now(KST).strftime("%Y-%m")
    seen = set()
    out = []
    for e in events:
        if not e.get("date", "").startswith(ym):
            continue
        k = (e["type"], e["company"], e["date"])
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    out.sort(key=lambda e: (e["date"], e["type"]))
    return out


def _briefing(events: list[dict]) -> list[str]:
    from google.genai import Client
    from google.genai import errors as genai_errors

    s = get_settings()
    keys = [k for k in (s.gemini_api_key, s.gemini_api_key_2) if k]
    if not keys:
        raise RuntimeError("GEMINI_API_KEY 미설정")

    lines = "\n".join(
        f"- {e['date']} [{e['type']}] {e['company']} {e.get('detail', '')}" for e in events
    )
    last_err: Exception | None = None
    for i, client in enumerate([Client(api_key=k) for k in keys]):
        try:
            resp = client.models.generate_content(
                model=s.gemini_model,
                config={"system_instruction": _SYSTEM_PROMPT,
                        "thinking_config": {"thinking_budget": 0},
                        "max_output_tokens": 600},
                contents=f"이번 달 발행시장 일정:\n\n{lines}\n\n브리핑 3줄을 작성해줘.",
            )
            txt = (resp.text or "").strip()
            bullets = [b.strip(" -•*") for b in txt.split("\n") if b.strip(" -•*")]
            if bullets:
                return bullets[:3]
            last_err = RuntimeError("빈 응답")
        except genai_errors.APIError as exc:
            last_err = exc
            if getattr(exc, "code", None) == 429 and i < len(keys) - 1:
                continue
            raise
    raise last_err or RuntimeError("브리핑 생성 실패")


_TREND_TYPES = ["수요예측", "청약", "상장", "유상증자"]


def _maybe_brief(payload: dict, force: bool = False) -> dict:
    s = get_settings()
    has = bool(payload.get("briefing"))
    cap = s.policy_max_gemini_calls_per_day
    if has and not force:
        return payload
    if not (s.gemini_api_key or s.gemini_api_key_2):
        if not has:
            payload["briefing_note"] = "AI 브리핑은 GEMINI_API_KEY 등록 후 제공됩니다."
        return payload
    if not payload.get("events"):
        payload["briefing_note"] = "이번 달 발행시장 일정이 없습니다."
        return payload
    if payload.get("gemini_attempts", 0) >= cap:
        payload["briefing_note"] = (
            f"AI 재생성 일일 한도({cap}회)에 도달했습니다."
            + (" 기존 브리핑을 표시합니다." if has else "")
        )
        return payload
    payload["gemini_attempts"] = payload.get("gemini_attempts", 0) + 1
    try:
        payload["briefing"] = _briefing(payload["events"])
        payload["briefing_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
        payload["briefing_note"] = None
    except Exception as exc:  # noqa: BLE001
        logger.warning("발행시장 브리핑 실패: %s", exc)
        if not has:
            payload["briefing_note"] = "AI 브리핑 생성에 실패했습니다."
    return payload


def get_issuance_digest(force: bool = False) -> dict:
    today = _today()
    snap = get_snapshot(_TABLE, today)
    if snap is not None:
        before = (bool(snap.get("briefing")), snap.get("gemini_attempts", 0))
        snap = _maybe_brief(snap, force=force)
        if (bool(snap.get("briefing")), snap.get("gemini_attempts", 0)) != before:
            save_snapshot(_TABLE, today, snap)
        return {**snap, "cached": not force}

    events = _this_month_events(collect_ipo() + collect_rights())
    if not events:
        stale = latest_snapshot(_TABLE)
        if stale:
            return {**stale, "cached": True, "stale": True}

    counts = {t: sum(1 for e in events if e["type"] == t) for t in _TREND_TYPES}
    payload = {
        "date": today,
        "month_label": _month_label(),
        "generated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "events": events,
        "counts": counts,
        "briefing": None,
        "briefing_at": None,
        "briefing_note": None,
        "gemini_attempts": 0,
    }
    save_snapshot(_TABLE, today, payload)
    payload = _maybe_brief(payload)
    save_snapshot(_TABLE, today, payload)
    return {**payload, "cached": False}
