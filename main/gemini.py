"""Gemini(google-genai) 호출 공용 헬퍼.

- GEMINI_API_KEY, _2 .. _5 를 순서대로 시도한다(중복 제거는 config 에서).
- '이 키의 문제'(429 쿼터·5xx 일시장애·키 무효)면 다음 키로 폴백하고,
  요청 자체가 잘못된 경우(400 INVALID_ARGUMENT 등)는 즉시 실패시킨다.
- Gemini 3.x 는 thinking_budget 을 받지 않으므로(400) 모델별로 thinking 설정을 분기한다.

정책·리서치·발행시장·CMA 탭이 모두 이 함수를 쓴다. 여기만 고치면 된다.
"""
from __future__ import annotations

import logging

from main.config import get_settings

logger = logging.getLogger(__name__)

# 다음 키로 폴백할 오류 코드(할당량·일시 장애·프로젝트 권한).
_RETRY_CODES = {403, 429, 500, 503}


def _key_problem(exc: Exception) -> bool:
    """해당 키만의 문제(무효/만료)라 다른 키면 될 수 있는 경우."""
    msg = str(exc)
    return "API_KEY_INVALID" in msg or "API key not valid" in msg


def _thinking_config(model: str) -> dict:
    # Gemini 3.x/4.x 는 thinking_budget 미지원(400) → thinking_level 로 낮춘다.
    if model.startswith(("gemini-3", "gemini-4")):
        return {"thinking_level": "low"}
    return {"thinking_budget": 0}


def generate_text(
    contents: str,
    *,
    system_instruction: str | None = None,
    max_output_tokens: int = 1024,
    thinking: bool = True,
    tools: list | None = None,
) -> str:
    """여러 키를 순서대로 시도해 첫 성공 응답의 텍스트를 반환. 모두 실패하면 raise."""
    from google.genai import Client
    from google.genai import errors as genai_errors

    s = get_settings()
    keys = list(s.gemini_api_keys)
    if not keys:
        raise RuntimeError("GEMINI_API_KEY 미설정")

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
            if code in _RETRY_CODES or code is None or _key_problem(exc):
                logger.warning("Gemini 키 #%d 실패(code=%s) → 다음 키 시도: %s", i + 1, code, exc)
                continue
            raise
    raise last_err or RuntimeError("Gemini 응답 없음")
