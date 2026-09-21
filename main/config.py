import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # 공공데이터포털(data.go.kr) 금융위원회 서비스 공용 인증키.
    # 비어 있으면 각 데이터 모듈이 샘플(mock) 데이터로 응답한다.
    data_go_kr_api_key: str | None

    # Google AI Studio (Gemini) — 각 탭 AI 브리핑용.
    # GEMINI_API_KEY 하나만 사용한다(정액제로 사용량 제한 없음 — _2.._5 는 무효 키라
    # 폴백 시도 자체가 오류 로그만 쌓아 제거함, 2026-09-22).
    gemini_api_keys: tuple[str, ...]
    gemini_model: str
    policy_max_gemini_calls_per_day: int
    # 앱 전체(모든 탭 합산) 하루 Gemini 실호출 상한 — 비용 통제용. 업종 분류 배치처럼
    # 별도로 이미 월 1회로 제한된 대량 호출은 이 예산에서 제외한다(main/gemini.py 참고).
    gemini_max_calls_per_day: int

    # Naver 검색 API — 리서치/뉴스 탭.
    naver_client_id: str | None
    naver_client_secret: str | None

    # DART OpenAPI — 자본시장 > 발행시장 탭(유상증자·회사채 공시).
    dart_api_key: str | None

    # Supabase — 정책/규제·리서치 탭 일일 스냅샷 저장용. 없으면 프로세스 메모리에 임시 저장.
    supabase_url: str | None
    supabase_key: str | None

    # /internal/warmup 호출 인증용 비밀키. 매일 아침 외부 스케줄러(GitHub Actions 등)가
    # 이 키를 붙여 호출하면 정책·규제/리서치·뉴스 스냅샷을 미리 만들어둔다.
    warmup_key: str | None


def _env(name: str) -> str | None:
    v = os.getenv(name)
    return v.strip() if v and v.strip() else None


def _int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or "").strip() or default)
    except ValueError:
        return default


def _gemini_keys() -> tuple[str, ...]:
    # GEMINI_API_KEY 하나만 사용(정액제, 무제한). GEMINI_API_KEY_2.._5 는 더 이상 읽지
    # 않는다 — 무효 키로 남아 있으면 매 호출마다 실패 폴백 시도가 로그만 채운다.
    v = _env("GEMINI_API_KEY")
    return (v,) if v else ()


def get_settings() -> Settings:
    return Settings(
        data_go_kr_api_key=_env("DATA_GO_KR_API_KEY"),
        gemini_api_keys=_gemini_keys(),
        gemini_model=_env("GEMINI_MODEL") or "gemini-3.6-flash",
        policy_max_gemini_calls_per_day=_int("POLICY_MAX_GEMINI_CALLS_PER_DAY", 3),
        gemini_max_calls_per_day=_int("GEMINI_MAX_CALLS_PER_DAY", 30),
        naver_client_id=_env("NAVER_CLIENT_ID"),
        naver_client_secret=_env("NAVER_CLIENT_SECRET"),
        dart_api_key=_env("DART_API_KEY"),
        supabase_url=_env("SUPABASE_URL"),
        supabase_key=_env("SUPABASE_KEY"),
        warmup_key=_env("WARMUP_KEY"),
    )
