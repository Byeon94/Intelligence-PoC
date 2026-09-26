"""Gemini(google-genai) 호출 공용 헬퍼.

- GEMINI_API_KEY 하나만 사용한다(main/config.py 참고).
- Gemini 3.x 는 thinking_budget 을 받지 않으므로(400) 모델별로 thinking 설정을 분기한다.
- 앱 전체(모든 탭 합산) 하루 실호출 수를 GEMINI_MAX_CALLS_PER_DAY(기본 30)로 제한한다
  — 비용 통제용. 개별 탭의 gemini_attempts 재시도 상한(POLICY_MAX_GEMINI_CALLS_PER_DAY)은
  탭 하나가 하루에 몇 번까지 "재시도"하는지를 정할 뿐, 앱 전체 합산 상한은 아니었다.
  업종 분류 배치(sector/classify.py)처럼 이미 자체적으로 월 1회로 제한된 대량 호출은
  count_against_daily_budget=False 로 이 예산에서 제외한다.

정책·뉴스·발행시장·CMA 탭이 모두 이 함수를 쓴다. 여기만 고치면 된다.
"""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from main.config import get_settings

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

_USAGE_TABLE = "gemini_usage_snapshots"


def _key_problem(exc: Exception) -> bool:
    """해당 키만의 문제(무효/만료)라 다른 키면 될 수 있는 경우."""
    msg = str(exc)
    return "API_KEY_INVALID" in msg or "API key not valid" in msg


def _thinking_config(model: str) -> dict:
    # Gemini 3.x/4.x 는 thinking_budget 미지원(400) → thinking_level 로 낮춘다.
    if model.startswith(("gemini-3", "gemini-4")):
        return {"thinking_level": "low"}
    return {"thinking_budget": 0}


def _budget_ok(cap: int) -> bool:
    """오늘 앱 전체 Gemini 실호출 수가 cap 미만이면 카운트를 늘리고 True.

    Supabase 스냅샷(날짜별 카운터)로 워커·재배포 사이에도 유지되게 한다. 약간의
    동시성 레이스는 있을 수 있지만(정확한 과금 시스템이 아닌 소프트한 비용 캡이라
    허용), 대략적인 하루 총량 제어에는 충분하다.
    """
    if cap <= 0:
        return True
    from main.snapshot_store import get_snapshot, save_snapshot

    today = datetime.now(KST).date().isoformat()
    snap = get_snapshot(_USAGE_TABLE, today) or {"count": 0}
    if snap.get("count", 0) >= cap:
        return False
    snap["count"] = snap.get("count", 0) + 1
    save_snapshot(_USAGE_TABLE, today, snap)
    return True


def generate_text(
    contents: str,
    *,
    system_instruction: str | None = None,
    max_output_tokens: int = 1024,
    thinking: bool = True,
    tools: list | None = None,
    count_against_daily_budget: bool = True,
) -> str:
    """Gemini 호출 1회. 앱 전체 일일 예산을 넘으면 호출 전에 실패시킨다."""
    from google.genai import Client
    from google.genai import errors as genai_errors

    s = get_settings()
    keys = list(s.gemini_api_keys)
    if not keys:
        raise RuntimeError("GEMINI_API_KEY 미설정")

    if count_against_daily_budget and not _budget_ok(s.gemini_max_calls_per_day):
        raise RuntimeError(f"Gemini 일일 호출 한도({s.gemini_max_calls_per_day}회)에 도달했습니다.")

    config: dict = {"max_output_tokens": max_output_tokens}
    if system_instruction:
        config["system_instruction"] = system_instruction
    if tools is not None:
        config["tools"] = tools          # 웹검색 등 도구 사용 시엔 thinking 설정 생략
    elif thinking:
        config["thinking_config"] = _thinking_config(s.gemini_model)

    last_err: Exception | None = None
    for i, key in enumerate(keys):
        client = Client(api_key=key)   # 지역변수로 유지(임시 객체면 GC 가 httpx 를 닫아버림)
        try:
            resp = client.models.generate_content(
                model=s.gemini_model, config=config, contents=contents,
            )
            text = (resp.text or "").strip()
            if text:
                return text
            last_err = RuntimeError("빈 응답")
        except genai_errors.APIError as exc:
            last_err = exc
            code = getattr(exc, "code", None)
            if code in {403, 429, 500, 503} or code is None or _key_problem(exc):
                logger.warning("Gemini 키 #%d 실패(code=%s) → 다음 키 시도: %s", i + 1, code, exc)
                continue
            raise
    raise last_err or RuntimeError("Gemini 응답 없음")
