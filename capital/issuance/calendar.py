"""자본시장 > 발행시장 다이제스트: 이번 달 캘린더 이벤트 + 유형별 건수 + AI 브리핑.

하루 1회 수집해 issuance_snapshots 에 저장하고 재사용한다(일정이 하나도 없어도 저장 —
그래야 화면을 열 때마다 38.co.kr·DART 를 다시 긁지 않는다). 일정이 없는 날은 직전
자료(fallback)를 "이전 자료"로 보여준다.

일부 소스가 실패하면(failed_sources) 그 결과를 하루 종일 고정하지 않고 _RETRY_AFTER 뒤
다음 요청에서 다시 수집한다. AI 브리핑은 새벽 배치(/internal/warmup)에서 만들지만, 배치
전에 화면 요청이 먼저 오면 그 요청이 생성할 수 있다 — table_lock 으로 동시 요청의 중복
수집·Gemini 호출을 막고, try_ai 가 스냅샷당 시도 상한을 지킨다.
force=True(재생성)는 수집은 그대로 두고 브리핑만 다시 만든다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from main.config import get_settings
from main.daily_snapshot import AI_CAPPED, AI_FAILED, table_lock, try_ai
from main.gemini import generate_text
from main.snapshot_store import get_snapshot, latest_snapshot, save_snapshot
from main.utils import now_kst, stamp, today_iso

from .sources import collect_ipo, collect_rights

logger = logging.getLogger(__name__)
_TABLE = "issuance_snapshots"
_RETRY_AFTER = timedelta(minutes=30)   # 소스 일부 실패 시 재수집 간격
_TREND_TYPES = ["수요예측", "청약", "상장", "유상증자"]
# 일정이 없는 날 대신 보여줄 직전 자료에서 화면이 쓰는 필드만 남긴다
_FALLBACK_KEYS = ["date", "month_label", "generated_at", "events", "counts",
                  "briefing", "briefing_at", "briefing_note"]

_SYSTEM_PROMPT = (
    "너는 한국증권금융(KSFC) 임직원을 위한 발행시장 브리핑 어시스턴트야. "
    "아래는 이번 달 IPO 수요예측·청약·상장 일정과 유상증자 공시 목록이다.\n"
    "KSFC 업무 관점에서 이번 달에 챙겨야 할 포인트를 불릿 3개로 정리해.\n"
    "- 각 불릿은 '- '로 시작, 60자 이내 한 문장.\n"
    "- 예: 우리사주 배정 IPO의 취득자금 대출 수요, 청약일 집중에 따른 투자자예탁금·증거금 유입 변동, "
    "대형 IPO 상장일의 유통금융 수요, 유상증자에 따른 담보가치 영향 등.\n"
    "- 소제목·서두 없이 불릿 3개만."
)


def _month_label() -> str:
    d = now_kst()
    return f"{d.year}년 {d.month}월"


def _this_month_events(events: list[dict]) -> list[dict]:
    ym = now_kst().strftime("%Y-%m")
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
    lines = "\n".join(
        f"- {e['date']} [{e['type']}] {e['company']} {e.get('detail', '')}" for e in events
    )
    txt = generate_text(
        f"이번 달 발행시장 일정:\n\n{lines}\n\n브리핑 3줄을 작성해줘.",
        system_instruction=_SYSTEM_PROMPT,
        max_output_tokens=1500,   # Gemini 3.x 는 thinking 토큰이 출력 예산을 먹으므로 넉넉히
    )
    bullets = [b.strip(" -•*") for b in txt.split("\n") if b.strip(" -•*")]
    if not bullets:
        raise RuntimeError("빈 응답")
    return bullets[:3]


def _fill_brief(payload: dict) -> None:
    """try_ai 콜백 — 성공했을 때만 브리핑 필드를 한 번에 대입."""
    bullets = _briefing(payload["events"])
    payload.update(briefing=bullets, briefing_at=stamp(), briefing_note=None)


def _maybe_brief(payload: dict, force: bool = False) -> None:
    has = bool(payload.get("briefing"))
    if has and not force:
        return
    if not get_settings().gemini_api_keys:
        if not has:
            payload["briefing_note"] = "AI 브리핑은 GEMINI_API_KEY 등록 후 제공됩니다."
        return
    if not payload.get("events"):
        payload["briefing_note"] = "이번 달 발행시장 일정이 없습니다."
        return
    status = try_ai(payload, _fill_brief, "발행시장 브리핑")
    if status == AI_CAPPED:
        cap = get_settings().ai_retries_per_snapshot
        payload["briefing_note"] = (
            f"AI 재생성 일일 한도({cap}회)에 도달했습니다."
            + (" 기존 브리핑을 표시합니다." if has else "")
        )
    elif status == AI_FAILED and not has:
        payload["briefing_note"] = "AI 브리핑 생성에 실패했습니다."


def _fallback_from(prev: dict | None) -> dict | None:
    """일정이 없는 날 보여줄 직전 자료. prev 자체도 비어 있으면 prev 가 들고 있던 fallback."""
    if not prev:
        return None
    if prev.get("events"):
        return {k: prev.get(k) for k in _FALLBACK_KEYS}
    return prev.get("fallback")


def _retry_due(snap: dict) -> bool:
    """소스 일부가 실패한 스냅샷이고, 마지막 수집 후 _RETRY_AFTER 가 지났으면 True."""
    if not snap.get("failed_sources"):
        return False
    try:
        collected = datetime.fromisoformat(snap["collected_at"])
    except (KeyError, TypeError, ValueError):
        return True
    return now_kst() - collected >= _RETRY_AFTER


def _collect(today: str, prev: dict | None) -> dict:
    """원자료 수집 → 오늘 payload. prev 는 같은 날 먼저 저장된(일부 실패한) 스냅샷."""
    ipo, ipo_failed = collect_ipo()
    rights, rights_failed = collect_rights()
    failed = ipo_failed + rights_failed
    events = _this_month_events(ipo + rights)

    if prev is not None and failed and set(failed) >= set(prev.get("failed_sources") or []):
        # 재시도했는데 나아진 게 없음 — 기존 결과를 두고 재시도 시각만 미룬다
        return {**prev, "collected_at": now_kst().isoformat()}

    payload = {
        "date": today,
        "month_label": _month_label(),
        "generated_at": stamp(),
        "collected_at": now_kst().isoformat(),
        "events": events,
        "counts": {t: sum(1 for e in events if e["type"] == t) for t in _TREND_TYPES},
        "failed_sources": failed,
        "briefing": None,
        "briefing_at": None,
        "briefing_note": None,
        "gemini_attempts": 0,
    }
    if prev is not None:
        # 같은 날 재수집: Gemini 시도 횟수는 이어가고, 일정이 그대로면 브리핑도 유지
        payload["gemini_attempts"] = prev.get("gemini_attempts", 0)
        if prev.get("events") == events:
            for k in ("briefing", "briefing_at", "briefing_note"):
                payload[k] = prev.get(k)
    if not events:
        payload["fallback"] = _fallback_from(prev if prev is not None else latest_snapshot(_TABLE))
    return payload


def get_issuance_digest(force: bool = False) -> dict:
    today = today_iso()
    with table_lock(_TABLE):
        snap = get_snapshot(_TABLE, today)
        cached = snap is not None and not force
        if snap is None or _retry_due(snap):
            snap = _collect(today, snap)
            save_snapshot(_TABLE, today, snap)
            cached = False
        before = (snap.get("briefing"), snap.get("gemini_attempts", 0), snap.get("briefing_note"))
        _maybe_brief(snap, force=force)
        if (snap.get("briefing"), snap.get("gemini_attempts", 0), snap.get("briefing_note")) != before:
            save_snapshot(_TABLE, today, snap)

    if not snap.get("events") and snap.get("fallback"):
        return {**snap["fallback"], "cached": True, "stale": True}
    return {**snap, "cached": cached}
