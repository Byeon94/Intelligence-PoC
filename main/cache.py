"""아주 단순한 TTL 메모리 캐시 (조회 폭주·레이트리밋 방지용).

실패·대체값은 짧게만 캐시한다: 반환값이 비어 있거나(falsy) `source`가 "live"가 아닌
dict(샘플·unavailable 폴백)면 `fallback_seconds`(기본 60초)만 보관한다. 외부 API가 한 번
삐끗했다고 샘플 데이터나 빈 결과가 몇 시간씩 고정되지 않게 하기 위함.
"""
from __future__ import annotations

import time
from functools import wraps
from typing import Callable

_store: dict[str, tuple[float, float, object]] = {}   # key → (저장 시각, 유효 초, 값)


def _is_fallback(value: object) -> bool:
    if not value:
        return True
    return isinstance(value, dict) and "source" in value and value["source"] != "live"


def ttl_cache(seconds: int, fallback_seconds: int = 60) -> Callable:
    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = f"{fn.__module__}.{fn.__qualname__}:{args}:{sorted(kwargs.items())}"
            hit = _store.get(key)
            now = time.time()
            if hit and now - hit[0] < hit[1]:
                return hit[2]
            value = fn(*args, **kwargs)
            ttl = fallback_seconds if _is_fallback(value) else seconds
            _store[key] = (now, ttl, value)
            return value

        return wrapper

    return deco
