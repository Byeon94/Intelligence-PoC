"""Gemini(google-genai) 호출 공용 헬퍼 — AI를 쓰는 모든 탭이 generate_text() 하나로 호출한다.

- 키는 GEMINI_API_KEY 하나만 쓴다(main/config.py). 모델은 GEMINI_MODEL.
- Gemini 3.x/4.x 는 thinking_budget 을 받지 않으므로(400) 모델별로 thinking 설정을 분기한다.
- 앱 전체(모든 탭 합산) 하루 실호출 수를 GEMINI_MAX_CALLS_PER_DAY(기본 40)로 제한한다
  — 비용 통제용 소프트 캡. 스냅샷 1건당 재시도 상한(POLICY_MAX_GEMINI_CALLS_PER_DAY,
  main/daily_snapshot.try_ai)과는 별개다. 업종 분류 배치(sector/classify.py)처럼 수동으로만
  돌리는 대량 호출은 count_against_daily_budget=False 로 이 예산에서 제외한다.
"""
from __future__ import annotations

import logging
import threading

from main.config import get_settings
from main.utils import today_iso

logger = logging.getLogger(__name__)

_USAGE_TABLE = "gemini_usage_snapshots"
# 하루 호출 카운터 읽기→증가→저장을 한 번에(gthread 스레드끼리 같은 값을 읽고 덮어써
# 상한을 넘기지 않게). 워커가 1개라 프로세스 락으로 충분하다.
_budget_lock = threading.Lock()


def _thinking_config(model: str) -> dict:
    # Gemini 3.x/4.x 는 thinking_budget 미지원(400) → thinking_level 로 낮춘다.
    if model.startswith(("gemini-3", "gemini-4")):
        return {"thinking_level": "low"}
    return {"thinking_budget": 0}


def _budget_ok(cap: int) -> bool:
    """오늘(KST) 앱 전체 Gemini 실호출 수가 cap 미만이면 카운트를 늘리고 True.

    Supabase 스냅샷(날짜별 카운터)이라 재배포 후에도 유지된다(미설정이면 메모리).
    """
    if cap <= 0:
        return True
    from main.snapshot_store import get_snapshot, save_snapshot

    today = today_iso()
    with _budget_lock:
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
    pdf: bytes | None = None,
) -> str:
    """Gemini 호출 1회. 키 미설정·일일 예산 초과·빈 응답·API 오류는 예외로 올린다.

    pdf 를 넘기면 PDF 원문(표 포함)을 첨부해 함께 보낸다 — 단기자금 시황 브리프 요약용.
    """
    from google.genai import Client
    from google.genai import errors as genai_errors
    from google.genai import types

    if pdf is not None:
        contents = [types.Part.from_bytes(data=pdf, mime_type="application/pdf"), contents]

    s = get_settings()
    if not s.gemini_api_keys:
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

    client = Client(api_key=s.gemini_api_keys[0])   # 지역변수로 유지(임시 객체면 GC 가 httpx 를 닫아버림)
    try:
        resp = client.models.generate_content(
            model=s.gemini_model, config=config, contents=contents,
        )
    except genai_errors.APIError as exc:
        logger.warning("Gemini 호출 실패(code=%s): %s", getattr(exc, "code", None), exc)
        raise
    text = (resp.text or "").strip()
    if not text:
        raise RuntimeError("빈 응답")
    return text
