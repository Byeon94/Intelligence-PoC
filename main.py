import argparse

from google.genai import Client

from config import get_settings
from naver_news import search_news
from summarizer import summarize_articles
from supabase_client import get_supabase_client, save_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="네이버 뉴스를 검색해 Gemini로 요약하고 Supabase에 저장합니다."
    )
    parser.add_argument("keywords", nargs="+", help="검색할 키워드 (여러 개 입력 가능)")
    parser.add_argument("--display", type=int, default=10, help="키워드당 조회할 뉴스 개수")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_settings()

    gemini_client = Client(api_key=settings.gemini_api_key)
    supabase_client = get_supabase_client(settings.supabase_url, settings.supabase_key)

    for keyword in args.keywords:
        articles = search_news(
            keyword,
            client_id=settings.naver_client_id,
            client_secret=settings.naver_client_secret,
            display=args.display,
        )

        summary = summarize_articles(gemini_client, keyword, articles)
        save_summary(supabase_client, keyword, summary, len(articles))

        print(f"\n=== '{keyword}' 뉴스 요약 ({len(articles)}건) ===")
        print(summary)


if __name__ == "__main__":
    main()
