"""정책 탭 데이터 조립.

흐름(테이블 락 안에서 한 번에): 오늘 스냅샷 조회 → 없거나 구버전이면 금융당국 4곳
(금융위·금감원·한국은행·재정경제부)과 유관기관(예보·금투협 스크랩, 거래소·예탁원은 링크 카드)
보도자료를 스크랩(policy.sources)하고 표시분의 상세 본문을 붙여 저장(main.snapshot_store)
→ 브리핑이 없으면 Gemini 로 스냅샷당 시도 상한(POLICY_MAX_GEMINI_CALLS_PER_DAY) 안에서
1회 생성 → 저장. 같은 날 이후 요청은 저장된 스냅샷을 그대로 돌려준다.
전 기관 스크랩 실패 시에는 직전 스냅샷(stale)을 주고, 10분간 재스크랩하지 않는다.
"""
from __future__ import annotations

import time

from main.config import get_settings
from main.daily_snapshot import AI_CAPPED, AI_FAILED, AI_NO_KEY, table_lock, try_ai
from main.gemini import generate_text
from main.snapshot_store import get_snapshot, latest_snapshot, save_snapshot
from main.utils import stamp, today_iso

from .sources import (
    AFFILIATE_ORGS,
    attach_bodies,
    count_on,
    fetch_affiliates,
    fetch_all,
    group_by_org,
    reference_date,
)

_TABLE = "policy_snapshots"
_SCHEMA_V = 9  # v9: 스크랩 실패 기관 1회 재시도 추가(오늘자 금융위 누락 재수집)
_RETRY_AFTER = 600   # 전 기관 스크랩 실패 후 재스크랩까지 대기(초) — 8곳×15초 타임아웃이 요청마다 스레드를 묶지 않게
_fail_at = 0.0       # 마지막 전체 실패 시각(time.monotonic), 락 안에서만 갱신

_SYSTEM_PROMPT = (
    "너는 한국증권금융(KSFC) 임직원을 위한 정책·규제 브리핑 어시스턴트야.\n"
    "금융위·금감원·한국은행·재정경제부 및 예금보험공사·금융투자협회의 최신 보도자료 중 "
    "업무상 가장 중요한 것 3가지를 골라 불릿 3개로 정리해.\n"
    "- 각 항목은 '제목'과, 가능하면 '본문 발췌'가 함께 주어진다. 본문이 있으면 그 내용을 "
    "우선 근거로 삼고, 본문이 없으면 제목만으로 판단해.\n"
    "- 각 불릿은 '- '로 시작하는 **한 문장, 90자 이내**. 앞에 '(금융위)'처럼 발표 기관 표기.\n"
    "- 핵심 발표내용과 KSFC 업무(증권담보대출·신용공여·수탁·자금조달·증권대차) 시사점을 "
    "한 문장으로 압축. 수식어·부연 설명 없이.\n"
    "- 소제목(#)·구분선(---)·서두·출처 표기 없이 불릿 3개만 출력. 보도자료에 없는 내용은 지어내지 마."
)


# ── Gemini ────────────────────────────────────────────────────────
def _generate_briefing(items: list[dict]) -> str:
    blocks = []
    for it in items:
        head = f"[{it['org_name']}] {it['date']} {it['title']}"
        body = (it.get("body") or "").strip()
        if body:
            head += f"\n  ▷ 본문 발췌: {body}"
        blocks.append(head)
    lines = "\n\n".join(blocks)
    contents = (
        "다음은 오늘 기준 금융당국·유관기관의 최신 보도자료다. "
        "각 항목은 제목이며, '▷ 본문 발췌'가 있으면 상세페이지 본문 일부다.\n\n"
        f"{lines}\n\n"
        "위 내용을 바탕으로 가장 중요한 3가지만 골라 정책·규제 브리핑을 작성해줘."
    )
    return generate_text(
        contents, system_instruction=_SYSTEM_PROMPT, max_output_tokens=2048,
    )


