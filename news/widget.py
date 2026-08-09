from flask import Blueprint, jsonify
from google.genai import Client

from main.config import get_settings
from main.supabase_client import get_supabase_client

from .feed import fetch_all_categories
from .store import get_today_feed, save_feed
from .summarizer import summarize_daily_briefing_with_fallback

news_summary_bp = Blueprint(
    "news_summary",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/news",
)

settings = get_settings()
gemini_clients = [Client(api_key=settings.gemini_api_key)]
if settings.gemini_api_key_2:
    gemini_clients.append(Client(api_key=settings.gemini_api_key_2))
supabase_client = get_supabase_client(settings.supabase_url, settings.supabase_key)


@news_summary_bp.route("/api/widgets/news-feed/today", methods=["GET"])
def today_feed():
    try:
        cached = get_today_feed(supabase_client)
    except Exception:
        return jsonify({"error": "뉴스 피드를 불러오는데 실패했습니다. DB 설정을 확인해주세요."}), 502

    if cached:
        return jsonify({"items": cached["items"], "summary": cached["summary"], "cached": True})

    try:
        items = fetch_all_categories(settings.naver_client_id, settings.naver_client_secret)
    except Exception:
        return jsonify({"error": "뉴스 검색에 실패했습니다. 잠시 후 다시 시도해주세요."}), 502

    try:
        summary = summarize_daily_briefing_with_fallback(gemini_clients, items)
    except Exception:
        summary = ""

    try:
        save_feed(supabase_client, items, summary)
    except Exception:
        pass

    return jsonify({"items": items, "summary": summary, "cached": False})
