"""종목코드(6자리) → DART corp_code(8자리) 매핑.

DART 는 재무제표·공시·기업개황 조회에 corp_code 를 요구한다.
`corpCode.xml`(zip, 압축 해제 시 ~20MB·10만+ 항목)을 하루 1회만 받아
스트리밍 파싱하고, 결과 맵을 Supabase(하루치)에 저장해 워커 재시작·다중 워커에서 재사용한다.
DART_API_KEY 없으면 빈 맵.
"""
from __future__ import annotations

import io
import logging
import threading
import xml.etree.ElementTree as ET
import zipfile

import requests

from capital._cache import ttl_cache
from main.config import get_settings

from . import store

logger = logging.getLogger(__name__)
_lock = threading.Lock()   # 여러 스레드가 동시에 corpCode.xml 을 중복 다운로드하지 않도록


def _download_map() -> dict[str, str]:
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
        raw = zf.read(zf.namelist()[0])
    except (requests.RequestException, zipfile.BadZipFile) as exc:
        logger.warning("DART corpCode.xml 다운로드 실패: %s", exc)
        return {}

    out: dict[str, str] = {}
    try:
        # iterparse + clear 로 트리를 통째로 안 들고 있게 한다(메모리 절약).
        for _, elem in ET.iterparse(io.BytesIO(raw), events=("end",)):
            if elem.tag != "list":
                continue
            stock_code = (elem.findtext("stock_code") or "").strip()
            corp_code = (elem.findtext("corp_code") or "").strip()
            if stock_code and corp_code:  # 상장사만 (비상장은 stock_code 공백)
                out[stock_code] = corp_code
            elem.clear()
    except ET.ParseError as exc:
        logger.warning("DART corpCode.xml 파싱 실패: %s", exc)
        return {}
    logger.info("DART corp_code 매핑 %d건 로드", len(out))
    return out


@ttl_cache(60 * 60 * 12)
def _index() -> dict[str, str]:
    with _lock:                       # 첫 스레드만 내려받고, 나머지는 그 결과(메모리)를 받음
        cached = store.get_corpmap()
        if cached:
            return cached
        mapping = _download_map()
        if mapping:
            store.save_corpmap(mapping)
        return mapping


def corp_code(stock_code: str) -> str | None:
    return _index().get(stock_code)
