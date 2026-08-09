import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    naver_client_id: str
    naver_client_secret: str
    gemini_api_key: str
    gemini_api_key_2: str | None
    supabase_url: str
    supabase_key: str
    dart_api_key: str


def get_settings() -> Settings:
    required = {
        "NAVER_CLIENT_ID": os.getenv("NAVER_CLIENT_ID"),
        "NAVER_CLIENT_SECRET": os.getenv("NAVER_CLIENT_SECRET"),
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_KEY": os.getenv("SUPABASE_KEY"),
        "DART_API_KEY": os.getenv("DART_API_KEY"),
    }

    missing = [key for key, value in required.items() if not value]
    if missing:
        raise RuntimeError(f".env에 다음 값이 설정되어 있지 않습니다: {', '.join(missing)}")

    return Settings(
        naver_client_id=required["NAVER_CLIENT_ID"],
        naver_client_secret=required["NAVER_CLIENT_SECRET"],
        gemini_api_key=required["GEMINI_API_KEY"],
        gemini_api_key_2=os.getenv("GEMINI_API_KEY_2") or None,
        supabase_url=required["SUPABASE_URL"],
        supabase_key=required["SUPABASE_KEY"],
        dart_api_key=required["DART_API_KEY"],
    )
