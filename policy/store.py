from datetime import datetime
from zoneinfo import ZoneInfo

from supabase import Client

KST = ZoneInfo("Asia/Seoul")


def get_today_updates(client: Client) -> list[dict]:
    today = datetime.now(KST).date().isoformat()

    response = (
        client.table("policy_updates")
        .select(
            "category, org_code, org_name, title, summary, tags, "
            "source_label, source_url, published_label, fetched_date"
        )
        .eq("fetched_date", today)
        .execute()
    )
    return response.data or []


def get_latest_updates(client: Client) -> list[dict]:
    response = (
        client.table("policy_updates")
        .select(
            "category, org_code, org_name, title, summary, tags, "
            "source_label, source_url, published_label, fetched_date"
        )
        .order("fetched_date", desc=True)
        .execute()
    )
    rows = response.data or []
    if not rows:
        return []
    latest_date = rows[0]["fetched_date"]
    return [r for r in rows if r["fetched_date"] == latest_date]


def save_updates(client: Client, updates: list[dict]) -> None:
    if not updates:
        return
    client.table("policy_updates").upsert(updates, on_conflict="org_code,fetched_date").execute()
