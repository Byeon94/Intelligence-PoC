"""자본시장 > CMA > 증권사별 CMA 금리.

우선순위:
  1) 당일 AI 검색 스냅샷(Gemini + Google Search, cma_rate_snapshots) — 하루 1회 자동 갱신
  2) 가장 최근 AI 검색 스냅샷(stale)
  3) capital/cma_rates.json (사람이 관리하는 기준값·폴백)

공개 API가 없어 AI가 웹에서 조사한 값이므로 화면에 'AI 검색 기준'으로 표기한다.
AI 출력의 증권사명은 _COMPANIES 목록에 있는 것만 받는다(화면에 그대로 찍히므로).
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from main.config import get_settings
from main.daily_snapshot import parse_json_obj
from main.gemini import generate_text
from main.snapshot_store import get_snapshot, latest_snapshot, save_snapshot
from main.utils import today_iso

logger = logging.getLogger(__name__)
_PATH = Path(__file__).with_name("cma_rates.json")
_TABLE = "cma_rate_snapshots"

_COMPANIES = [
    "한국투자증권", "KB증권", "NH투자증권", "미래에셋증권", "삼성증권", "신한투자증권",
    "키움증권", "하나증권", "대신증권", "메리츠증권", "유안타증권", "SK증권",
]

_PROMPT = (
    "국내 주요 증권사의 현재 CMA 금리를 웹에서 조사해줘.\n"
    "- 'RP형 CMA'와 '발행어음형 CMA'의 세전 연 수익률(기본 금리, 대량예치·이벤트 우대 제외).\n"
    f"- 대상 증권사: {', '.join(_COMPANIES)}\n"
    "- 발행어음형은 발행어음 인가 증권사(한국투자증권·KB증권·NH투자증권 등)만 값이 있고 나머지는 null.\n"
    "- 확인이 안 되는 값은 null. 추정하지 말 것.\n"
    "설명 없이 아래 JSON만 출력:\n"
    '{"as_of": "YYYY-MM-DD", "companies": [{"company": "한국투자증권", "rp_rate": 3.05, "note_rate": 3.35}]}'
)


def _load_json() -> dict:
    with _PATH.open(encoding="utf-8") as fp:
        return json.load(fp)


def _known_company(raw) -> str | None:
    """AI가 돌려준 증권사명을 _COMPANIES 표기로 맞춘다('NH투자증권(나무)' → 'NH투자증권').
    목록에 없는 이름은 None — 임의 문자열이 화면에 찍히지 않게 한다."""
    name = str(raw or "").strip()
    if name in _COMPANIES:
        return name
    # 긴 이름부터 봐야 '신한투자증권'이 다른 이름의 부분문자열에 먼저 걸리지 않는다
    for known in sorted(_COMPANIES, key=len, reverse=True):
        if known in name:
            return known
    return None


def _norm(companies: list[dict]) -> list[dict]:
    out = []
    seen: set[str] = set()
    for c in companies:
        if not isinstance(c, dict):
            continue
        name = _known_company(c.get("company"))
        if not name or name in seen:
            continue
        rp = c.get("rp_rate")
        note = c.get("note_rate")
        try:
            rp = round(float(rp), 2) if rp is not None else None
        except (TypeError, ValueError):
            rp = None
        try:
            note = round(float(note), 2) if note is not None else None
        except (TypeError, ValueError):
            note = None
        if rp is None and note is None:
            continue
        seen.add(name)
        out.append({"company": name, "rp_rate": rp, "note_rate": note})
    out.sort(key=lambda c: (c["rp_rate"] is None, -(c["rp_rate"] or 0)))
    return out


def _ai_fetch() -> dict:
    from google.genai import types

    text = generate_text(
        _PROMPT,
        tools=[types.Tool(google_search=types.GoogleSearch())],
        max_output_tokens=2048,
    )
    obj = parse_json_obj(text)
    companies = _norm(obj.get("companies") or [])
    if len(companies) < 4:
        raise ValueError("유효 항목 부족")
    return {
        "as_of": str(obj.get("as_of") or today_iso())[:10],
        "companies": companies,
        "note": "AI가 웹에서 조사한 값입니다. 정확한 금리는 각 증권사 공시를 확인하세요.",
        "source": "ai_search",
    }


def _curated() -> dict:
    data = _load_json()
    companies = _norm(data.get("companies", []))
    return {
        "as_of": data.get("as_of"),
        "companies": companies,
        "note": data.get("note"),
        "source": "curated",
    }


_attempted: set[str] = set()  # 프로세스 내에서 AI 조사를 시도한 날짜
_attempted_lock = threading.Lock()


def _claim_attempt(today: str) -> bool:
    """오늘 첫 시도권을 얻으면 True. 동시 요청(gthread)이 둘 다 Gemini를 부르지 않게 락으로 확인·기록."""
    with _attempted_lock:
        if today in _attempted:
            return False
        _attempted.add(today)
        return True


def _checked(snap: dict | None) -> dict | None:
    """저장된 스냅샷도 증권사명 검증을 다시 거친다(검증 도입 전 저장분 대비)."""
    if not snap or not snap.get("companies"):
        return None
    companies = _norm(snap["companies"])
    return {**snap, "companies": companies} if companies else None


def rate_table() -> dict:
    today = today_iso()

    snap = _checked(get_snapshot(_TABLE, today))
    if snap:
        return snap

    s = get_settings()
    if s.gemini_api_keys and _claim_attempt(today):
        # 성공하면 스냅샷으로 캐시되고, 실패해도 이 프로세스에선 오늘 재시도 안 함
        try:
            result = _ai_fetch()
            save_snapshot(_TABLE, today, result)
            return result
        except Exception as exc:  # noqa: BLE001
            logger.info("CMA 금리 AI 조사 실패 → 큐레이션/이전값 사용: %s", exc)

    stale = _checked(latest_snapshot(_TABLE))
    if stale:
        return {**stale, "stale": True}
    return _curated()


def top_rp_rate() -> dict:
    """RP형 최고금리 1건 + 그 값의 출처(rate_table 의 source: ai_search/curated)."""
    table = rate_table()
    companies = [c for c in table["companies"] if c.get("rp_rate") is not None]
    if not companies:
        return {"rate": None, "company": None, "source": table.get("source")}
    top = max(companies, key=lambda c: c["rp_rate"])
    return {"rate": top["rp_rate"], "company": top["company"], "source": table.get("source")}
