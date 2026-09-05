"""공공데이터포털(data.go.kr) 금융위원회 서비스 공통 호출 헬퍼.

- 모든 금융위원회 오픈API는 같은 serviceKey(DATA_GO_KR_API_KEY)를 공유한다.
- 키가 없거나 호출이 실패하면 호출부에서 샘플 데이터로 폴백한다.
"""
from __future__ import annotations

import time
from typing import Any
from urllib.parse import unquote

import requests

from main.config import get_settings

BASE = "https://apis.data.go.kr/1160100/service"

_TIMEOUT = 10
_session = requests.Session()
_session.headers.update({"User-Agent": "KSFC-Intelligence/1.0"})


class DataGoError(RuntimeError):
    """data.go.kr 호출 실패(키 없음·네트워크·응답 오류)."""


def api_key() -> str | None:
    """디코딩된 serviceKey를 돌려준다.

    .env 에 data.go.kr '인코딩' 키(%2F, %3D 포함)를 넣어도 동작하도록,
    requests 가 params 를 다시 인코딩하기 전에 한 번 풀어 준다.
    (data.go.kr 키 원문은 base64 문자셋이라 '%' 가 없어 unquote 는 안전.)
    """
    key = get_settings().data_go_kr_api_key
    return unquote(key) if key else None


def get_json(service: str, operation: str, params: dict[str, Any]) -> list[dict]:
    """`service/operation`을 호출해 items 리스트를 돌려준다.

    표준 응답: {"response": {"header": {...}, "body": {"items": {"item": [...]}}}}
    """
    key = api_key()
    if not key:
        raise DataGoError("DATA_GO_KR_API_KEY 미설정")

    query = {
        "serviceKey": key,
        "resultType": "json",
        "numOfRows": 10000,
        "pageNo": 1,
        **params,
    }

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            resp = _session.get(f"{BASE}/{service}/{operation}", params=query, timeout=_TIMEOUT)
            resp.raise_for_status()
            payload = resp.json()
            break
        except (requests.RequestException, ValueError) as exc:  # ValueError: JSON 파싱
            last_err = exc
            time.sleep(0.6 * (attempt + 1))
    else:
        raise DataGoError(f"{operation} 호출 실패: {last_err}")

    body = (payload or {}).get("response", {}).get("body", {})
    header = (payload or {}).get("response", {}).get("header", {})
    code = header.get("resultCode")
    if code not in (None, "00", "0"):
        raise DataGoError(f"{operation} 오류 {code}: {header.get('resultMsg')}")

    items = body.get("items")
    if isinstance(items, dict):
        items = items.get("item", [])
    if items is None:
        items = []
    if isinstance(items, dict):
        items = [items]
    return items


def pick(row: dict, *candidates: str) -> Any:
    """응답 필드명이 문서와 다를 수 있어 후보 키를 순서대로 시도한다."""
    for key in candidates:
        if key in row and row[key] not in (None, "", "-"):
            return row[key]
    return None


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
