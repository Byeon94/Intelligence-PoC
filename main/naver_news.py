"""네이버 뉴스 검색 API 공용 클라이언트.

뉴스(research)·IT뉴스(it_news)·증권대차(lending)·여신 상속증여/우리사주(credit) 뉴스가
모두 이 모듈로 검색한다. 반환 기사 dict 형식:

    {"title", "summary", "url", "naver_url",
     "published": "YYYY-MM-DD HH:MM", "published_date": "YYYY-MM-DD", "keyword"}

- url 은 http(s) 링크만 남긴다(javascript: 같은 스킴이 화면 href 로 들어가지 않게).
- collect() 는 키워드 전부가 실패하면 NewsFetchError 를 올린다 — 호출자가 "오늘 기사가
  없음"과 "네이버 장애"를 구분해, 장애일 때 빈 결과를 그날 스냅샷으로 굳히지 않도록.
"""
from __future__ import annotations

import html
import logging
import re
import time
from email.utils import parsedate_to_datetime
from typing import Iterable

import requests
from bs4 import BeautifulSoup

from main.config import get_settings
from main.utils import KST

logger = logging.getLogger(__name__)

_ENDPOINT = "https://openapi.naver.com/v1/search/news.json"
_STRIP_TAG = re.compile(r"<[^>]+>")
_TRUNCATED_RE = re.compile(r"(\.\.\.|…)\s*$")


class NewsFetchError(RuntimeError):
    """키 미설정 또는 모든 키워드 검색 실패."""


def _clean(text: str | None) -> str:
    return html.unescape(_STRIP_TAG.sub("", text or "")).strip()


def safe_url(url: str | None) -> str | None:
    return url if url and url.startswith(("http://", "https://")) else None


def dedup_key(title: str) -> str:
    """제목 기준 중복 판정 키 — 기호·공백을 뺀 앞 40자."""
    return re.sub(r"\W+", "", title or "")[:40]


def _headers() -> dict:
    s = get_settings()
    if not (s.naver_client_id and s.naver_client_secret):
        raise NewsFetchError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 미설정")
    return {
        "X-Naver-Client-Id": s.naver_client_id,
        "X-Naver-Client-Secret": s.naver_client_secret,
    }


def search(keyword: str, display: int = 20, sort: str = "date") -> list[dict]:
    """단일 키워드 검색. 키 미설정이면 NewsFetchError, 통신 오류는 requests 예외를 그대로 올린다."""
    resp = requests.get(
        _ENDPOINT,
        headers=_headers(),
        params={"query": keyword, "display": display, "sort": sort},
        timeout=10,
    )
    resp.raise_for_status()
    out = []
    for it in resp.json().get("items", []):
        try:
            pub = parsedate_to_datetime(it["pubDate"]).astimezone(KST)
        except (KeyError, ValueError, TypeError):
            continue
        url = safe_url(it.get("originallink")) or safe_url(it.get("link"))
        if not url:
            continue
        out.append({
            "title": _clean(it.get("title")),
            "summary": _clean(it.get("description")),
            "url": url,
            "naver_url": safe_url(it.get("link")),
            "published": pub.strftime("%Y-%m-%d %H:%M"),
            "published_date": pub.date().isoformat(),
            "keyword": keyword,
        })
    return out


def collect(
    keywords: Iterable[str],
    *,
    display: int = 20,
    sort: str = "date",
    cutoff_date: str | None = None,
    exclude: re.Pattern | None = None,
    seen: set[str] | None = None,
) -> list[dict]:
    """여러 키워드 검색 결과를 합친다(제목 중복 제거, 입력 순서 유지 — 정렬은 호출자가).

    cutoff_date('YYYY-MM-DD') 이전 기사와 exclude 정규식에 걸리는 제목은 뺀다.
    seen 을 넘기면 여러 번 호출해도 중복 판정을 이어간다. 모든 키워드가 실패하면 NewsFetchError.
    """
    seen = set() if seen is None else seen
    pool: list[dict] = []
    keywords = list(keywords)
    failures = 0
    for kw in keywords:
        try:
            items = search(kw, display=display, sort=sort)
        except requests.RequestException as exc:
            failures += 1
            logger.warning("Naver 뉴스 검색 실패(%s): %s", kw, exc)
            continue
        for it in items:
            if cutoff_date and it["published_date"] < cutoff_date:
                continue
            if exclude is not None and exclude.search(it["title"]):
                continue
            key = dedup_key(it["title"])
            if not key or key in seen:
                continue
            seen.add(key)
            pool.append(it)
        time.sleep(0.05)
    if keywords and failures == len(keywords):
        raise NewsFetchError("Naver 뉴스 검색이 모두 실패했습니다.")
    return pool


def enrich_title(item: dict, timeout: float = 4.0) -> dict:
    """검색 API가 제목을 '...'로 잘라 준 경우에만 원문 페이지 og:title/<title>로 보완한다.

    resp.content(바이트)를 BeautifulSoup에 넘겨 meta charset을 직접 감지하게 한다 —
    EUC-KR 사이트를 resp.text(헤더 없으면 latin-1)로 읽으면 제목이 깨지기 때문.
    실패하면 원래 item 그대로.
    """
    title = item.get("title") or ""
    url = item.get("url")
    if not url or not _TRUNCATED_RE.search(title):
        return item
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")
        og = soup.find("meta", property="og:title")
        full = (og.get("content") if og else None) or (soup.title.string if soup.title else None)
        full = re.sub(r"\s*\|\s*[^|]{1,20}$", "", (full or "").strip()).strip()  # " | 언론사명" 접미사 제거
        # 원문 제목이 잘린 제목보다 짧으면(사이트 자체 표기 등) 바꿀 의미가 없다.
        if full and len(full) > len(_TRUNCATED_RE.sub("", title)):
            return {**item, "title": full}
    except Exception as exc:  # noqa: BLE001 - 원문 페이지 구조는 사이트마다 달라 실패가 흔함
        logger.info("뉴스 제목 보완 실패(%s): %s", url, exc)
    return item
