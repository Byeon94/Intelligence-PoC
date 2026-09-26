"""Supabase 클라이언트(프로세스당 1개 캐시). URL/KEY 미설정이면 None — 생성 실패 처리는 snapshot_store 가 한다."""
from functools import lru_cache

from supabase import Client, create_client

from main.config import get_settings


@lru_cache(maxsize=1)
def get_supabase_client() -> Client | None:
    s = get_settings()
    if not (s.supabase_url and s.supabase_key):
        return None
    return create_client(s.supabase_url, s.supabase_key)
