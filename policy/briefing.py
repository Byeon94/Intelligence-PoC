"""정책/규제 탭 데이터 조립.

- 보도자료: 금융위·금감원·한국은행·기재부 공식 사이트 스크랩 (policy.sources)
- 스크랩은 **하루 1회만** 수행하고 그날 스냅샷을 DB(policy.store)에 저장한다.
  같은 날 이후 요청은 저장된 스냅샷을 그대로 돌려준다.
- AI 브리핑: Gemini. 스냅샷당 1회 생성, POLICY_MAX_GEMINI_CALLS_PER_DAY 로 재시도 상한.
"""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from main.config import get_settings

from main.snapshot_store import get_snapshot, latest_snapshot, save_snapshot

from .sources import (
    AFFILIATE_ORGS,
    count_on,
    fetch_affiliates,
    fetch_all,
    group_by_org,
    reference_date,
)

_TABLE = "policy_snapshots"
_SCHEMA_V = 6  # 스냅샷 구조 버전(유관기관 공식 보도자료·링크카드 반영)

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

_SYSTEM_PROMPT = (
    "너는 한국증권금융(KSFC) 임직원을 위한 정책·규제 브리핑 어시스턴트야.\n"
    "금융위·금감원·한국은행·기재부의 최신 보도자료 중 업무상 가장 중요한 것 3가지를 골라 "
    "불릿 3개로 정리해.\n"
    "- 각 불릿은 '- '로 시작하는 **한 문장, 90자 이내**. 앞에 '(금융위)'처럼 발표 기관 표기.\n"
    "- 핵심 발표내용과 KSFC 업무(증권담보대출·신용공여·수탁·자금조달·증권대차) 시사점을 "
    "한 문장으로 압축. 수식어·부연 설명 없이.\n"
    "- 소제목(#)·구분선(---)·서두·출처 표기 없이 불릿 3개만 출력. 보도자료에 없는 내용은 지어내지 마."
)


def _today() -> str:
    return datetime.now(KST).date().isoformat()


# ── Gemini ────────────────────────────────────────────────────────
def _generate_briefing(items: list[dict]) -> str:
    from google.genai import Client
    from google.genai import errors as genai_errors

    s = get_settings()
    keys = list(s.gemini_api_keys)
    if not keys:
        raise RuntimeError("GEMINI_API_KEY 미설정")
    clients = [Client(api_key=k) for k in keys]

    lines = "\n".join(f"[{it['org_name']}] {it['date']} {it['title']}" for it in items)
    contents = (
        "다음은 오늘 기준 금융당국 4곳의 최신 보도자료 제목 목록이다.\n\n"
        f"{lines}\n\n"
        "위 내용을 바탕으로 가장 중요한 3가지만 골라 정책·규제 브리핑을 작성해줘."
    )

    last_err: Exception | None = None
    for i, client in enumerate(clients):
        try:
            resp = client.models.generate_content(
                model=s.gemini_model,
                config={
                    "system_instruction": _SYSTEM_PROMPT,
                    "thinking_config": {"thinking_budget": 0},
                    "max_output_tokens": 900,
                },
                contents=contents,
            )
            text = (resp.text or "").strip()
            if text:
                return text
            last_err = RuntimeError("빈 응답")
        except genai_errors.APIError as exc:
            last_err = exc
            if getattr(exc, "code", None) == 429 and i < len(clients) - 1:
                continue
            raise
    raise last_err or RuntimeError("브리핑 생성 실패")


def _maybe_add_briefing(payload: dict, force: bool = False) -> dict:
    """브리핑이 없으면(또는 force=True 면) 한도 내에서 한 번 생성 시도.

    force 재생성 시 한도 초과·생성 실패면 기존 브리핑은 그대로 둔다.
    """
    s = get_settings()
    has = bool(payload.get("briefing"))
    cap = s.policy_max_gemini_calls_per_day

    if has and not force:
        return payload
    if not s.gemini_api_keys:
        if not has:
            payload["briefing_note"] = "AI 브리핑은 GEMINI_API_KEY 등록 후 제공됩니다. 현재는 보도자료 목록만 표시합니다."
        return payload
    if payload.get("gemini_attempts", 0) >= cap:
        payload["briefing_note"] = (
            f"AI 재생성 일일 한도({cap}회)에 도달했습니다. " +
            ("기존 브리핑을 표시합니다." if has else "목록만 표시합니다.")
        )
        return payload

    payload["gemini_attempts"] = payload.get("gemini_attempts", 0) + 1
    items = [it for g in payload["groups"] for it in g["items"]]
    try:
        payload["briefing"] = _generate_briefing(items)
        payload["briefing_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
        payload["briefing_note"] = None
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI 브리핑 생성 실패: %s", exc)
        if not has:
            payload["briefing_note"] = "AI 브리핑 생성에 실패했습니다. 목록만 표시합니다."
    return payload


# ── 공개 함수 ─────────────────────────────────────────────────────
def get_policy_digest(force_briefing: bool = False) -> dict:
    """force_briefing=True 면(재생성 버튼) 스크랩은 그대로 두고 브리핑만 다시 생성."""
    today = _today()

    snap = get_snapshot(_TABLE, today)
    if snap is not None and snap.get("v") != _SCHEMA_V:
        snap = None  # 구버전 스냅샷 → 새 구조로 다시 수집
    if snap is not None:
        # 스크랩은 이미 오늘 완료됨. 브리핑만 필요 시(또는 재생성 요청 시) 갱신.
        before = (snap.get("briefing"), snap.get("gemini_attempts", 0))
        snap = _maybe_add_briefing(snap, force=force_briefing)
        if (snap.get("briefing"), snap.get("gemini_attempts", 0)) != before:
            save_snapshot(_TABLE, today, snap)
        return {**snap, "cached": not force_briefing}

    # 오늘 첫 요청 → 스크랩 1회 (금융당국 + 유관기관).
    items, failed = fetch_all()
    aff_items, aff_failed = fetch_affiliates()
    if not items and not aff_items:
        stale = latest_snapshot(_TABLE)
        if stale:
            return {**stale, "cached": True, "stale": True}
        raise RuntimeError("보도자료를 한 곳도 가져오지 못했습니다.")

    as_of = reference_date(items)
    aff_groups = group_by_org(aff_items, order=AFFILIATE_ORGS)
    payload = {
        "v": _SCHEMA_V,
        "date": today,
        "as_of": as_of,                        # 조회 기준일(금융당국 기준, 직전 영업일)
        "press_count": count_on(items, as_of),  # 기준일 금융당국 보도자료 총 건수
        "affiliate_count": sum(
            len(g["items"]) for g in aff_groups if not g["items"][0].get("link_only")
        ),
        "generated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "groups": group_by_org(items),
        "affiliate_groups": aff_groups,
        "failed": failed + aff_failed,
        "briefing": None,
        "briefing_at": None,
        "briefing_note": None,
        "gemini_attempts": 0,
    }
    save_snapshot(_TABLE, today, payload)          # 스크랩 결과 먼저 저장 → 오늘 재스크랩 방지
    payload = _maybe_add_briefing(payload)
    save_snapshot(_TABLE, today, payload)
    return {**payload, "cached": False}
