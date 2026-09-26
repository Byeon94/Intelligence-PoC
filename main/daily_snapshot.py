"""일일 스냅샷 + AI 가공 공용 헬퍼.

정책·뉴스·IT뉴스·발행시장·상속증여/우리사주 뉴스는 모두 같은 흐름이다:

    오늘 스냅샷 조회 → 없으면 원자료 수집 후 저장 → AI(Gemini) 가공이 안 됐으면
    스냅샷당 시도 상한(gemini_attempts) 안에서 한 번 시도 → 결과 저장

gunicorn gthread(스레드 4개)에서 워밍업·홈·탭 요청이 동시에 "오늘 첫 요청"이 되면 수집과
Gemini 호출이 중복되고, 각 스레드가 gemini_attempts 를 따로 올려 상한도 뚫린다. 그래서
테이블별 락(table_lock) 안에서 조회→수집→AI→저장을 한 번에 처리한다. 뒤에 온 스레드는
기다렸다가 앞 스레드가 저장한 스냅샷을 그대로 읽는다.
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Callable

from main.config import get_settings

logger = logging.getLogger(__name__)

_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


def table_lock(table: str) -> threading.RLock:
    """스냅샷 테이블별 재진입 락(같은 스레드가 중첩 호출해도 막히지 않음)."""
    with _locks_guard:
        return _locks.setdefault(table, threading.RLock())


def parse_json_obj(text: str) -> dict:
    """Gemini 응답에서 JSON 객체를 꺼낸다(```json 코드블록·앞뒤 설명 허용). 실패 시 ValueError."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[4:] if t[:4].lower() == "json" else t
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b < a:
        raise ValueError("JSON 응답 없음")
    obj = json.loads(t[a : b + 1])
    if not isinstance(obj, dict):
        raise ValueError("JSON 객체가 아님")
    return obj


# try_ai() 결과
AI_NO_KEY = "no_key"      # GEMINI_API_KEY 미설정 — 시도 안 함
AI_CAPPED = "capped"      # 스냅샷당 시도 상한 도달 — 시도 안 함
AI_OK = "ok"              # 시도 성공
AI_FAILED = "failed"      # 시도했지만 예외(로그 남김)


def try_ai(payload: dict, fn: Callable[[dict], None], label: str) -> str:
    """payload 에 대해 AI 가공 fn(payload)을 상한 안에서 1회 시도한다.

    fn 은 payload 를 직접 채우고, 실패하면 예외를 올린다(부분 결과를 payload 에 남기지
    않도록 fn 쪽에서 전부 만든 뒤 한 번에 대입할 것). 상한은 POLICY_MAX_GEMINI_CALLS_PER_DAY
    (settings.ai_retries_per_snapshot) — 스냅샷 1건당 Gemini 시도 횟수다.
    """
    s = get_settings()
    if not s.gemini_api_keys:
        return AI_NO_KEY
    cap = s.ai_retries_per_snapshot
    attempts = payload.get("gemini_attempts", 0)
    if attempts >= cap:
        return AI_CAPPED
    payload["gemini_attempts"] = attempts + 1
    try:
        fn(payload)
        return AI_OK
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s AI 가공 실패(%d/%d회): %s", label, attempts + 1, cap, exc)
        return AI_FAILED
