from datetime import datetime
from zoneinfo import ZoneInfo

from supabase import Client

KST = ZoneInfo("Asia/Seoul")


def get_today_feed(client: Client) -> dict | None:
    today = datetime.now(KST).date().isoformat()

    items_response = (
        client.table("news_feed_items")
        .select("category, keyword, title, description, link, published_label")
        .eq("fetched_date", today)
        .execute()
    )
    items = items_response.data or []
    if not items:
        return None

    briefing_response = (
        client.table("news_briefing")
        .select("summary")
        .eq("fetched_date", today)
        .limit(1)
        .execute()
    )
    briefing_rows = briefing_response.data or []
    summary = briefing_rows[0]["summary"] if briefing_rows else ""

    return {"items": items, "summary": summary}


def save_feed(client: Client, items: list[dict], summary: str) -> None:
    today = datetime.now(KST).date().isoformat()

    if items:
        client.table("news_feed_items").upsert(
            [{**item, "fetched_date": today} for item in items],
            on_conflict="link,fetched_date",
        ).execute()

    client.table("news_briefing").upsert(
        {"fetched_date": today, "summary": summary},
        on_conflict="fetched_date",
    ).execute()
