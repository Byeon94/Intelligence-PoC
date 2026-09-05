from functools import lru_cache

from supabase import Client, create_client

from main.config import get_settings


@lru_cache(maxsize=1)
def get_supabase_client() -> Client | None:
    s = get_settings()
    if not (s.supabase_url and s.supabase_key):
        return None
    return create_client(s.supabase_url, s.supabase_key)
