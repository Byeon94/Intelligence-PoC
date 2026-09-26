"""일일 스냅샷 저장소 — 정책·뉴스·IT뉴스·발행시장·CMA·시장 브리핑·여신 리드 등 모든 탭 공용.

우선순위: Supabase(테이블) → 미설정·설정 오류·조회 실패 시 프로세스 메모리(임시).
스냅샷 1건 = 그날 수집한 원자료 + AI 산출물을 통째로 담은 payload(테이블별 snapshot_date 1행).

- 조회 결과는 항상 깊은 복사본을 돌려준다. 호출자가 payload 를 제자리에서 고쳐도
  (gthread 4스레드) 메모리 캐시의 원본이 다른 스레드와 공유·오염되지 않게 하기 위함.
- 메모리 캐시는 테이블마다 최근 _MEM_KEEP_DATES 개 날짜만 남긴다(장기 구동 시 무한 증가 방지).
- 동시 수집 방지(조회→수집→저장 원자성)는 여기서 하지 않는다 — main.daily_snapshot.table_lock 참고.
"""
from __future__ import annotations

import copy
import logging
import threading

from main.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

_MEM_KEEP_DATES = 3                         # 테이블별 메모리에 남길 최근 날짜 수
_mem: dict[str, dict[str, dict]] = {}       # table → {date_iso → payload}
_mem_lock = threading.Lock()
_save_warned: set[str] = set()              # 테이블별 저장 실패 경고 1회만
_client_warned = False


def _client():
    """Supabase 클라이언트. 설정이 잘못돼 생성 자체가 실패해도 None(메모리 폴백)."""
    global _client_warned
    try:
        return get_supabase_client()
    except Exception as exc:  # noqa: BLE001
        if not _client_warned:
            logger.warning("Supabase 클라이언트 생성 실패 → 메모리 저장으로 대체: %s", exc)
            _client_warned = True
        return None


def _mem_get(table: str, date_iso: str | None = None) -> dict | None:
    with _mem_lock:
        rows = _mem.get(table) or {}
        if not rows:
            return None
        payload = rows.get(date_iso) if date_iso else rows[max(rows)]
        return copy.deepcopy(payload) if payload is not None else None


def _mem_put(table: str, date_iso: str, payload: dict) -> None:
    with _mem_lock:
        rows = _mem.setdefault(table, {})
        rows[date_iso] = copy.deepcopy(payload)
        for old in sorted(rows)[:-_MEM_KEEP_DATES]:
            del rows[old]


def get_snapshot(table: str, date_iso: str) -> dict | None:
    client = _client()
    if client is not None:
        try:
            resp = (
                client.table(table)
                .select("payload")
                .eq("snapshot_date", date_iso)
                .limit(1)
                .execute()
            )
            rows = resp.data or []
            if rows:
                return rows[0]["payload"]
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s] 스냅샷 조회 실패(%s): %s", table, date_iso, exc)
    return _mem_get(table, date_iso)  # 미설정·빈결과·오류 → 메모리


def save_snapshot(table: str, date_iso: str, payload: dict) -> None:
    _mem_put(table, date_iso, payload)   # 항상 메모리에 우선 보관
    client = _client()
    if client is None:
        return
    try:
        client.table(table).upsert(
            {"snapshot_date": date_iso, "payload": payload},
            on_conflict="snapshot_date",
        ).execute()
    except Exception as exc:  # noqa: BLE001
        if table not in _save_warned:
            logger.warning(
                "[%s] Supabase 저장 실패 → 메모리로 대체. RLS 정책 또는 service_role 키를 확인하세요: %s",
                table, exc,
            )
            _save_warned.add(table)


def latest_snapshot(table: str) -> dict | None:
    client = _client()
    if client is not None:
        try:
            resp = (
                client.table(table)
                .select("payload")
                .order("snapshot_date", desc=True)
                .limit(1)
                .execute()
            )
            rows = resp.data or []
            if rows:
                return rows[0]["payload"]
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s] 최근 스냅샷 조회 실패: %s", table, exc)
    return _mem_get(table)
