"""증권사별 CMA 금리.

우선순위:
  1) 당일 AI 검색 스냅샷(Gemini + Google Search, DB 캐시) — 하루 1회 자동 갱신
  2) capital/cma_rates.json (사람이 관리하는 기준값·폴백)

공개 API가 없어 AI가 웹에서 조사한 값이므로 화면에 'AI 검색 기준'으로 표기한다.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from main.config import get_settings
from main.snapshot_store import get_snapshot, latest_snapshot, save_snapshot

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")
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


def _norm(companies: list[dict]) -> list[dict]:
    out = []
    for c in companies:
        name = (c.get("company") or "").strip()
        if not name:
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
        out.append({"company": name, "rp_rate": rp, "note_rate": note})
    out.sort(key=lambda c: (c["rp_rate"] is None, -(c["rp_rate"] or 0)))
    return out


def _ai_fetch() -> dict:
    from google.genai import Client, types
    from google.genai import errors as genai_errors

    s = get_settings()
    keys = list(s.gemini_api_keys)
    if not keys:
        raise RuntimeError("GEMINI_API_KEY 미설정")

    last_err: Exception | None = None
    for i, key in enumerate([Client(api_key=k) for k in keys]):
        try:
            resp = key.models.generate_content(
                model=s.gemini_model,
                config={
                    "tools": [types.Tool(google_search=types.GoogleSearch())],
                    "max_output_tokens": 2048,
                },
                contents=_PROMPT,
            )
            text = (resp.text or "").strip()
            a, b = text.find("{"), text.rfind("}")
            if a < 0 or b < 0:
                raise ValueError("JSON 응답 없음")
            obj = json.loads(text[a : b + 1])
            companies = _norm(obj.get("companies") or [])
            if len(companies) < 4:
                raise ValueError("유효 항목 부족")
            return {
                "as_of": (obj.get("as_of") or datetime.now(KST).date().isoformat())[:10],
                "companies": companies,
                "note": "AI가 웹에서 조사한 값입니다. 정확한 금리는 각 증권사 공시를 확인하세요.",
                "source": "ai_search",
            }
        except genai_errors.APIError as exc:
            last_err = exc
            if getattr(exc, "code", None) == 429 and i < len(keys) - 1:
                continue
            raise
    raise last_err or RuntimeError("CMA 금리 AI 조사 실패")


def _curated() -> dict:
    data = _load_json()
    companies = _norm(data.get("companies", []))
    return {
        "as_of": data.get("as_of"),
        "companies": companies,
        "note": data.get("note"),
        "source": "curated",
    }


_attempted: set[str] = set()  # 프로세스 내에서 오늘 AI 조사 시도했는지


def rate_table() -> dict:
    today = datetime.now(KST).date().isoformat()

    snap = get_snapshot(_TABLE, today)
    if snap and snap.get("companies"):
        return snap

    s = get_settings()
    if s.gemini_api_keys and today not in _attempted:
        _attempted.add(today)  # 성공하면 스냅샷으로 캐시되고, 실패해도 이 프로세스에선 재시도 안 함
        try:
            result = _ai_fetch()
            save_snapshot(_TABLE, today, result)
            return result
        except Exception as exc:  # noqa: BLE001
            logger.info("CMA 금리 AI 조사 실패 → 큐레이션/이전값 사용: %s", exc)

    stale = latest_snapshot(_TABLE)
    if stale and stale.get("companies"):
        return {**stale, "stale": True}
    return _curated()


def top_rp_rate() -> dict:
    companies = [c for c in rate_table()["companies"] if c.get("rp_rate") is not None]
    if not companies:
        return {"rate": None, "company": None}
    top = max(companies, key=lambda c: c["rp_rate"])
    return {"rate": top["rp_rate"], "company": top["company"]}
