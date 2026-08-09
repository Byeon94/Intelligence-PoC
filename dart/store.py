from datetime import datetime
from zoneinfo import ZoneInfo

from supabase import Client

KST = ZoneInfo("Asia/Seoul")


def get_today_filings(client: Client) -> list[dict] | None:
    today = datetime.now(KST).date().isoformat()

    response = (
        client.table("dart_filings")
        .select("category, corp_name, stock_code, report_nm, flr_nm, rcept_no, rcept_dt, source_url")
        .eq("fetched_date", today)
        .order("rcept_dt", desc=True)
        .execute()
    )
    rows = response.data or []
    return rows or None


def save_filings(client: Client, filings: list[dict]) -> None:
    if not filings:
        return
    today = datetime.now(KST).date().isoformat()
    client.table("dart_filings").upsert(
        [{**f, "fetched_date": today} for f in filings],
        on_conflict="rcept_no,fetched_date",
    ).execute()


def get_month(client: Client, year_month: str) -> list[dict] | None:
    response = (
        client.table("dart_calendar_items")
        .select("category, corp_name, report_nm, rcept_no, rcept_dt, source_url, right_type, right_label")
        .eq("year_month", year_month)
        .order("rcept_dt")
        .execute()
    )
    rows = response.data or []
    return rows or None


def save_month(client: Client, year_month: str, items: list[dict]) -> None:
    if not items:
        return
    client.table("dart_calendar_items").upsert(
        [{**item, "year_month": year_month} for item in items],
        on_conflict="rcept_no",
    ).execute()
