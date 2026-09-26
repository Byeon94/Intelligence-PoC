"""여신 "오늘 신규 리드" 통합 집계.

credit 탭 화면(credit/static/credit.js)과 홈 대시보드 알림(main/home.py)이 항상
같은 숫자를 보도록 이 함수 하나로 계산을 단일화한다. 예전에는 두 곳에 각각
"오늘"을 정하는 로직이 따로 구현돼 있어(프론트는 JS, 홈은 Python), 한쪽만
고치면 화면마다 다른 건수가 표시되는 문제가 있었다.

기준일은 둘 다 '데이터에 실제로 찍힌 최신 날짜'다.
  - dart_ref_date : 공시 리드의 최신 날짜 — DART 공시는 비영업일에 올라오지 않으므로
                    곧 전 영업일 기준이 된다.
  - news_ref_date : 상속·증여/우리사주 뉴스(AI 선별)의 최신 게재일. 뉴스 스냅샷은 매일
                    00시대에 수집되므로 '조회일(오늘)'을 기준으로 잡으면 거의 항상 0건이 된다.
둘 다 데이터가 없으면 오늘(KST).
"""
from __future__ import annotations

import logging

from main.utils import today_iso

from .esop_news import get_esop_news
from .inherit_news import get_inherit_news
from .leads import get_leads

logger = logging.getLogger(__name__)


def get_today_leads_summary() -> dict:
    leads = get_leads()
    if leads.get("pending"):
        return {"pending": True}

    try:
        news = get_inherit_news()
    except Exception as exc:  # noqa: BLE001
        logger.warning("오늘 신규 리드 집계: 상속·증여 뉴스 조회 실패: %s", exc)
        news = {}
    try:
        esop_news = get_esop_news()
    except Exception as exc:  # noqa: BLE001
        logger.warning("오늘 신규 리드 집계: 우리사주 뉴스 조회 실패: %s", exc)
        esop_news = {}

    collateral = leads.get("collateral") or []
    esop = leads.get("esop") or []
    inherit_news_items = news.get("items") or []
    esop_news_items = esop_news.get("items") or []

    today = today_iso()
    dart_dates = [x.get("date") for x in collateral + esop if x.get("date")]
    news_dates = [n.get("published") for n in inherit_news_items + esop_news_items if n.get("published")]
    dart_ref_date = max(dart_dates) if dart_dates else today
    news_ref_date = max(news_dates) if news_dates else today

    today_collateral = [x for x in collateral if x.get("date") == dart_ref_date]
    today_esop = [x for x in esop if x.get("date") == dart_ref_date]
    today_inherit_news = [n for n in inherit_news_items if n.get("published") == news_ref_date]
    today_esop_news = [n for n in esop_news_items if n.get("published") == news_ref_date]

    count = len(today_collateral) + len(today_esop) + len(today_inherit_news) + len(today_esop_news)

    return {
        "pending": False,
        "dart_ref_date": dart_ref_date,
        "news_ref_date": news_ref_date,
        "ref_month": dart_ref_date[:7],
        "count": count,
        "collateral": today_collateral,
        "esop": today_esop,
        "inherit_news": today_inherit_news,
        "esop_news": today_esop_news,
    }
