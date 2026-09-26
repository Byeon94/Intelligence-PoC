"""여신 메인 화면 — 우리사주(유상증자·IPO) 관련 뉴스 동향(참고용, AI 관련도 판단).

DART 공시(leads.py)는 유상증자·IPO 접수 사실만 잡고, 실제 우리사주조합 배정 규모·
청약 경쟁률·직원 반응 같은 내용은 공시 원문보다 언론 보도가 먼저·자세히 다루는
경우가 많아, 네이버 뉴스에서 우리사주 배정·청약 관련 기사를 모으고 Gemini로
무관한 기사(우리사주 제도 일반론 등)를 걸러 보완 정보로 보여준다.

일반 키워드("우리사주 청약" 등)만으로는 언론이 크게 다루는 대형주(예: 삼성바이오로직스)
기사만 잡히고, 실제 DART 공시가 훨씬 많은 중소형주 관련 보도는 거의 안 잡히는 걸
확인해(2026-09-20), leads.py 의 최근 유상증자·IPO 종목명으로 "{종목명} 우리사주"
검색을 추가해 회사별로 직접 찾는다.

어디까지나 언론 보도 기반 참고 정보다 — 실제 배정 물량·청약률은 DART 공시 원문에서
별도 확인이 필요하며, Gemini 판단도 주어진 기사 '제목'만 근거로 하고 제목에 없는
사실을 지어내지 않도록 프롬프트로 제약한다(inherit_news.py 와 동일한 원칙).

하루 1회 수집해 스냅샷으로 캐시한다(흐름은 credit/news_filter.py 공용).
"""
from __future__ import annotations

import logging
from datetime import timedelta

from main.naver_news import NewsFetchError, collect
from main.utils import today_kst

from .leads import get_leads
from .news_filter import daily_filtered_news, slim

logger = logging.getLogger(__name__)

_TABLE = "credit_esop_news_snapshots"

_KEYWORDS = ["우리사주조합 배정", "우리사주 청약", "유상증자 우리사주", "공모주 우리사주"]
_MAX_COMPANIES = 15         # 종목별 검색 대상(최근 유상증자·IPO 상위 N개사)
_PER_COMPANY_DISPLAY = 5    # 종목별 검색은 결과가 적어 소량만 받아도 충분
_LOOKBACK_DAYS = 60         # leads.py 와 동일한 조회 기간(그보다 오래된 뉴스는 제외)

_SYSTEM_PROMPT = (
    "너는 한국증권금융(KSFC) 여신심사 담당자를 위한 리서치 어시스턴트야.\n"
    "아래는 뉴스 기사 제목 목록이다. 특정 상장(예정) 회사의 '유상증자'·'IPO(공모)'에서 "
    "우리사주조합이 주식을 배정받거나 청약하는 이벤트뿐 아니라, 우리사주조합의 장내 매입·취득, "
    "임직원 우리사주 보유 비율 관련 소식처럼 특정 회사 임직원이 자사주를 취득하는 맥락이면 "
    "폭넓게 관련 있다고 판단해라(취득 자금 마련 수요로 이어질 수 있는 신호이기 때문). "
    "우리사주 제도 자체에 대한 일반론·법 개정 기사, 특정 회사의 자사주 취득과 무관한 유상증자·"
    "IPO 단신(청약률·공모가 등 재무 지표만 다루는 기사)은 관련 없음으로 처리해.\n"
    "각 줄에 대해 제목에 적힌 내용만 근거로 판단하고, 제목에 없는 회사명·금액·수량·날짜를 "
    "지어내지 마.\n"
    "출력 형식: 각 줄에 '번호. 판단' — 관련 있으면 어느 회사·어떤 맥락인지 한 문장으로, "
    "관련 없으면 정확히 '관련 없음'이라고만 써. 번호는 입력 목록의 순번과 반드시 일치시켜라. "
    "다른 설명·소제목 없이 목록만 출력해."
)


def _recent_esop_companies() -> list[str]:
    """leads.py 가 이미 모아둔 최근 유상증자·IPO 종목명(중복 제거, 최신순 상위 N개)."""
    try:
        leads = get_leads()
    except Exception as exc:  # noqa: BLE001
        logger.warning("최근 유상증자·IPO 종목 목록 조회 실패: %s", exc)
        return []
    seen: set[str] = set()
    names: list[str] = []
    for it in leads.get("esop") or []:
        name = (it.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
        if len(names) >= _MAX_COMPANIES:
            break
    return names


def _collect_candidates(limit: int = 60) -> list[dict]:
    """일반 키워드 + 최근 유상증자·IPO 종목별("{종목명} 우리사주") 검색 결과(최근 60일, 최신순).

    일반 키워드 검색이 전부 실패하면 NewsFetchError 를 올린다(네이버 장애·키 미설정).
    종목별 검색만 전부 실패한 경우는 일반 키워드 결과만으로 진행한다.
    """
    cutoff = (today_kst() - timedelta(days=_LOOKBACK_DAYS)).isoformat()
    seen: set[str] = set()
    pool = collect(_KEYWORDS, display=15, cutoff_date=cutoff, seen=seen)
    names = _recent_esop_companies()
    if names:
        try:
            pool += collect([f"{n} 우리사주" for n in names], display=_PER_COMPANY_DISPLAY,
                            cutoff_date=cutoff, seen=seen)
        except NewsFetchError as exc:
            logger.warning("우리사주 종목별 뉴스 검색 실패: %s", exc)
    pool.sort(key=lambda x: x["published"], reverse=True)
    return [slim(it) for it in pool[:limit]]


_SCHEMA_V = 3  # v3: 후보 뉴스와 AI 판단을 분리 저장 + gemini_attempts 재시도 상한 추가
                # (inherit_news.py 와 동일 원칙 — AI 호출 실패로 빈 결과가 하루 종일 굳는 문제 방지)


def get_esop_news(rebuild: bool = False) -> dict:
    return daily_filtered_news(_TABLE, _SCHEMA_V, _collect_candidates, _SYSTEM_PROMPT,
                               "우리사주 뉴스", rebuild=rebuild)
