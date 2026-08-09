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
