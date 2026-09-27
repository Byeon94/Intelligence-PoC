"""자본시장 > CMA > 증권사별 CMA 금리 — 증권사 공식 홈페이지 기준(네이버페이 CMA 비교 20개사 중 17곳).

매일 05:00 KST 새벽 배치(/internal/warmup 의 "CMA 금리")가 각 증권사 CMA 안내 페이지를 읽어
(capital/cma_firms.py) 그날 스냅샷(cma_rate_snapshots)으로 저장하고, 화면은 그 스냅샷만 읽는다.
오늘 스냅샷이 없으면(배치 실패·재배포 직후) 첫 화면 요청이 한 번 대신 수집한다.

증권사 한 곳의 파서가 실패하면(사이트 개편 등) 직전 스냅샷의 그 회사 값을 "이전값"으로 쓰고,
그마저 없으면 금리 없이 "확인 불가"로 둔다 — 추정·AI 검색값은 쓰지 않는다.
(예전 Gemini+구글 검색 방식은 날마다 값이 크게 흔들려 2026-09-27 이 방식으로 교체했다.)
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from main.daily_snapshot import table_lock
from main.snapshot_store import get_snapshot, latest_snapshot, save_snapshot
from main.utils import stamp, today_iso

from .cma_firms import FIRMS, fetch_firm

logger = logging.getLogger(__name__)
_TABLE = "cma_rate_snapshots"
_SOURCE = "official"
_NOTE = ("네이버페이 CMA 비교에 나오는 20개 증권사 중 공식 홈페이지에서 금리를 확인할 수 있는 17개사입니다"
         "(신영증권·케이프투자증권·메리츠증권은 사이트 조회 제한으로 제외). 각 사 CMA 안내 페이지에서 매일 새벽 확인한 "
         "개인 기본 금리(세전 연 %, 대량예치·이벤트 우대 제외)이며, 미래에셋증권은 일반 CMA와 네이버통장을 따로 표시합니다. "
         "기준일은 증권사가 페이지에 적은 날짜이며, 정확한 조건은 각 사 안내를 확인하세요.")


def _fetch_one(firm: tuple) -> dict:
    name, fn, link = firm
    key = fn.__name__ if fn else name   # 같은 증권사의 상품 여러 개(미래에셋 일반·네이버통장)를 구분
    if fn is None:
        return {"key": key, "company": name, "ok": False, "url": link}
    try:
        return {"key": key, "company": name, "ok": True, **fetch_firm(fn)}
    except Exception as exc:  # noqa: BLE001 - 한 곳 실패가 나머지를 막지 않게
        logger.warning("CMA 금리 파싱 실패(%s): %s", key, type(exc).__name__)
        return {"key": key, "company": name, "ok": False, "url": link, "error": _reason(exc)}


def _reason(exc: Exception) -> str:
    """실패 사유(진단용) — 'HTTP 403', 'ConnectTimeout', 'ValueError' 등. URL·키 같은 내부 정보는 담지 않는다."""
    resp = getattr(exc, "response", None)
    if resp is not None and getattr(resp, "status_code", None):
        return f"HTTP {resp.status_code}"
    return type(exc).__name__


def _expected_keys() -> set[str]:
    return {fn.__name__ if fn else name for name, fn, _ in FIRMS}


def _collect(prev: dict | None) -> dict:
    with ThreadPoolExecutor(max_workers=5) as ex:
        results = list(ex.map(_fetch_one, FIRMS))
    prev_by = {c.get("key") or c["company"]: c for c in (prev or {}).get("companies") or []
               if c.get("rp_rate") is not None or c.get("note_rate") is not None}
    companies = []
    for r in results:
        if r["ok"]:
            companies.append({k: r.get(k) for k in ("key", "company", "product", "rp_rate", "note_rate", "as_of", "url")}
                             | {"stale": False})
        elif r["key"] in prev_by:   # 오늘 못 읽었으면 직전 확인값
            companies.append({**prev_by[r["key"]], "stale": True})
        else:
            companies.append({"key": r["key"], "company": r["company"], "rp_rate": None, "note_rate": None,
                              "as_of": None, "url": r.get("url"), "stale": False, "unavailable": True})
    companies.sort(key=lambda c: (c["rp_rate"] is None, -(c["rp_rate"] or 0)))
    failed = [{"key": r["key"], "company": r["company"], "error": r.get("error") or "파서 없음"}
              for r in results if not r["ok"]]
    return {"as_of": today_iso(), "checked_at": stamp(), "companies": companies,
            "ok_count": sum(1 for r in results if r["ok"]), "total": len(results), "failed": failed,
            "note": _NOTE, "source": _SOURCE}


def _official(snap: dict | None) -> dict | None:
    """예전 AI 검색 스냅샷(source=ai_search)은 무시한다."""
    return snap if snap and snap.get("source") == _SOURCE else None


def rate_table(force: bool = False) -> dict:
    """force=True 는 새벽 배치용(오늘 스냅샷이 있어도 다시 확인)."""
    today = today_iso()
    with table_lock(_TABLE):
        snap = _official(get_snapshot(_TABLE, today))
        # 대상 증권사 목록이 코드에서 바뀌었으면(배포 직후) 오늘 저장본이 있어도 다시 확인한다
        same_set = bool(snap) and {c.get("key") for c in snap.get("companies") or []} == _expected_keys()
        if snap and same_set and not force:
            return snap
        prev = snap or _official(latest_snapshot(_TABLE))
        fresh = _collect(prev)
        if fresh["ok_count"] == 0:
            # 전부 실패(네트워크 장애 등) — 저장하지 않고 직전 스냅샷 유지
            logger.warning("CMA 금리: 모든 증권사 확인 실패 — 이전 스냅샷 유지")
            if prev:
                return {**prev, "stale": True}
            return fresh
        save_snapshot(_TABLE, today, fresh)
        return fresh


def top_rp_rate() -> dict:
    """RP형 최고금리 1건(이전값 포함, 확인 불가 제외)."""
    table = rate_table()
    companies = [c for c in table["companies"] if c.get("rp_rate") is not None]
    if not companies:
        return {"rate": None, "company": None, "source": table.get("source")}
    top = max(companies, key=lambda c: c["rp_rate"])
    return {"rate": top["rp_rate"], "company": top["company"], "source": table.get("source")}
