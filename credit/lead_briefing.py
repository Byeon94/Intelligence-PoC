"""여신·심사 메인 화면 — 증권담보대출/우리사주 리드에 대한 AI 브리핑.

get_leads()(DART 상속·증여·유상증자·IPO 리드)와 get_inherit_news()(상속·증여 관련
뉴스, AI 관련도 판단 완료)의 결과물을 다시 Gemini에 넣어, "최근 동향 + 당사가 대출
영업 확대를 위해 고려할 점"을 불릿 3개로 요약한다.

두 소스 모두 이미 하루 1회 캐시돼 있어 빠르게 준비되므로, 이 브리핑 자체도 하루 1회만
생성해 캐시한다(스냅샷 재사용). 입력 데이터에 없는 회사명·금액·수치는 지어내지 않도록
프롬프트로 제약한다(정책·리서치 브리핑과 동일한 원칙).
"""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from main.config import get_settings
from main.gemini import generate_text
from main.snapshot_store import get_snapshot, save_snapshot

from .inherit_news import get_inherit_news
from .leads import get_leads

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

_TABLE = "credit_lead_briefing_snapshots"

_COLLATERAL_SYSTEM_PROMPT = (
    "너는 한국증권금융(KSFC) 여신심사 담당자를 위한 브리핑 어시스턴트야.\n"
    "아래는 최근 60일 내 상속·증여 관련 ①월별 건수 ②DART 공시 목록 ③관련 뉴스(AI가 "
    "관련 있다고 판단한 것만)다.\n"
    "이 데이터만 근거로 최근 상속·증여 동향(월별 증감 포함)과, 당사가 증권담보대출 영업을 "
    "확대하려면 무엇을 고려해야 하는지 불릿 3개로 정리해.\n"
    "- 각 불릿은 '- '로 시작하는 한 문장, 100자 이내. 수식어·부연 없이.\n"
    "- 목록에 없는 회사명·금액·지분율·날짜를 지어내지 마.\n"
    "- DART 공시가 없고 뉴스만 있으면 '공시 기준 신규 리드는 없지만 언론 보도로는…' 식으로 "
    "그 사실을 그대로 반영해. 데이터가 아예 없으면 '최근 특이 동향 없음'과 함께 상속·증여세 "
    "재원 마련용 증권담보대출은 통상 시차를 두고 발생한다는 일반적 시사점만 제시해.\n"
    "- 소제목(#)·구분선(---)·서두·출처 표기 없이 불릿 3개만 출력."
)

_ESOP_SYSTEM_PROMPT = (
    "너는 한국증권금융(KSFC) 여신심사 담당자를 위한 브리핑 어시스턴트야.\n"
    "아래는 최근 60일 내 유상증자·IPO(신규상장 공모) 관련 DART 공시 목록과 월별 건수다.\n"
    "이 데이터만 근거로 최근 유상증자·IPO 동향과, 당사가 우리사주 취득자금대출 영업을 "
    "확대하려면 무엇을 고려해야 하는지 불릿 3개로 정리해.\n"
    "- 각 불릿은 '- '로 시작하는 한 문장, 100자 이내. 수식어·부연 없이.\n"
    "- 목록에 없는 회사명·금액·배정비율·날짜를 지어내지 마.\n"
    "- 자본시장법상 우리사주조합 우선배정 한도는 공모·유상증자 물량의 20%라는 일반 "
    "규정은 활용해도 되지만, 특정 건의 실제 배정 비율은 공시 원문 확인이 필요하다고만 해.\n"
    "- 소제목(#)·구분선(---)·서두·출처 표기 없이 불릿 3개만 출력."
)


def _collateral_monthly_with_news(collateral: list[dict], news: list[dict]) -> list[dict]:
    """DART 건수(월별)에 뉴스 건수(월별)를 합쳐, 우리사주 프롬프트와 같은 형태로 만든다."""
    counts: dict[str, dict[str, int]] = {}
    for it in collateral:
        m = it["date"][:7]
        counts.setdefault(m, {"dart": 0, "news": 0})["dart"] += 1
    for n in news:
        pub = n.get("published") or ""
        if len(pub) < 7:
            continue
        m = pub[:7]
        counts.setdefault(m, {"dart": 0, "news": 0})["news"] += 1
    return [{"month": m, "dart": counts[m]["dart"], "news": counts[m]["news"]}
            for m in sorted(counts, reverse=True)]


