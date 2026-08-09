import logging
import threading
import time

import requests

logger = logging.getLogger(__name__)

DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DART_VIEWER_URL = "https://dart.fss.or.kr/dsaf001/main.do"

# 013 = 조회된 데이터가 없습니다 (정상 상황, 오류 아님)
_OK_STATUS = {"000", "013"}

# 짧은 시간에 요청이 몰리면 DART가 "010 등록되지 않은 인증키입니다"로 잘못 응답하는 경우가 있어서
# (사실상 순간 요청량 제한로 추정), 같은 프로세스 내 모든 DART 호출 사이에 최소 간격을 둔다.
_MIN_REQUEST_INTERVAL_SECONDS = 1.0
_throttle_lock = threading.Lock()
_last_request_ts = 0.0

_RETRYABLE_STATUS = {"010"}
_MAX_RETRIES = 2
_RETRY_DELAY_SECONDS = 2.0


def _throttle() -> None:
    global _last_request_ts
    with _throttle_lock:
        now = time.monotonic()
        wait = _last_request_ts + _MIN_REQUEST_INTERVAL_SECONDS - now
        if wait > 0:
            time.sleep(wait)
        _last_request_ts = time.monotonic()


def _request(
    api_key: str,
    bgn_de: str,
    end_de: str,
    pblntf_ty: str | None,
    pblntf_detail_ty: str | None,
    page_no: int,
    page_count: int,
    corp_cls: str | None = None,
) -> dict:
    params = {
        "crtfc_key": api_key,
        "bgn_de": bgn_de,
        "end_de": end_de,
        "page_no": page_no,
        "page_count": page_count,
    }
    if pblntf_ty:
        params["pblntf_ty"] = pblntf_ty
    if pblntf_detail_ty:
        params["pblntf_detail_ty"] = pblntf_detail_ty
    if corp_cls:
        params["corp_cls"] = corp_cls

    for attempt in range(_MAX_RETRIES + 1):
        _throttle()
        response = requests.get(DART_LIST_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        status = data.get("status")
        if status in _OK_STATUS:
            return data

        is_last_attempt = attempt == _MAX_RETRIES
        if status in _RETRYABLE_STATUS and not is_last_attempt:
            logger.warning(
                "DART API 일시 오류(%s), %.0f초 후 재시도 (%d/%d)",
                status, _RETRY_DELAY_SECONDS, attempt + 1, _MAX_RETRIES,
            )
            time.sleep(_RETRY_DELAY_SECONDS)
            continue

        raise RuntimeError(f"DART API 오류: {status} {data.get('message')}")


def search_disclosures(
    api_key: str,
    bgn_de: str,
    end_de: str,
    pblntf_ty: str | None = None,
    pblntf_detail_ty: str | None = None,
    page_count: int = 100,
) -> list[dict]:
    data = _request(api_key, bgn_de, end_de, pblntf_ty, pblntf_detail_ty, page_no=1, page_count=page_count)
    return data.get("list") or []


def search_all_disclosures(
    api_key: str,
    bgn_de: str,
    end_de: str,
    pblntf_ty: str | None = None,
    pblntf_detail_ty: str | None = None,
    max_pages: int = 10,
) -> list[dict]:
    items = []
    page_no = 1
    while page_no <= max_pages:
        data = _request(api_key, bgn_de, end_de, pblntf_ty, pblntf_detail_ty, page_no=page_no, page_count=100)
        items.extend(data.get("list") or [])
        if page_no >= data.get("total_page", 1):
            break
        page_no += 1
    return items


def count_disclosures(
    api_key: str,
    bgn_de: str,
    end_de: str,
    corp_cls: str | None = None,
    pblntf_ty: str | None = None,
) -> int:
    data = _request(
        api_key, bgn_de, end_de, pblntf_ty, None, page_no=1, page_count=1, corp_cls=corp_cls
    )
    return data.get("total_count", 0)


def viewer_url(rcept_no: str) -> str:
    return f"{DART_VIEWER_URL}?rcpNo={rcept_no}"
