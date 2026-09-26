"""오늘의 브리핑 > 오늘의 시장 브리핑 — 주식/채권/환율/장전(해외) 4개 카테고리.

이미 모아둔 실데이터 스냅샷(코스피·코스닥, 다우·나스닥·S&P500, 환율, 미국채10년)에 더해
최근 5거래일 누적 등락률·52주 최고/최저 대비 위치까지 텍스트로 정리해 Gemini에 넘기고,
Gemini는 그 수치 안에서만 근거를 찾아 문장으로 풀어쓴다(새 수치를 지어내지 않음).

main/app.py 의 새벽 배치(/internal/warmup)가 전영업일 마감 수치를 기준으로 하루 1회
생성해 스냅샷으로 캐시한다(policy/briefing.py, research/curate.py와 같은
read-modify-write 패턴). 배치가 아직 못 돌았다면 첫 방문자 요청 때 그때그때 생성한다.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from main.config import get_settings
from main.gemini import generate_text
from main.snapshot_store import get_snapshot, save_snapshot
from research.sources import search_news

from .market_snapshot import (
    get_global_market_history_1y,
    get_global_market_snapshot,
    get_market_history_1y,
    get_market_snapshot,
)

_TABLE = "market_briefing_snapshots"
logger = logging.getLogger(__name__)

# 카테고리별 "관련 기사" 검색어 — 한국 경제지에서 매 거래일 관행적으로 나오는 시황
# 기사 제목 패턴이라 실제 기사가 거의 매일 검색된다(없으면 그냥 링크를 비워둔다 —
# 실제로 없는 기사를 지어내지 않는다는 원칙).
_RELATED_QUERIES = {
    "주식": "코스피 마감",
    "채권": "미국채 금리",
    "환율": "원달러 환율",
    "장전": "뉴욕증시 마감",
}
KST = ZoneInfo("Asia/Seoul")

CATEGORIES = ["주식", "채권", "환율", "장전"]

_SYSTEM_PROMPT = (
    "너는 한국증권금융(KSFC) 임직원을 위한 시장 브리핑 어시스턴트야.\n"
    "아래에 전영업일 마감 기준 실데이터 수치(지수, 등락률, 거래대금, 최근 5거래일 누적 "
    "등락률, 52주 최고·최저 대비 위치 등)가 주어진다. 그 수치 안에서만 근거를 찾아 "
    "'주식'/'채권'/'환율'/'장전' 4개 카테고리로 각각 2~3문장, **160자 이내**로 "
    "구체적인 수치를 인용해 데이터 기반으로 작성해(단답형 한 문장 금지 — 당일 수준뿐 "
    "아니라 최근 흐름·맥락까지 함께 설명).\n"
    "- '주식'은 코스피·코스닥(거래대금 포함), '채권'은 미국채 10년물 금리, '환율'은 "
    "원/달러 등 환율, '장전'은 미국 3대 지수(다우·나스닥·S&P500) 전일 마감을 다룬다.\n"
    "- 숫자는 주어진 값만 그대로 인용하고 새로 지어내지 마라(추세·거래대금·52주 위치도 "
    "주어진 값만 사용). 상승/하락 방향과 흐름을 명확히 써라.\n"
    "- KSFC 업무 시사점 같은 부연 설명은 붙이지 말고 수치 사실만 전달해라.\n"
    "- 데이터가 없는 카테고리는 키 자체를 빼라(빈 문자열 금지).\n"
    "- 추가로 '요약' 키에 4개 카테고리를 통틀어 오늘 가장 눈에 띄는 사실 하나를 "
    "정확히 한 문장, 70자 이내로 적어라(카드 헤드라인용, 여러 카테고리를 나열하지 말고 "
    "가장 중요한 것 하나만).\n"
    '- 반드시 JSON으로만 답해: {"주식": "...", "채권": "...", "환율": "...", '
    '"장전": "...", "요약": "..."}'
)


def _today() -> str:
    return datetime.now(KST).date().isoformat()


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "-"
    return f"{'+' if v > 0 else ''}{v:.2f}%"


def _trend_pct(values: list[float] | None, days: int = 5) -> float | None:
    """최근 N거래일 누적 등락률(%) — values는 날짜 오름차순 종가 배열."""
    if not values or len(values) <= days:
        return None
    base = values[-days - 1]
    if not base:
        return None
    return round((values[-1] - base) / base * 100, 2)


def _range_position_pct(values: list[float] | None) -> tuple[float, float] | None:
    """52주 최고/최저 대비 현재 위치(%) — (최고 대비, 최저 대비)."""
    if not values or len(values) < 2:
        return None
    hi, lo, cur = max(values), min(values), values[-1]
    if not hi or not lo:
        return None
    return (round((cur - hi) / hi * 100, 2), round((cur - lo) / lo * 100, 2))


def _trend_pp(values: list[float] | None, days: int = 5) -> float | None:
    """최근 N거래일 변동폭(%p, 금리처럼 이미 %인 값에 사용) — values는 날짜 오름차순."""
    if not values or len(values) <= days:
        return None
    return round(values[-1] - values[-days - 1], 3)


def _index_line(label: str, idx: dict, hist: dict | None, turnover_label: str | None = None) -> str:
    bit = f"{label} {idx['close']} ({_fmt_pct(idx.get('change_pct'))})"
    if turnover_label and idx.get("turnover") is not None:
        bit += f", 거래대금 {idx['turnover']}조원"
    values = hist.get("values") if hist else None
    trend = _trend_pct(values)
    if trend is not None:
        bit += f", 최근5거래일 누적 {_fmt_pct(trend)}"
    rng = _range_position_pct(values)
    if rng:
        bit += f", 52주 최고 대비 {_fmt_pct(rng[0])}"
    return bit


def _bond_line(bond: dict, hist: dict | None) -> str:
    bit = f"미국채10년 금리 {bond['value']}% ({_fmt_pct(bond.get('change_pct'))})"
    values = hist.get("values") if hist else None
    trend = _trend_pp(values)
    if trend is not None:
        bit += f", 최근5거래일 {trend:+.2f}%p 변동"
    rng = _range_position_pct(values)
    if rng:
        bit += f", 52주 최고 대비 {rng[0]:+.2f}%p"
    return bit


def _build_prompt(market: dict | None, gm: dict | None, mh: dict | None, gh: dict | None) -> str | None:
    lines: list[str] = []
    mh_live = bool(mh and mh.get("source") == "live")
    gh_live = bool(gh and gh.get("source") == "live")

    if market and market.get("source") == "live":
        lines.append(_index_line("코스피", market["kospi"], mh_live and mh.get("kospi"), True))
        lines.append(_index_line("코스닥", market["kosdaq"], mh_live and mh.get("kosdaq"), True))

    if gm and gm.get("source") == "live":
        for idx in gm.get("us_indices") or []:
            lines.append(_index_line(idx["name"], idx, gh_live and gh.get(idx["name"])))
        for fx in gm.get("fx") or []:
            lines.append(f"{fx['name']} {fx['value']} ({_fmt_pct(fx.get('change_pct'))})")
        bond = gm.get("bond_us10y")
        if bond:
            lines.append(_bond_line(bond, gh_live and gh.get("bond_us10y")))

    if not lines:
        return None
    return "전영업일 마감 기준 시장 수치:\n" + "\n".join(lines)


def _parse(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[4:] if t[:4].lower() == "json" else t
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b < 0:
        raise ValueError("JSON 응답 없음")
    obj = json.loads(t[a : b + 1])
    sections = {k: obj[k] for k in CATEGORIES if obj.get(k)}
    summary = (obj.get("요약") or "").strip() or None
    return {"sections": sections, "summary": summary}


def _generate(market: dict | None, gm: dict | None, mh: dict | None, gh: dict | None) -> dict | None:
    prompt = _build_prompt(market, gm, mh, gh)
    if not prompt:
        return None
    text = generate_text(
        prompt + "\n\n위 수치를 바탕으로 오늘의 시장 브리핑을 작성해줘.",
        system_instruction=_SYSTEM_PROMPT, max_output_tokens=1024,
    )
    result = _parse(text)
    if not result["sections"]:
        raise ValueError("브리핑 파싱 결과 비어있음")
    return result


def _related_articles(sections: dict) -> dict:
    """카테고리별 "관련 기사" 1건씩 — Naver 뉴스에서 그 카테고리 검색어로 가장 최신
    기사를 찾아 링크만 붙인다(요약 재작성 없음, AI 호출 없음). 검색 결과가 없는
    카테고리는 그냥 빠진다."""
    out: dict = {}
    for key in sections:
        query = _RELATED_QUERIES.get(key)
        if not query:
            continue
        try:
            hits = search_news(query, days=2, limit=1)
        except Exception as exc:  # noqa: BLE001
            logger.warning("시장 브리핑 관련 기사 검색 실패(%s): %s", key, exc)
            continue
        if hits:
            h = hits[0]
            out[key] = {"title": h["title"], "url": h["url"], "published": h["published"]}
    return out


def _maybe_generate(payload: dict, force: bool = False) -> dict:
    s = get_settings()
    has = bool(payload.get("sections"))
    cap = s.policy_max_gemini_calls_per_day

    if has and not force:
        return payload
    if not s.gemini_api_keys:
        if not has:
            payload["note"] = "AI 브리핑은 GEMINI_API_KEY 등록 후 제공됩니다."
        return payload
    if payload.get("gemini_attempts", 0) >= cap:
        if not has:
            payload["note"] = f"AI 재시도 한도({cap}회)에 도달했습니다. 잠시 후 다시 시도해주세요."
        return payload

    payload["gemini_attempts"] = payload.get("gemini_attempts", 0) + 1
    market = get_market_snapshot()
    gm = get_global_market_snapshot()
    mh = get_market_history_1y()
    gh = get_global_market_history_1y()
    try:
        result = _generate(market, gm, mh, gh)
        payload["sections"] = result["sections"]
        payload["summary"] = result["summary"]
        payload["related_articles"] = _related_articles(result["sections"])
        payload["note"] = None
    except Exception as exc:  # noqa: BLE001
        logger.warning("시장 브리핑 생성 실패: %s", exc)
        if not has:
            payload["note"] = "브리핑에 쓸 시장 데이터를 아직 불러오지 못했습니다."
    return payload


def get_market_briefing(force: bool = False) -> dict:
    today = _today()
    snap = get_snapshot(_TABLE, today)
    if snap is not None:
        before = (snap.get("sections"), snap.get("gemini_attempts", 0))
        snap = _maybe_generate(snap, force=force)
        if (snap.get("sections"), snap.get("gemini_attempts", 0)) != before:
            save_snapshot(_TABLE, today, snap)
        return {**snap, "cached": not force}

    payload = {
        "date": today,
        "generated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "sections": None,
        "summary": None,
        "related_articles": None,
        "note": None,
        "gemini_attempts": 0,
    }
    payload = _maybe_generate(payload)
    save_snapshot(_TABLE, today, payload)
    return {**payload, "cached": False}
