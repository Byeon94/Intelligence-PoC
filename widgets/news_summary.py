import threading

from flask import Blueprint, jsonify, request
from google.genai import Client

from config import get_settings
from naver_news import search_news
from summarizer import summarize_articles
from supabase_client import get_supabase_client, save_summary

news_summary_bp = Blueprint("news_summary", __name__, url_prefix="/api/widgets/news-summary")

settings = get_settings()
gemini_client = Client(api_key=settings.gemini_api_key)
supabase_client = get_supabase_client(settings.supabase_url, settings.supabase_key)


@news_summary_bp.route("", methods=["POST"])
def summarize():
    keyword = (request.get_json(silent=True) or {}).get("keyword", "").strip()
    if not keyword:
        return jsonify({"error": "키워드를 입력해주세요."}), 400

    articles = search_news(
        keyword,
        client_id=settings.naver_client_id,
        client_secret=settings.naver_client_secret,
    )
    summary = summarize_articles(gemini_client, keyword, articles)

    threading.Thread(
        target=save_summary,
        args=(supabase_client, keyword, summary, len(articles)),
        daemon=True,
    ).start()

    return jsonify({"keyword": keyword, "summary": summary, "articles": articles})
