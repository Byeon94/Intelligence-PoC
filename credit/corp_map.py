"""종목코드(6자리) → DART corp_code(8자리) 매핑.

DART 는 재무제표·공시·기업개황 조회에 corp_code 를 요구한다.
`corpCode.xml` (zip) 을 하루 1회 받아 메모리에 캐시한다. DART_API_KEY 없으면 빈 맵.
"""
from __future__ import annotations

import io
import logging
import xml.etree.ElementTree as ET
import zipfile

import requests

from capital._cache import ttl_cache
from main.config import get_settings

logger = logging.getLogger(__name__)


@ttl_cache(60 * 60 * 24)
def _index() -> dict[str, str]:
    key = get_settings().dart_api_key
    if not key:
        return {}
    try:
        resp = requests.get(
            "https://opendart.fss.or.kr/api/corpCode.xml",
            params={"crtfc_key": key},
            timeout=30,
        )
        resp.raise_for_status()
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        root = ET.fromstring(zf.read(zf.namelist()[0]))
    except (requests.RequestException, zipfile.BadZipFile, ET.ParseError) as exc:
        logger.warning("DART corpCode.xml 로드 실패: %s", exc)
        return {}

    out: dict[str, str] = {}
    for e in root.iter("list"):
        stock_code = (e.findtext("stock_code") or "").strip()
        corp_code = (e.findtext("corp_code") or "").strip()
        if stock_code and corp_code:  # 상장사만 (비상장은 stock_code 공백)
            out[stock_code] = corp_code
    logger.info("DART corp_code 매핑 %d건 로드", len(out))
    return out


def corp_code(stock_code: str) -> str | None:
    return _index().get(stock_code)
