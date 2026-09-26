"""홈 대시보드: 정책·리서치 통합 브리핑 + 자본시장/여신심사/정책 알림.

각 탭이 이미 하루 1회 캐시해둔 스냅샷(get_policy_digest/get_research_digest/
get_leads/get_inherit_news)과 ttl_cache 된 자본시장 유동성 요약을 재사용한다. 그날 첫
호출이면 해당 스냅샷이 새로 수집될 수 있으나, /internal/warmup 이 매일 아침
미리 데워두므로 평소엔 캐시만 읽는다.
"""
from __future__ import annotations

import logging
from typing import Callable, TypeVar

from capital.briefing import CATEGORIES, get_market_briefing
from capital.liquidity import get_liquidity_summary
from capital.market_snapshot import (
    get_global_market_history_1y,
    get_global_market_snapshot,
    get_market_history_1y,
    get_market_snapshot,
)
from credit.today_summary import get_today_leads_summary
from policy.briefing import get_policy_digest
from research.curate import get_research_digest

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 신용공여/예탁금 비율이 전기 대비 이 값(%p) 이상 변하면 홈에 알림 카드 표시.
_RATIO_ALERT_PP = 1.0

# "오늘의 핵심"은 최대 이만큼만(AI가 먼저 걸러줬다는 느낌을 주기 위해 뉴스 feed처럼
# 나열하지 않는다). 우선순위: ①이상징후(유동성) ②금융당국(금융위원회 등) 보도자료 1건
# ③여신 신규 리드(상속·증여/우리사주) ④AI 선별 리서치 기사(나머지 자리를 채움).
_MAX_TODAY_KEY = 3

# "오늘의 주요뉴스"(홈 미리보기 5건) — research.curate 가 관련도순으로 골라둔 기사를
# 그대로 앞에서부터 5개 자르면 같은 태그(예: 증권담보/신용공여)가 상위를 독점할 수 있다.
# 관련도 순서는 유지하되 태그당 이만큼만 담아 주제가 겹치지 않게 한다(부족하면 남은
# 자리는 순서대로 마저 채움 — 억지로 5건 미만으로 줄이지는 않는다).
_MAX_TODAY_NEWS = 5
_MAX_PER_TAG_TODAY_NEWS = 2


def _diversify_news(articles: list[dict], limit: int, max_per_tag: int) -> list[dict]:
    picked: list[dict] = []
    tag_count: dict[str, int] = {}
    for a in articles:
        if len(picked) >= limit:
            break
        tag = a.get("tag") or "일반"
        if tag_count.get(tag, 0) >= max_per_tag:
            continue
        picked.append(a)
        tag_count[tag] = tag_count.get(tag, 0) + 1
    if len(picked) < limit:
        picked_urls = {a.get("url") for a in picked}
        for a in articles:
            if len(picked) >= limit:
                break
            if a.get("url") in picked_urls:
                continue
            picked.append(a)
            picked_urls.add(a.get("url"))
    return picked


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
    """여신 탭의 "오늘 신규 리드"와 항상 같은 숫자를 보여준다 —
    credit.today_summary.get_today_leads_summary() 하나로 계산을 단일화해
    화면마다(홈/여신 탭) 다른 건수가 표시되던 문제를 막는다."""
    summary = _safe("여신 오늘 신규 리드", get_today_leads_summary)
    if not summary or summary.get("pending"):
        return None
    count = summary.get("count") or 0
    if count == 0:
        return None
    ref_date = max(summary["dart_ref_date"], summary["news_ref_date"])
    return {
        "level": "info",
        "title": f"여신 신규 공시/뉴스 {count}건",
        "detail": f"{ref_date} 기준 · 상속·증여/우리사주 관련 신규 공시·뉴스",
        "tab": "credit",
    }


def _first_sentence(text: str) -> str:
    for sep in ("다.", "요.", "함.", "임."):
        idx = text.find(sep)
        if idx != -1:
            return text[: idx + len(sep)].strip()
    return text.strip()


