"""로그·알림 문구에서 API 키를 가린다.

외부 API 오류(ConnectionError 등)의 메시지에는 요청 URL 이 그대로 들어가 DART crtfc_key,
data.go.kr serviceKey, ECOS 경로 키가 로그에 찍힐 수 있다. 모듈마다 막는 대신 로그 핸들러에
필터를 달아(install) 모든 로그의 메시지·트레이스백에서 설정된 키 값과 키 파라미터를 가린다.
텔레그램 오류 요약(main/batch_report._short_error)도 redact() 를 거친다.
"""
from __future__ import annotations

import logging
import re

from main.config import get_settings

_KEY_PARAM = re.compile(r"((?:crtfc_key|serviceKey|servicekey|api_key|apikey|key)=)[^&\s'\"]+", re.I)


def _secret_values() -> list[str]:
    s = get_settings()
    vals = [s.data_go_kr_api_key, s.dart_api_key, s.ecos_api_key, s.naver_client_secret,
            s.supabase_key, s.warmup_key, s.telegram_bot_token, *s.gemini_api_keys]
    return [v for v in vals if v and len(v) >= 8]


def redact(text: str) -> str:
    if not text:
        return text
    for v in _secret_values():
        text = text.replace(v, "***")
    return _KEY_PARAM.sub(r"\1***", text)


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(record.getMessage())
            record.args = ()
            if record.exc_info and not record.exc_text:
                record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
        except Exception:  # noqa: BLE001 - 로깅 자체는 절대 막지 않는다
            pass
        return True


def install() -> None:
    """루트 로거 핸들러(없으면 lastResort)와 gunicorn 핸들러에 필터를 단다(중복 설치 무시)."""
    handlers = list(logging.getLogger().handlers) + [logging.lastResort]
    for name in ("gunicorn.error", "werkzeug"):
        handlers += logging.getLogger(name).handlers
    for h in handlers:
        if h is not None and not any(isinstance(f, RedactFilter) for f in h.filters):
            h.addFilter(RedactFilter())
