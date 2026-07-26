from supabase import Client, create_client


def get_supabase_client(url: str, key: str) -> Client:
    return create_client(url, key)


def save_summary(client: Client, keyword: str, summary: str, article_count: int) -> None:
    client.table("news_summaries").insert(
        {
            "keyword": keyword,
            "summary": summary,
            "article_count": article_count,
        }
    ).execute()
