"""네이버 뉴스 검색 API가 가끔 제목을 "..."로 잘라 돌려주는 경우, 원문 링크에서
<title>/og:title 을 가져와 보완한다(inherit_news·esop_news 공용).

AI 필터링을 통과한 소수(최대 15건)에 대해서만, 그것도 Gemini 재시도와 같은 배치
경로(_maybe_filter)에서만 호출되므로 페이지 요청 경로에는 영향이 없다.
"""
from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_TRUNCATED_RE = re.compile(r"(\.\.\.|…)\s*$")


def enrich_title(item: dict, timeout: float = 4.0) -> dict:
    title = item.get("title") or ""
    url = item.get("url")
    if not url or not _TRUNCATED_RE.search(title):
        return item
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        og = soup.find("meta", property="og:title")
        full = (og.get("content") if og else None) or (soup.title.string if soup.title else None)
        full = (full or "").strip()
        # 원문 제목이 우리가 가진 "...로 잘린" 제목보다 짧으면(사이트 자체 표기 등) 의미가 없다.
        if full and len(full) > len(_TRUNCATED_RE.sub("", title)):
            return {**item, "title": full}
    except Exception as exc:  # noqa: BLE001
        logger.info("뉴스 제목 보완 실패(%s): %s", url, exc)
    return item
