"""아주 단순한 TTL 메모리 캐시 (조회 폭주·레이트리밋 방지용)."""
from __future__ import annotations

import time
from functools import wraps
from typing import Callable

_store: dict[str, tuple[float, object]] = {}


def ttl_cache(seconds: int) -> Callable:
    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = f"{fn.__module__}.{fn.__qualname__}:{args}:{sorted(kwargs.items())}"
            hit = _store.get(key)
            now = time.time()
            if hit and now - hit[0] < seconds:
                return hit[1]
            value = fn(*args, **kwargs)
            _store[key] = (now, value)
            return value

        return wrapper

    return deco
