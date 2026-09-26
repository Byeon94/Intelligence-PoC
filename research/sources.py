"""뉴스 탭 — Naver 뉴스 검색(main.naver_news)으로 후보 기사 수집.

한국증권금융 업무 관련 키워드로 검색 → 최근 1일(오늘 우선) 발행분만 → 제목 중복 제거 → 후보 풀.
Gemini(research.curate)가 이 풀에서 20건을 선별·태깅한다.
search_news()는 단일 키워드 최신 기사 조회용으로 시장 브리핑(capital.briefing)이 관련 기사 링크에 쓴다.
"""
from __future__ import annotations

from datetime import timedelta

import requests

from main import naver_news
from main.utils import today_kst

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


def search_news(keyword: str, days: int = 7, limit: int = 3) -> list[dict]:
    """단일 키워드로 최근 days일 내 뉴스 최신순 limit건(시장 브리핑 관련 기사용).

    통신 오류는 빈 리스트, 키 미설정은 NewsFetchError 를 그대로 올린다.
    """
    cutoff = (today_kst() - timedelta(days=days)).isoformat()
    try:
        items = naver_news.search(keyword, display=20)
    except requests.RequestException:
        return []
    return [it for it in items if it["published_date"] >= cutoff][:limit]


def collect_candidates(max_age_days: int = 1) -> list[dict]:
    """최근 max_age_days 이내(오늘 우선, 그다음 최신순) 후보 기사.

    키 미설정·전 키워드 실패면 naver_news.NewsFetchError.
    """
    today = today_kst()
    cutoff = (today - timedelta(days=max_age_days)).isoformat()
    pool = naver_news.collect(KEYWORDS, display=30, cutoff_date=cutoff)
    pool.sort(key=lambda x: (x["published_date"] == today.isoformat(), x["published"]), reverse=True)
    return pool