def _collateral_prompt(collateral: list[dict], news: list[dict]) -> str:
    monthly = _collateral_monthly_with_news(collateral, news)
    lines = ["[월별 건수]"]
    if monthly:
        for m in monthly[:3]:
            lines.append(f"- {m['month']}: DART 공시 {m['dart']}건, 관련 뉴스 {m['news']}건")
    else:
        lines.append("- (해당 없음)")
    lines.append("\n[DART 공시]")
    if collateral:
        for it in collateral[:20]:
            lines.append(f"- {it['date']} {it['name']} — 보고사유 '{it['reason']}'")
    else:
        lines.append("- (해당 없음)")
    lines.append("\n[관련 뉴스]")
    if news:
        for n in news[:10]:
            lines.append(f"- {n['published']} {n['title']} — {n.get('ai_note', '')}")
    else:
        lines.append("- (해당 없음)")
    return "\n".join(lines)


def _esop_prompt(esop: list[dict], monthly: list[dict]) -> str:
    lines = ["[월별 건수]"]
    for m in monthly[:3]:
        lines.append(f"- {m['month']}: 유상증자 {m['rights']}건, IPO {m['ipo']}건")
    lines.append("\n[최근 공시]")
    if esop:
        for it in esop[:20]:
            tag = "IPO" if it["category"] == "ipo" else "유상증자"
            lines.append(f"- {it['date']} [{tag}] {it['name']} — {it['title']}")
    else:
        lines.append("- (해당 없음)")
    return "\n".join(lines)


def _bullets_from(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        line = line.strip().lstrip("-•*").strip()
        if line:
            out.append(line)
    return out[:3]


_SCHEMA_V = 2  # v2: 브리핑 2종(담보대출/우리사주) 각각 gemini_attempts 재시도 상한 추가.
                # 이전엔 단일 시도만 하고 실패하면 그날 내내 빈 브리핑으로 굳었다
                # (research/policy 등 다른 AI 브리핑과 동일한 문제, 2026-09-22 확인).


def _maybe_generate(payload: dict, leads: dict, news: list[dict], force: bool = False) -> dict:
    """브리핑이 비어 있으면(또는 force=True 면) 항목별로 일일 한도 내에서 한 번 더 시도.

    담보대출·우리사주 브리핑을 독립적으로 재시도한다(한쪽만 실패했을 때 성공한
    쪽까지 다시 만들지 않도록).
    """
    s = get_settings()
    cap = s.policy_max_gemini_calls_per_day
    attempts = payload.setdefault("gemini_attempts", {"collateral": 0, "esop": 0})

    if s.gemini_api_keys and (force or not payload.get("collateral_briefing")) and attempts["collateral"] < cap:
        attempts["collateral"] += 1
        try:
            text = generate_text(
                _collateral_prompt(leads.get("collateral", []), news),
                system_instruction=_COLLATERAL_SYSTEM_PROMPT, max_output_tokens=1024,
            )
            payload["collateral_briefing"] = _bullets_from(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("증권담보대출 리드 AI 브리핑 생성 실패(%d/%d회): %s", attempts["collateral"], cap, exc)

    if s.gemini_api_keys and (force or not payload.get("esop_briefing")) and attempts["esop"] < cap:
        attempts["esop"] += 1
        try:
            text = generate_text(
                _esop_prompt(leads.get("esop", []), leads.get("esop_monthly", [])),
                system_instruction=_ESOP_SYSTEM_PROMPT, max_output_tokens=1024,
            )
            payload["esop_briefing"] = _bullets_from(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("우리사주 리드 AI 브리핑 생성 실패(%d/%d회): %s", attempts["esop"], cap, exc)

    return payload


def get_lead_briefings(force: bool = False) -> dict:
    today = datetime.now(KST).date().isoformat()
    snap = get_snapshot(_TABLE, today)
    if snap is not None and snap.get("v") != _SCHEMA_V:
        snap = None
    if snap is None:
        snap = {"v": _SCHEMA_V, "collateral_briefing": [], "esop_briefing": []}

    leads = get_leads()
    try:
        news = get_inherit_news().get("items", [])
    except Exception:  # noqa: BLE001
        news = []

    before = (snap.get("collateral_briefing"), snap.get("esop_briefing"), dict(snap.get("gemini_attempts") or {}))
    snap = _maybe_generate(snap, leads, news, force=force)
    after = (snap.get("collateral_briefing"), snap.get("esop_briefing"), dict(snap.get("gemini_attempts") or {}))
    if after != before:
        save_snapshot(_TABLE, today, snap)
    return snap
