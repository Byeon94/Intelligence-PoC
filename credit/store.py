"""여신 기업분석: 종목별 '오늘자' 스냅샷 캐시.

목적: 같은 종목을 하루 안에 다시 조회하면 외부 API(data.go.kr·DART·네이버)를
      재호출하지 않고 저장본을 돌려준다. (API 호출 수 제한 대응)

계층
  L1 프로세스 메모리(_mem)         — 오늘(KST)자 항목만 보관(날짜가 바뀌면 지난 항목 정리)
  L2 Supabase equity_snapshots    — 워커 공유 + 하루 유지 (schema.sql 참고)
둘 다 없으면 호출부가 실데이터를 만들어 save_cached() 한다. sample 폴백은 저장하지 않는다.
"""
from __future__ import annotations

import logging

from main.supabase_client import get_supabase_client
from main.utils import today_iso

logger = logging.getLogger(__name__)

_TABLE = "equity_snapshots"
_mem: dict[str, dict] = {}          # "<date>:<code>" → {"basics": {...}, "financials": {...}, ...}
_warned = False                     # 저장 실패 경고 1회
_read_warned = False                # 조회 실패 경고 1회


def _key(date_iso: str, code: str) -> str:
    return f"{date_iso}:{code}"


def _remember(date_iso: str, k: str, row: dict) -> None:
    """L1 에 저장하면서 다른 날짜 항목은 버린다 — 날짜별 키가 끝없이 쌓이지 않도록."""
    prefix = f"{date_iso}:"
    for old in [x for x in _mem if not x.startswith(prefix)]:
        _mem.pop(old, None)
    _mem[k] = row


def _row(date_iso: str, code: str) -> dict:
    """오늘자 종목 행 전체({kind: payload})를 L1→L2 순으로 조회."""
    k = _key(date_iso, code)
    if k in _mem:
        return _mem[k]
    client = get_supabase_client()
    if client is not None:
        try:
            resp = (
                client.table(_TABLE)
                .select("payload")
                .eq("snapshot_date", date_iso)
                .eq("code", code)
                .limit(1)
                .execute()
            )
            rows = resp.data or []
            if rows:
                _remember(date_iso, k, rows[0]["payload"] or {})
                return _mem[k]
        except Exception as exc:  # noqa: BLE001
            global _read_warned
            if not _read_warned:
                logger.warning(
                    "[equity] 스냅샷 조회 실패 → 매 조회 시 실데이터 생성. "
                    "schema.sql 의 equity_snapshots 테이블을 만드세요: %s", exc,
                )
                _read_warned = True
    return {}


def get_cached(code: str, kind: str) -> dict | None:
    """kind: 'basics' | 'financials'. 오늘자 저장본이 있으면 반환, 없으면 None."""
    return _row(today_iso(), code).get(kind)


def save_cached(code: str, kind: str, payload: dict) -> None:
    date_iso = today_iso()
    k = _key(date_iso, code)
    row = dict(_mem.get(k) or {})
    row[kind] = payload
    _remember(date_iso, k, row)
    _upsert(date_iso, code, row)


# ── 종목코드 → corp_code 매핑도 같은 테이블에 하루치로 저장 (재다운로드·재파싱 방지) ──
_CORPMAP_CODE = "_corpmap"


def get_corpmap() -> dict[str, str] | None:
    return _row(today_iso(), _CORPMAP_CODE).get("map")


def save_corpmap(mapping: dict[str, str]) -> None:
    date_iso = today_iso()
    row = {"map": mapping}
    _remember(date_iso, _key(date_iso, _CORPMAP_CODE), row)
    _upsert(date_iso, _CORPMAP_CODE, row)


def _upsert(date_iso: str, code: str, row: dict) -> None:
    client = get_supabase_client()
    if client is None:
        return
    try:
        client.table(_TABLE).upsert(
            {"snapshot_date": date_iso, "code": code, "payload": row},
            on_conflict="snapshot_date,code",
        ).execute()
    except Exception as exc:  # noqa: BLE001
        global _warned
        if not _warned:
            logger.warning(
                "[equity] Supabase 저장 실패 → 메모리 캐시만 사용. "
                "schema.sql 의 equity_snapshots 테이블/RLS 를 확인하세요: %s", exc,
            )
            _warned = True
