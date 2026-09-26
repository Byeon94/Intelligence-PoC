"""오늘의 브리핑 > 오늘의 시장 브리핑 — 주식/채권/환율/장전(해외) 4개 카테고리.

이미 모아둔 실데이터 스냅샷(코스피·코스닥, 다우·나스닥·S&P500, 환율, 미국채10년)을
텍스트로 정리해 Gemini에 넘기고, Gemini는 그 수치 안에서만 근거를 찾아 문장으로
풀어쓴다(새 수치를 지어내지 않음). 하루 1회만 생성하고 스냅샷으로 캐시한다
(policy/briefing.py, research/curate.py와 같은 read-modify-write 패턴).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from main.config import get_settings
from main.gemini import generate_text
from main.snapshot_store import get_snapshot, save_snapshot

from .market_snapshot import get_global_market_snapshot, get_market_snapshot

_TABLE = "market_briefing_snapshots"
logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

CATEGORIES = ["주식", "채권", "환율", "장전"]

_SYSTEM_PROMPT = (
    "너는 한국증권금융(KSFC) 임직원을 위한 시장 브리핑 어시스턴트야.\n"
    "아래에 오늘 기준 실데이터 수치가 주어진다. 그 수치 안에서만 근거를 찾아 "
    "'주식'/'채권'/'환율'/'장전' 4개 카테고리로 각각 정확히 한 문장, **70자 이내**로 "
    "간결하게 작성해(카드 UI에 그대로 들어가므로 길게 늘어놓지 마라).\n"
    "- '주식'은 코스피·코스닥, '채권'은 미국채 10년물 금리, '환율'은 원/달러 등 환율,\n"
    "  '장전'은 미국 3대 지수(다우·나스닥·S&P500) 전일 마감을 다룬다.\n"
    "- 숫자는 주어진 값만 그대로 인용하고 새로 지어내지 마라. 상승/하락 방향을 명확히 써라.\n"
    "- KSFC 업무 시사점 같은 부연 설명은 붙이지 말고 수치 사실만 한 문장으로 전달해라.\n"
    "- 데이터가 없는 카테고리는 키 자체를 빼라(빈 문자열 금지).\n"
    '- 반드시 JSON으로만 답해: {"주식": "...", "채권": "...", "환율": "...", "장전": "..."}'
)


def _today() -> str:
    return datetime.now(KST).date().isoformat()


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "-"
    return f"{'+' if v > 0 else ''}{v:.2f}%"


def _build_prompt(market: dict | None, gm: dict | None) -> str | None:
    lines: list[str] = []
    if market and market.get("source") == "live":
        lines.append(f"코스피 {market['kospi']['close']} ({_fmt_pct(market['kospi']['change_pct'])})")
        lines.append(f"코스닥 {market['kosdaq']['close']} ({_fmt_pct(market['kosdaq']['change_pct'])})")
    if gm and gm.get("source") == "live":
        for idx in gm.get("us_indices") or []:
            lines.append(f"{idx['name']} {idx['close']} ({_fmt_pct(idx['change_pct'])})")
        for fx in gm.get("fx") or []:
            lines.append(f"{fx['name']} {fx['value']} ({_fmt_pct(fx['change_pct'])})")
        bond = gm.get("bond_us10y")
        if bond:
            lines.append(f"미국채10년 금리 {bond['value']}% ({_fmt_pct(bond['change_pct'])})")
    if not lines:
        return None
    return "오늘 시장 수치:\n" + "\n".join(lines)


def _parse(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[4:] if t[:4].lower() == "json" else t
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b < 0:
        raise ValueError("JSON 응답 없음")
    obj = json.loads(t[a : b + 1])
    return {k: obj[k] for k in CATEGORIES if obj.get(k)}


def _generate(market: dict | None, gm: dict | None) -> dict | None:
    prompt = _build_prompt(market, gm)
    if not prompt:
        return None
    text = generate_text(
        prompt + "\n\n위 수치를 바탕으로 오늘의 시장 브리핑을 작성해줘.",
        system_instruction=_SYSTEM_PROMPT, max_output_tokens=768,
    )
    sections = _parse(text)
    if not sections:
        raise ValueError("브리핑 파싱 결과 비어있음")
    return sections


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
    try:
        sections = _generate(market, gm)
        payload["sections"] = sections
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
        "note": None,
        "gemini_attempts": 0,
    }
    payload = _maybe_generate(payload)
    save_snapshot(_TABLE, today, payload)
    return {**payload, "cached": False}
