"""여신·심사 > 기업분석 > 공시: 종목별 DART 공시 목록.

DART OpenAPI  list.json
  params: crtfc_key, corp_code, bgn_de(YYYYMMDD), end_de, page_no, page_count
  → 최근 N개월 중 최신순. 각 항목의 rcept_no 로 DART 원문 뷰어 링크를 만든다.

공시는 장중에도 계속 올라오므로 하루치 DB 스냅샷 대신 30분 메모리 캐시만 쓴다.
DART_API_KEY 가 없거나 corp_code 를 못 찾으면 빈 목록 + 안내.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import requests

from capital._cache import ttl_cache
from main.config import get_settings

from .corp_map import corp_code

logger = logging.getLogger(__name__)

_URL = "https://opendart.fss.or.kr/api/list.json"
_VIEWER = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="

# DART '비고(rm)' 코드 → 짧은 라벨
_RM = {
    "유": "유가증권", "코": "코스닥", "채": "채권", "넥": "코넥스",
    "공": "공정위", "연": "연결", "정": "정정", "철": "철회/반려", "조": "조회공시",
}


def _fmt_date(yyyymmdd: str | None) -> str:
    s = str(yyyymmdd or "")
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else s


@ttl_cache(60 * 30)
def get_filings(code: str, months: int = 12, limit: int = 20) -> dict:
    key = get_settings().dart_api_key
    cc = corp_code(code) if key else None
    if not cc:
        return {
            "code": code, "items": [], "total": 0, "source": "none",
            "note": "DART 연동이 없어 공시 목록을 불러올 수 없습니다.",
        }

    try:
        resp = requests.get(_URL, params={
            "crtfc_key": key,
            "corp_code": cc,
            "bgn_de": (date.today() - timedelta(days=months * 31)).strftime("%Y%m%d"),
            "end_de": date.today().strftime("%Y%m%d"),
            "page_no": 1,
            "page_count": min(max(limit, 1), 100),
        }, timeout=15)
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.info("DART 공시 조회 실패(%s): %s", code, exc)
        return {"code": code, "items": [], "total": 0, "source": "none",
                "note": "공시 목록을 불러오지 못했습니다. 잠시 후 다시 시도해주세요."}

    status = data.get("status")
    if status == "013":  # 조회된 데이터 없음
        return {"code": code, "items": [], "total": 0, "source": "live", "corp_name": None}
    if status != "000":
        return {"code": code, "items": [], "total": 0, "source": "none",
                "note": f"DART 응답 오류: {data.get('message') or status}"}

    rows = data.get("list") or []
    items = []
    for it in rows:
        rno = (it.get("rcept_no") or "").strip()
        if not rno:
            continue
        rm = (it.get("rm") or "").strip()
        items.append({
            "date": _fmt_date(it.get("rcept_dt")),
            "title": (it.get("report_nm") or "").strip(),
            "filer": (it.get("flr_nm") or "").strip(),
            "tag": _RM.get(rm, rm) or None,
            "url": _VIEWER + rno,
        })

    return {
        "code": code,
        "corp_name": (rows[0].get("corp_name") if rows else None),
        "items": items,
        "total": data.get("total_count", len(items)),
        "source": "live",
    }
