"""홈 대시보드: 정책·리서치 통합 브리핑 + 자본시장/여신심사/정책 알림.

각 탭이 이미 하루 1회 캐시해둔 스냅샷(get_policy_digest/get_research_digest/
get_leads/get_inherit_news)과 ttl_cache 된 자본시장 유동성 요약을 재사용한다. 그날 첫
호출이면 해당 스냅샷이 새로 수집될 수 있으나, /internal/warmup 이 매일 아침
미리 데워두므로 평소엔 캐시만 읽는다.
"""
from __future__ import annotations

import logging
from typing import Callable, TypeVar

from capital.liquidity import get_liquidity_summary
from capital.market_snapshot import get_market_snapshot
from credit.today_summary import get_today_leads_summary
from policy.briefing import get_policy_digest
from research.curate import get_research_digest

logger = logging.getLogger(__name__)

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


def _policy_highlight(policy: dict | None) -> dict | None:
    """오늘의 브리핑 "꼭 확인하세요" 카드 1건 — 기준일에 실제로 올라온 보도자료 중 첫 건.
    _policy_org_alerts()와 같은 as_of 필터를 쓰되, "꼭 확인하세요" 카드용으로 제목·기관·
    날짜·원문 링크를 그대로 돌려준다(지어낸 요약 없음 — 스크랩 대상 자체가 이미 KSFC
    관련 기관으로 걸러져 있어 "확인이 필요하다"는 문구는 일반적이어도 사실에 부합)."""
    if not policy:
        return None
    as_of = policy.get("as_of")
    if not as_of:
        return None
    for g in policy.get("groups") or []:
        items = [it for it in (g.get("items") or []) if it.get("date") == as_of]
        if items:
            it = items[0]
            return {
                "kind": "policy",
                "title": it.get("title") or "",
                "org": g.get("org_name") or g.get("badge") or "",
                "date": as_of,
                "url": it.get("url"),
                "hot": True,
            }
    return None


def _credit_leads_alert() -> dict | None:
    """여신·심사 탭의 "오늘 신규 리드"와 항상 같은 숫자를 보여준다 —
    credit.today_summary.get_today_leads_summary() 하나로 계산을 단일화해
    화면마다(홈/여신·심사 탭) 다른 건수가 표시되던 문제를 막는다."""
    summary = _safe("여신·심사 오늘 신규 리드", get_today_leads_summary)
    if not summary or summary.get("pending"):
        return None
    count = summary.get("count") or 0
    if count == 0:
        return None
    ref_date = max(summary["dart_ref_date"], summary["news_ref_date"])
    return {
        "level": "info",
        "title": f"여신·심사 신규 공시/뉴스 {count}건",
        "detail": f"{ref_date} 기준 · 상속·증여/우리사주 관련 신규 공시·뉴스",
        "tab": "credit",
    }


def get_home_summary() -> dict:
    policy = _safe("정책·규제", get_policy_digest)
    research = _safe("리서치·뉴스", get_research_digest)
    market = _safe("오늘의 시장 한눈에", get_market_snapshot)
    alerts = (
        [a for a in (_liquidity_alert(),) if a]
        + [a for a in (_credit_leads_alert(),) if a]
        + _policy_org_alerts(policy)
    )
    alerts = alerts[:_MAX_ALERTS]

    # "꼭 확인하세요"(오늘의 브리핑) — 정책 발표 1건(있으면) + AI 선별 리서치·뉴스 상위 건.
    # 리서치 기사는 이미 AI가 업무 관련도순으로 정렬·태깅·이유(reason)까지 판단해둔
    # research.curate 결과를 그대로 재사용한다(추가 Gemini 호출 없음).
    articles = research.get("articles") if research else None
    highlights: list[dict] = []
    ph = _policy_highlight(policy)
    if ph:
        highlights.append(ph)
    for a in (articles or [])[: (4 if not ph else 3)]:
        highlights.append({
            "kind": "research", "title": a.get("title"), "tag": a.get("tag"),
            "date": a.get("published"), "url": a.get("url"), "reason": a.get("reason"),
        })

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
            "candidate_count": research.get("candidate_count"),
            "articles": articles or [],
        } if research else None,
        "market": market,
        "highlights": highlights,
        "alerts": alerts,
    }
