"""전사 위젯 > 오늘의 IT·정보보호 뉴스 — Naver 뉴스 검색(main.naver_news)으로 후보 기사 수집.

IT부 관심 키워드로 검색 → 최근 1일(오늘 우선) 발행분만 → 제목 중복 제거 → 후보 풀.
Gemini(it_news.curate)가 이 풀에서 상위 5건을 선별·요약한다.
"""
from __future__ import annotations

from datetime import timedelta

from main import naver_news
from main.utils import today_kst

KEYWORDS = [
    "금융 IT", "정보보호", "AI", "클라우드", "빅데이터", "UI/UX",
    "생성형 AI", "개발 트렌드", "혁신금융서비스", "블록체인", "금융 차세대", "한국증권금융",
]


def collect_candidates(max_age_days: int = 1) -> list[dict]:
    """최근 max_age_days 이내(오늘 우선, 그다음 최신순) 후보 기사.

    키 미설정·전 키워드 실패면 naver_news.NewsFetchError.
    """
    today = today_kst()
    cutoff = (today - timedelta(days=max_age_days)).isoformat()
    pool = naver_news.collect(KEYWORDS, display=20, cutoff_date=cutoff)
    pool.sort(key=lambda x: (x["published_date"] == today.isoformat(), x["published"]), reverse=True)
    return pool
