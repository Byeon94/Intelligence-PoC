import threading

from flask import Blueprint, jsonify, request
from google.genai import Client

from config import get_settings
from naver_news import search_news
from summarizer import summarize_articles
from supabase_client import get_supabase_client, get_today_summary, save_summary

ARTICLE_DISPLAY_COUNT = 5

news_summary_bp = Blueprint("news_summary", __name__, url_prefix="/api/widgets/news-summary")

settings = get_settings()
gemini_client = Client(api_key=settings.gemini_api_key)
supabase_client = get_supabase_client(settings.supabase_url, settings.supabase_key)


@news_summary_bp.route("/articles", methods=["POST"])
def articles():
    keyword = (request.get_json(silent=True) or {}).get("keyword", "").strip()
    if not keyword:
        return jsonify({"error": "키워드를 입력해주세요."}), 400

    cached = get_today_summary(supabase_client, keyword)
    if cached:
        return jsonify(
            {
                "keyword": keyword,
                "summary": cached["summary"],
                "articles": cached["articles"],
                "cached": True,
            }
        )

    found_articles = search_news(
        keyword,
        client_id=settings.naver_client_id,
        client_secret=settings.naver_client_secret,
        display=ARTICLE_DISPLAY_COUNT,
    )
    return jsonify({"keyword": keyword, "articles": found_articles, "cached": False})


@news_summary_bp.route("/summary", methods=["POST"])
def summary():
    body = request.get_json(silent=True) or {}
    keyword = body.get("keyword", "").strip()
    articles_in = body.get("articles") or []
    if not keyword:
        return jsonify({"error": "키워드를 입력해주세요."}), 400

    summary_text = summarize_articles(gemini_client, keyword, articles_in)

    threading.Thread(
        target=save_summary,
        args=(supabase_client, keyword, summary_text, articles_in),
        daemon=True,
    ).start()

    return jsonify({"keyword": keyword, "summary": summary_text})