def _apply_briefing(payload: dict) -> None:
    groups = list(payload.get("groups", [])) + [
        g for g in payload.get("affiliate_groups", [])
        if g.get("items") and not g["items"][0].get("link_only")
    ]
    briefing = (_generate_briefing([it for g in groups for it in g["items"]]) or "").strip()
    if not briefing:
        raise ValueError("빈 브리핑 응답")
    payload.update(briefing=briefing, briefing_at=stamp(), briefing_note=None)


def _maybe_add_briefing(payload: dict) -> None:
    """브리핑이 없으면 상한 안에서 1회 생성 시도하고, 결과에 맞는 안내문을 남긴다."""
    if payload.get("briefing"):
        return
    status = try_ai(payload, _apply_briefing, "정책 브리핑")
    if status == AI_NO_KEY:
        payload["briefing_note"] = "AI 브리핑은 GEMINI_API_KEY 등록 후 제공됩니다. 현재는 보도자료 목록만 표시합니다."
    elif status == AI_CAPPED:
        cap = get_settings().ai_retries_per_snapshot
        payload["briefing_note"] = f"AI 재생성 일일 한도({cap}회)에 도달했습니다. 목록만 표시합니다."
    elif status == AI_FAILED:
        payload["briefing_note"] = "AI 브리핑 생성에 실패했습니다. 목록만 표시합니다."


def _stale_or_raise() -> dict:
    stale = latest_snapshot(_TABLE)
    if stale:
        return {**stale, "cached": True, "stale": True}
    raise RuntimeError("보도자료를 한 곳도 가져오지 못했습니다.")


# ── 공개 함수 ─────────────────────────────────────────────────────
def get_policy_digest() -> dict:
    global _fail_at
    with table_lock(_TABLE):
        today = today_iso()
        snap = get_snapshot(_TABLE, today)
        if snap is not None and snap.get("v") != _SCHEMA_V:
            snap = None  # 구버전 스냅샷 → 새 구조로 다시 수집
        if snap is not None:
            # 스크랩은 이미 오늘 완료됨. 브리핑만 없으면 상한 안에서 재시도.
            before = snap.get("gemini_attempts", 0)
            _maybe_add_briefing(snap)
            if snap.get("gemini_attempts", 0) != before:
                save_snapshot(_TABLE, today, snap)
            return {**snap, "cached": True}

        if _fail_at and time.monotonic() - _fail_at < _RETRY_AFTER:
            return _stale_or_raise()

        # 오늘 첫 요청 → 스크랩 1회 (금융당국 + 유관기관).
        items, failed = fetch_all()
        aff_items, aff_failed = fetch_affiliates()
        # 거래소·예탁원 링크 카드는 스크랩이 아니므로 성공 판정에서 뺀다.
        if not items and not any(not it.get("link_only") for it in aff_items):
            _fail_at = time.monotonic()
            return _stale_or_raise()
        _fail_at = 0.0

        as_of = reference_date(items)
        auth_groups = group_by_org(items)
        aff_groups = group_by_org(aff_items, order=AFFILIATE_ORGS)
        # 화면 표시(기관당 상위 3건)에 한해 상세페이지 본문을 병렬 수집 → 브리핑 근거로 사용.
        attach_bodies(auth_groups + aff_groups)
        payload = {
            "v": _SCHEMA_V,
            "date": today,
            "as_of": as_of,                        # 조회 기준일(금융당국 기준, 직전 영업일)
            "press_count": count_on(items, as_of),  # 기준일 금융당국 보도자료 총 건수
            "affiliate_count": sum(
                len(g["items"]) for g in aff_groups if not g["items"][0].get("link_only")
            ),
            "generated_at": stamp(),
            "groups": auth_groups,
            "affiliate_groups": aff_groups,
            "failed": failed + aff_failed,
            "briefing": None,
            "briefing_at": None,
            "briefing_note": None,
            "gemini_attempts": 0,
        }
        save_snapshot(_TABLE, today, payload)          # 스크랩 결과 먼저 저장 → 오늘 재스크랩 방지
        _maybe_add_briefing(payload)
        save_snapshot(_TABLE, today, payload)
        return {**payload, "cached": False}
