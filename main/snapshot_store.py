"""정책/규제 · 리서치/뉴스 일일 스냅샷 저장소.

우선순위: Supabase(테이블) → 실패/미설정 시 프로세스 메모리(임시).
스냅샷 1건 = 그날 수집한 원자료 + AI 산출물을 통째로 담은 payload.
"""
from __future__ import annotations

import logging

from main.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

_mem: dict[str, dict] = {}          # "<table>:<date>" → payload
_save_warned: set[str] = set()      # 테이블별 저장 실패 경고 1회만


def _key(table: str, date_iso: str) -> str:
    return f"{table}:{date_iso}"


def get_snapshot(table: str, date_iso: str) -> dict | None:
    client = get_supabase_client()
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
    return _mem.get(_key(table, date_iso))  # 미설정·빈결과·오류 → 메모리


def save_snapshot(table: str, date_iso: str, payload: dict) -> None:
    _mem[_key(table, date_iso)] = payload   # 항상 메모리에 우선 보관
    client = get_supabase_client()
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
    client = get_supabase_client()
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
    mem_keys = [k for k in _mem if k.startswith(f"{table}:")]
    return _mem[max(mem_keys)] if mem_keys else None
