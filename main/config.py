import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # 공공데이터포털(data.go.kr) 금융위원회 서비스 공용 인증키.
    # 비어 있으면 각 데이터 모듈이 샘플(mock) 데이터로 응답한다.
    data_go_kr_api_key: str | None

    # Google AI Studio (Gemini) — 정책/규제 탭 AI 브리핑용.
    gemini_api_key: str | None
    gemini_api_key_2: str | None
    gemini_model: str
    policy_max_gemini_calls_per_day: int

    # Naver 검색 API — 리서치/뉴스 탭.
    naver_client_id: str | None
    naver_client_secret: str | None

    # DART OpenAPI — 자본시장 > 발행시장 탭(유상증자·회사채 공시).
    dart_api_key: str | None

    # Supabase — 정책/규제·리서치 탭 일일 스냅샷 저장용. 없으면 프로세스 메모리에 임시 저장.
    supabase_url: str | None
    supabase_key: str | None


def _env(name: str) -> str | None:
    v = os.getenv(name)
    return v.strip() if v and v.strip() else None


def _int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or "").strip() or default)
    except ValueError:
        return default


def get_settings() -> Settings:
    return Settings(
        data_go_kr_api_key=_env("DATA_GO_KR_API_KEY"),
        gemini_api_key=_env("GEMINI_API_KEY"),
        gemini_api_key_2=_env("GEMINI_API_KEY_2"),
        gemini_model=_env("GEMINI_MODEL") or "gemini-3.5-flash",
        policy_max_gemini_calls_per_day=_int("POLICY_MAX_GEMINI_CALLS_PER_DAY", 3),
        naver_client_id=_env("NAVER_CLIENT_ID"),
        naver_client_secret=_env("NAVER_CLIENT_SECRET"),
        dart_api_key=_env("DART_API_KEY"),
        supabase_url=_env("SUPABASE_URL"),
        supabase_key=_env("SUPABASE_KEY"),
    )
