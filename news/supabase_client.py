from datetime import datetime
from zoneinfo import ZoneInfo

from supabase import Client

KST = ZoneInfo("Asia/Seoul")


def save_summary(client: Client, keyword: str, summary: str, articles: list[dict]) -> None:
    client.table("news_summaries").insert(
        {
            "keyword": keyword,
            "summary": summary,
            "article_count": len(articles),
            "articles": articles,
        }
    ).execute()


def get_today_summary(client: Client, keyword: str) -> dict | None:
    start_of_day = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)

    response = (
        client.table("news_summaries")
        .select("summary, articles, article_count, created_at")
        .eq("keyword", keyword)
        .gte("created_at", start_of_day.isoformat())
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else None
