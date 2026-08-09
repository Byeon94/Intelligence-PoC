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


def save_updates(client: Client, updates: list[dict]) -> None:
    if not updates:
        return
    client.table("policy_updates").upsert(updates, on_conflict="org_code,fetched_date").execute()
