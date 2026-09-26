"""공공데이터포털(data.go.kr) 금융위원회 서비스 공통 호출 헬퍼.

- 모든 금융위원회 오픈API는 같은 serviceKey(DATA_GO_KR_API_KEY)를 공유한다.
- 키가 없거나 호출이 실패하면 DataGoError — 호출부에서 샘플/unavailable 로 폴백한다.
- capital 패키지가 같이 쓰는 서비스별 헬퍼도 여기 둔다:
  금융투자협회종합통계(KOFIA: 증시자금·CMA·신용공여)와 지수시세(코스피·코스닥 일별).
  credit/equity.py·credit/leads.py 도 get_json·pick·to_float 를 가져다 쓴다.
"""
from __future__ import annotations

import time
from datetime import timedelta
from typing import Any
from urllib.parse import unquote

import requests

from main.config import get_settings
from main.utils import today_kst

BASE = "https://apis.data.go.kr/1160100/service"
JO = 1_000_000_000_000  # 원 → 조원

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


def ymd(d) -> str:
    """date → 'YYYYMMDD'(data.go.kr beginBasDt/endBasDt 형식)."""
    return d.strftime("%Y%m%d")


# ── 금융투자협회종합통계(GetKofiaStatisticsInfoService) ─────────────
KOFIA_SERVICE = "GetKofiaStatisticsInfoService"
KOFIA_OPS = {
    "stock_fund": "getSecuritiesMarketTotalCapitalInfo",   # 증시자금(투자자예탁금 등)
    "cma": "getCMAStatus",                                 # CMA 현황(운용대상×투자자구분)
    "credit": "getGrantingOfCreditBalanceInfo",            # 신용공여 잔고
}


def date_of(row: dict) -> str | None:
    """행의 기준일자('YYYYMMDD'). 서비스마다 필드명이 달라 후보를 순서대로 본다."""
    return pick(row, "basDt", "BAS_DT", "stdDt", "trdDt")


def kofia_range_params(months: int) -> dict:
    """최근 N개월(+여유 45일) 조회 구간 — 월말 값·전월 비교에 필요한 만큼 넉넉히."""
    today = today_kst()
    begin = today - timedelta(days=int(months * 31) + 45)
    return {"beginBasDt": ymd(begin), "endBasDt": ymd(today), "numOfRows": 20000}


def kofia_rows(op_key: str, months: int) -> list[dict]:
    return get_json(KOFIA_SERVICE, KOFIA_OPS[op_key], kofia_range_params(months))


# ── 지수시세(GetMarketIndexInfoService) ─────────────────────────────
INDEX_SERVICE = "GetMarketIndexInfoService"
INDEX_OP = "getStockMarketIndex"


def index_daily(idx_nm: str, days: int, num_rows: int) -> list[dict]:
    """코스피/코스닥 최근 days일 일별 행 → [{date, close, turnover(원)}] 날짜 오름차순.

    idxNm 은 부분일치라 '코스피 200' 같은 하위지수가 섞여 오므로 이름이 정확히 같은 행만
    남긴다. close·turnover 는 없으면 None — 필요한 값은 호출부에서 거른다.
    """
    today = today_kst()
    rows = get_json(INDEX_SERVICE, INDEX_OP, {
        "idxNm": idx_nm,
        "beginBasDt": ymd(today - timedelta(days=days)),
        "endBasDt": ymd(today),
        "numOfRows": num_rows,
    })
    out = []
    for r in rows:
        if pick(r, "idxNm") not in (idx_nm, None):
            continue
        d = pick(r, "basDt", "BAS_DT")
        if not d:
            continue
        out.append({
            "date": str(d),
            "close": to_float(pick(r, "clpr", "CLPR")),
            "turnover": to_float(pick(r, "trPrc", "TR_PRC")),
        })
    out.sort(key=lambda x: x["date"])
    return out