def _market_briefing_key(briefing: dict | None) -> dict | None:
    """오늘의 핵심 1번 카드 — 오늘의 시장 브리핑의 "요약"을 헤드라인으로, 4개 카테고리
    각각의 첫 문장을 압축해 "왜 중요한가?" 자리에 보여준다(오늘의 시장 브리핑 섹션과
    같은 내용을 참고해 만들어, 아래로 스크롤하면 더 자세한 내용을 볼 수 있다)."""
    sections = (briefing or {}).get("sections") or {}
    headline = (briefing or {}).get("summary") or sections.get("주식")
    if not headline:
        return None
    rest = [f"{k}: {_first_sentence(sections[k])}" for k in CATEGORIES if sections.get(k)]
    return {"kind": "market", "title": headline, "detail": " ".join(rest) if rest else None}


def _market_related_article(articles: list[dict] | None) -> dict | None:
    """오늘의 시장 브리핑 하단 "관련 기사" — research.curate 가 이미 관련도순으로 골라둔
    기사 중 1건을 그대로 링크로 보여준다(새 수집·AI 호출 없이 기존 큐레이션 재사용)."""
    if not articles:
        return None
    a = articles[0]
    if not a.get("title") or not a.get("url"):
        return None
    return {"title": a["title"], "url": a["url"], "published": a.get("published")}


def get_home_summary() -> dict:
    policy = _safe("정책·규제", get_policy_digest)
    research = _safe("리서치·뉴스", get_research_digest)
    market = _safe("오늘의 시장 한눈에(국내)", get_market_snapshot)
    global_market = _safe("오늘의 시장 한눈에(해외·환율)", get_global_market_snapshot)
    market_history = _safe("시장 한눈에 1년 차트(국내)", get_market_history_1y)
    global_market_history = _safe("시장 한눈에 1년 차트(해외)", get_global_market_history_1y)
    market_briefing = _safe("오늘의 시장 브리핑", get_market_briefing)

    # "오늘의 핵심" — AI가 먼저 걸러준 최대 3건. 뉴스 feed가 아니라 우선순위 목록이라는
    # 인상을 주기 위해, 이미 계산해둔 실데이터 신호를 정해진 순서로 최대 3개까지만 채운다.
    # 1번은 항상 시장 브리핑 요약(있으면) — 나머지는 기존 우선순위(유동성 이상징후 →
    # 금융당국 발표 → 여신 신규 리드 → AI 선별 리서치 기사)로 남은 자리를 채운다.
    # 리서치 기사는 research.curate 가 이미 업무 관련도순으로 정렬·태깅·이유(reason)까지
    # 판단해둔 결과를 그대로 재사용한다(추가 Gemini 호출 없음).
    articles = research.get("articles") if research else None
    today_key: list[dict] = []
    market_key = _market_briefing_key(market_briefing)
    if market_key:
        today_key.append(market_key)
    liquidity_alert = _liquidity_alert()
    if liquidity_alert:
        today_key.append({"kind": "alert", **liquidity_alert})
    policy_highlight = _policy_highlight(policy)
    if policy_highlight:
        today_key.append(policy_highlight)
    credit_alert = _credit_leads_alert()
    if credit_alert:
        today_key.append({"kind": "alert", **credit_alert})
    for a in (articles or []):
        if len(today_key) >= _MAX_TODAY_KEY:
            break
        today_key.append({
            "kind": "research", "title": a.get("title"), "tag": a.get("tag"),
            "date": a.get("published"), "url": a.get("url"), "reason": a.get("reason"),
        })
    today_key = today_key[:_MAX_TODAY_KEY]

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
        "global_market": global_market,
        "market_history": market_history,
        "global_market_history": global_market_history,
        "market_briefing": {
            "sections": market_briefing.get("sections"),
            "summary": market_briefing.get("summary"),
            "note": market_briefing.get("note"),
            "generated_at": market_briefing.get("generated_at"),
            "related_article": _market_related_article(articles),
        } if market_briefing else None,
        "today_key": today_key,
        "today_news": _diversify_news(articles or [], _MAX_TODAY_NEWS, _MAX_PER_TAG_TODAY_NEWS),
    }
