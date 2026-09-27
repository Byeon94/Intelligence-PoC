"""환경변수(.env) → Settings. 키가 비어 있으면 각 모듈이 샘플 데이터·메모리 저장·AI 생략으로 동작한다."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # 공공데이터포털(data.go.kr) 금융위원회 서비스 공용 인증키.
    # 비어 있으면 각 데이터 모듈이 샘플(mock) 데이터로 응답한다.
    data_go_kr_api_key: str | None

    # Google AI Studio (Gemini) — 각 탭 AI 브리핑용. GEMINI_API_KEY 하나만 읽는다
    # (비었으면 빈 튜플 → AI 가공 생략). 튜플 형태는 호출부 호환용.
    gemini_api_keys: tuple[str, ...]
    gemini_model: str
    # 일일 스냅샷 1건당 Gemini 시도 상한(실패 시 다음 요청에서 재시도하는 횟수 포함).
    # 정책·뉴스·IT뉴스·발행시장·여신 뉴스 등 모든 스냅샷 공통(main/daily_snapshot.try_ai).
    # 환경변수 이름은 Render 설정 호환을 위해 예전 이름(POLICY_MAX_GEMINI_CALLS_PER_DAY) 유지.
    ai_retries_per_snapshot: int
    # 앱 전체(모든 탭 합산) 하루 Gemini 실호출 상한 — 비용 통제용. 수동 실행 전용인
    # 업종 분류 배치 같은 대량 호출은 이 예산에서 제외한다(main/gemini.py 참고).
    gemini_max_calls_per_day: int

    # Naver 검색 API — 뉴스·IT뉴스·증권대차·여신 뉴스(main/naver_news.py).
    naver_client_id: str | None
    naver_client_secret: str | None

    # DART OpenAPI — 발행시장(유상증자 공시), 여신 리드·기업분석(기업개황·재무·공시).
    dart_api_key: str | None

    # 한국은행 ECOS Open API — 단기자금 탭(원화 시장금리·기준금리, 외화 환율·주요국 정책금리).
    ecos_api_key: str | None

    # Supabase — 모든 탭 일일 스냅샷 저장용(main/snapshot_store.py). 없으면 프로세스 메모리에 임시 저장.
    supabase_url: str | None
    supabase_key: str | None

    # /internal/warmup 호출 인증용 비밀키. 매일 00:01·07:00 KST GitHub Actions 가 이 키를 붙여
    # 호출하면 각 탭의 그날 스냅샷을 미리 만들어둔다(main/app.py _WARMUP_JOBS). 비면 403.
    warmup_key: str | None

    # 텔레그램 봇 — 배치 결과 알림(main/batch_report.py). 둘 다 있어야 발송, 없으면 건너뜀.
    telegram_bot_token: str | None
    telegram_chat_id: str | None


def _env(name: str) -> str | None:
    v = os.getenv(name)
    return v.strip() if v and v.strip() else None


def _int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or "").strip() or default)
    except ValueError:
        return default


def _gemini_keys() -> tuple[str, ...]:
    # GEMINI_API_KEY 하나만 읽는다(예전 GEMINI_API_KEY_2.._5 폴백은 제거됨).
    v = _env("GEMINI_API_KEY")
    return (v,) if v else ()


def get_settings() -> Settings:
    return Settings(
        data_go_kr_api_key=_env("DATA_GO_KR_API_KEY"),
        gemini_api_keys=_gemini_keys(),
        gemini_model=_env("GEMINI_MODEL") or "gemini-3.6-flash",
        ai_retries_per_snapshot=_int("POLICY_MAX_GEMINI_CALLS_PER_DAY", 3),
        gemini_max_calls_per_day=_int("GEMINI_MAX_CALLS_PER_DAY", 40),
        naver_client_id=_env("NAVER_CLIENT_ID"),
        naver_client_secret=_env("NAVER_CLIENT_SECRET"),
        dart_api_key=_env("DART_API_KEY"),
        ecos_api_key=_env("ECOS_API_KEY"),
        supabase_url=_env("SUPABASE_URL"),
        supabase_key=_env("SUPABASE_KEY"),
        warmup_key=_env("WARMUP_KEY"),
        telegram_bot_token=_env("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_env("TELEGRAM_CHAT_ID"),
    )
