"""여러 패키지가 같이 쓰는 작은 헬퍼 — 날짜(KST) 등.

Render 서버 시계는 UTC라 `date.today()`를 쓰면 00:00~09:00 KST 동안 날짜가 하루 어긋난다.
"오늘"이 필요한 곳은 모두 여기 today_kst()/now_kst()를 쓴다.
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now_kst() -> datetime:
    return datetime.now(KST)


def today_kst() -> date:
    return now_kst().date()


def today_iso() -> str:
    """오늘(KST) 날짜 'YYYY-MM-DD' — 일일 스냅샷 키로 쓴다."""
    return today_kst().isoformat()


def stamp() -> str:
    """'YYYY-MM-DD HH:MM'(KST) — generated_at·briefing_at 표시용."""
    return now_kst().strftime("%Y-%m-%d %H:%M")


def ymd_to_iso(s: str | None) -> str:
    """'20260922' → '2026-09-22'. 형식이 다르면 그대로 돌려준다."""
    s = str(s or "")
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 and s.isdigit() else s
