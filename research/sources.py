"""리서치/뉴스 탭 — Naver 뉴스 검색으로 당일 후보 기사 수집.

한국증권금융 업무 관련 키워드로 검색 → 오늘(KST) 발행분만 → 중복 제거 → 후보 풀.
Gemini(research.curate)가 이 풀에서 10건을 선별·태깅한다.
"""
from __future__ import annotations

import html
import logging
import re
import time
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import requests

from main.config import get_settings

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

_ENDPOINT = "https://openapi.naver.com/v1/search/news.json"

# 사용자가 지정한 키워드 + 회사명. 과도한 호출을 피해 핵심만.
KEYWORDS = [
    "한국증권금융", "증권금융공사",
    "투자자예탁금", "증권사 예탁금",
    "신용공여", "신용융자",
    "증권 대차거래", "주식 대차잔고", "대주",
    "우리사주",
    "증권 수탁", "유통금융",
    "공매도",
    "증권사 AI", "금융 디지털 전환",
]

_STRIP_TAG = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return html.unescape(_STRIP_TAG.sub("", text or "")).strip()


def _headers() -> dict:
    s = get_settings()
    if not (s.naver_client_id and s.naver_client_secret):
        raise RuntimeError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 미설정")
    return {
        "X-Naver-Client-Id": s.naver_client_id,
        "X-Naver-Client-Secret": s.naver_client_secret,
    }


def _search(keyword: str, display: int = 30) -> list[dict]:
    resp = requests.get(
        _ENDPOINT,
        headers=_headers(),
        params={"query": keyword, "display": display, "sort": "date"},
        timeout=10,
    )
    resp.raise_for_status()
    out = []
    for it in resp.json().get("items", []):
        try:
            pub = parsedate_to_datetime(it["pubDate"]).astimezone(KST)
        except (KeyError, ValueError, TypeError):
            continue
        out.append({
            "title": _clean(it.get("title")),
            "summary": _clean(it.get("description")),
            "url": it.get("originallink") or it.get("link"),
            "naver_url": it.get("link"),
            "published": pub.strftime("%Y-%m-%d %H:%M"),
            "published_date": pub.date().isoformat(),
            "keyword": keyword,
        })
    return out


def search_news(keyword: str, days: int = 7, limit: int = 3) -> list[dict]:
    """단일 키워드로 최근 days일 내 뉴스 최신순 limit건. (정책 탭 유관기관 폴백용)"""
    from datetime import datetime as _dt
    cutoff = (_dt.now(KST).date() - timedelta(days=days)).isoformat()
    try:
        items = _search(keyword, display=20)
    except requests.RequestException:
        return []
    fresh = [it for it in items if it["published_date"] >= cutoff]
    return fresh[:limit]


def collect_candidates(max_age_days: int = 1) -> list[dict]:
    """최근 max_age_days 이내(오늘 우선) 후보 기사. 제목 기준 중복 제거."""
    today = datetime.now(KST).date()
    cutoff = (today - timedelta(days=max_age_days)).isoformat()

    seen: set[str] = set()
    pool: list[dict] = []
    for kw in KEYWORDS:
        try:
            items = _search(kw)
        except requests.RequestException as exc:
            logger.warning("Naver 뉴스 검색 실패(%s): %s", kw, exc)
            continue
        for it in items:
            if it["published_date"] < cutoff:
                continue
            key = re.sub(r"\W+", "", it["title"])[:40]
            if not key or key in seen:
                continue
            seen.add(key)
            pool.append(it)
        time.sleep(0.05)

    # 오늘 발행분을 앞으로, 그다음 최신순
    pool.sort(key=lambda x: (x["published_date"] == today.isoformat(), x["published"]), reverse=True)
    return pool
