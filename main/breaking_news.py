"""오늘의 핵심 — 당일 경제 속보(네이버 뉴스 검색 API).

영업일(주말·공휴일·KRX 휴장일 제외) 09:00~18:00 KST 에만, 제목이 "[속보]"로 시작하고 경제·금융
키워드가 들어간 기사 중 게재 60분 이내의 가장 최근 1건을 오늘의 핵심 3번째 칸에 띄운다.

수집은 GitHub Actions 배치가 아니라 요청 시 15분 캐시로 한다 — Actions 스케줄은 수 시간씩
밀려 10~20분 간격을 지킬 수 없다. 홈 화면은 열려 있는 동안 10분마다 다시 불러오므로
(main/static/home/briefing.js) 사용자가 보고 있으면 최대 약 15분 안에 새 속보가 반영된다.
네이버 호출은 15분에 1번(영업시간 내 하루 최대 약 36번)이고 Gemini 호출은 없다.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta

import holidays
import requests

from .cache import ttl_cache
from .naver_news import NewsFetchError, dedup_key, search
from .utils import KST, now_kst

logger = logging.getLogger(__name__)

_WINDOW = timedelta(minutes=60)   # 게재 후 이만큼만 오늘의 핵심에 노출
_REFRESH_SEC = 15 * 60
_OPEN_HOUR, _CLOSE_HOUR = 9, 18

_BREAKING = re.compile(r"^\s*\[\s*속보\s*\]")
_ECON = re.compile(
    r"코스피|코스닥|증시|주가|뉴욕증시|나스닥|다우|S&P|환율|원[·ㆍ]?달러|달러|엔화|위안|금리|국채|채권|"
    r"기준금리|금통위|한은|한국은행|연준|Fed|FOMC|물가|CPI|GDP|성장률|수출|무역|관세|유가|WTI|브렌트|"
    r"금융위|금감원|금융감독|재정경제부|재경부|기재부|기획재정부|증권|은행|보험|카드사|대출|가계부채|"
    r"부동산|주택|공매도|IPO|상장|유상증자|자사주|배당|시가총액|시총|반도체|삼성전자|하이닉스|"
    r"인수|매각|합병|M&A|파산|회생|부도|워크아웃|신용등급|외환|가상자산|비트코인|스테이블코인|ADR"
)
_EXCLUDE = re.compile(r"기상|날씨")


def _krx_closed(d: date) -> bool:
    """주말·법정공휴일(대체공휴일 포함)·KRX 추가 휴장일(근로자의 날, 연말 12/31)."""
    if d.weekday() >= 5 or d in holidays.KR(years=d.year):
        return True
    return (d.month, d.day) in ((5, 1), (12, 31))


def in_business_hours(now: datetime | None = None) -> bool:
    now = now or now_kst()
    return not _krx_closed(now.date()) and _OPEN_HOUR <= now.hour < _CLOSE_HOUR


@ttl_cache(_REFRESH_SEC)
def _recent_breaking() -> dict:
    """최근 경제 속보 목록(최신순, 제목 중복 제거) — 15분 캐시."""
    try:
        items = search("속보", display=100, sort="date")
    except (NewsFetchError, requests.RequestException, ValueError) as exc:
        logger.info("속보 검색 실패: %s", exc)
        return {"source": "unavailable"}
    out, seen = [], set()
    for it in items:
        title = it["title"]
        if not _BREAKING.search(title) or _EXCLUDE.search(title) or not _ECON.search(title):
            continue
        key = dedup_key(_BREAKING.sub("", title))
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return {"source": "live", "items": out}


def get_breaking_news() -> dict | None:
    """영업시간이면 게재 60분 이내 경제 속보 1건, 아니면 None."""
    now = now_kst()
    if not in_business_hours(now):
        return None
    data = _recent_breaking()
    for it in data.get("items") or []:
        pub = datetime.strptime(it["published"], "%Y-%m-%d %H:%M").replace(tzinfo=KST)
        if now - pub <= _WINDOW:
            return {
                "title": _BREAKING.sub("", it["title"]).strip(),
                "summary": it.get("summary") or "",
                "url": it["url"],
                "published": it["published"],
            }
        break   # 최신순이라 첫 건이 60분을 넘었으면 나머지도 넘는다
    return None
