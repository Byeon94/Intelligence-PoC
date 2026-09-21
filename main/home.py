"""홈 대시보드: 정책·리서치 통합 브리핑 + 자본시장/여신심사/정책 알림.

각 탭이 이미 하루 1회 캐시해둔 스냅샷(get_policy_digest/get_research_digest/
get_leads/get_inherit_news)과 ttl_cache 된 자본시장 유동성 요약을 재사용한다. 그날 첫
호출이면 해당 스냅샷이 새로 수집될 수 있으나, /internal/warmup 이 매일 아침
미리 데워두므로 평소엔 캐시만 읽는다.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, TypeVar
from zoneinfo import ZoneInfo

from capital.liquidity import get_liquidity_summary
from credit.esop_news import get_esop_news
from credit.inherit_news import get_inherit_news
from credit.leads import get_leads
from policy.briefing import get_policy_digest
from research.curate import get_research_digest

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

T = TypeVar("T")

# 신용공여/예탁금 비율이 전기 대비 이 값(%p) 이상 변하면 홈에 알림 카드 표시.
_RATIO_ALERT_PP = 1.0

# 홈 화면 알림은 최대 이만큼만(과다 노출 방지). 우선순위: ①이상징후(유동성)
# ②여신·심사 신규 리드(상속·증여/우리사주) ③금융당국 동향(최대 1건 — 금융위원회
# 우선순위, AUTHORITY_ORGS 순서를 그대로 따름).
_MAX_ALERTS = 3
_MAX_POLICY_ALERTS = 1


def _safe(label: str, fn: Callable[[], T]) -> T | None:
    try:
        return fn()
    except Exception:  # noqa: BLE001
        logger.exception("홈 요약: %s 조회 실패", label)
        return None


def _liquidity_alert() -> dict | None:
    summary = _safe("자본시장 유동성", get_liquidity_summary)
    if not summary:
        return None
    ratio = (summary.get("items") or {}).get("credit_deposit_ratio") or {}
    change = ratio.get("change") or 0
    if abs(change) < _RATIO_ALERT_PP:
        return None
    direction = "상승" if change > 0 else "하락"
    return {
        "level": "warn",
        "title": f"신용공여/예탁금 비율 {direction}",
        "detail": f"{summary.get('as_of', '')} 기준 {ratio.get('value')}% (전기 대비 {change:+.2f}%p)",
        "tab": "capital",
        "sub": "liquidity",
    }


def _policy_org_alerts(policy: dict | None) -> list[dict]:
    """조회 기준일(비영업일이면 직전 영업일)에 금융당국(금융위·금감원·한국은행·재정경제부)
    보도자료가 새로 등록된 기관이 있으면 알림 카드를 만든다. 최대 _MAX_POLICY_ALERTS건만
    (AUTHORITY_ORGS 순서 = 금융위원회 우선순위)."""
    if not policy:
        return []
    as_of = policy.get("as_of")
    if not as_of:
        return []
    alerts: list[dict] = []
    for g in policy.get("groups") or []:
        if len(alerts) >= _MAX_POLICY_ALERTS:
            break
        items = [it for it in (g.get("items") or []) if it.get("date") == as_of]
        if not items:
            continue
        title = items[0].get("title") or ""
        more = f" 외 {len(items) - 1}건" if len(items) > 1 else ""
        alerts.append({
            "level": "info",
            "title": f"{g.get('org_name') or g.get('badge') or ''} 새 보도자료",
            "detail": f"{as_of} 기준 · {title}{more}",
            "tab": "policy",
        })
    return alerts


def _credit_leads_alert() -> dict | None:
    """여신·심사 메인 화면의 "오늘 신규 리드"와 반드시 같은 기준으로 계산한다
    (credit/static/credit.js 의 renderTopKpis/refDateInfo 와 동일한 로직 — 한쪽만
    고치면 두 화면 숫자가 어긋나므로 함께 유지).

    DART 공시는 비영업일에 올라오지 않으므로 '공시 데이터에 실제로 찍힌 최신
    날짜'가 곧 전 영업일 기준이 되고(dart_ref_date), 뉴스는 주말에도 나올 수
    있어 조회 시점의 실제 날짜(news_ref_date)를 쓴다 — 이 둘을 하나의 날짜로
    합쳐서 세면(예전 방식) 비영업일에는 뉴스만 있는 오늘 날짜가 기준이 돼버려
    전 영업일의 DART 공시 건수가 통째로 빠지는 문제가 있었다."""
    leads = _safe("여신·심사 리드", get_leads)
    if not leads or leads.get("pending"):
        return None
    news = _safe("여신·심사 상속증여 뉴스", get_inherit_news) or {}
    esop_news = _safe("여신·심사 우리사주 뉴스", get_esop_news) or {}

    dart_dates = [x.get("date") for x in (leads.get("collateral") or []) + (leads.get("esop") or []) if x.get("date")]
    news_dates = [n.get("published") for n in (news.get("items") or []) + (esop_news.get("items") or []) if n.get("published")]
    if not dart_dates and not news_dates:
        return None

    news_ref_date = datetime.now(KST).date().isoformat()
    dart_ref_date = max(dart_dates) if dart_dates else news_ref_date
    count = sum(1 for d in dart_dates if d == dart_ref_date) + sum(1 for d in news_dates if d == news_ref_date)
    if count == 0:
        return None
    ref_date = max(dart_ref_date, news_ref_date)
    return {
        "level": "info",
        "title": f"여신·심사 신규 리드 {count}건",
        "detail": f"{ref_date} 기준 · 상속·증여/우리사주 관련 신규 공시·뉴스",
        "tab": "credit",
    }


def get_home_summary() -> dict:
    policy = _safe("정책·규제", get_policy_digest)
    research = _safe("리서치·뉴스", get_research_digest)
    alerts = (
        [a for a in (_liquidity_alert(),) if a]
        + [a for a in (_credit_leads_alert(),) if a]
        + _policy_org_alerts(policy)
    )
    alerts = alerts[:_MAX_ALERTS]

    return {
        "policy": {
            "as_of": policy.get("as_of"),
            "briefing": policy.get("briefing"),
            "briefing_note": policy.get("briefing_note"),
            "press_count": policy.get("press_count"),
            "affiliate_count": policy.get("affiliate_count"),
        } if policy else None,
        "research": {
            "date": research.get("date"),
            "briefing": research.get("briefing"),
            "briefing_note": research.get("briefing_note"),
            "count": len(research.get("articles") or []),
        } if research else None,
        "alerts": alerts,
    }
