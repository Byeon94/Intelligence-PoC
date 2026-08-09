from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request

from main.config import get_settings
from main.supabase_client import get_supabase_client

from .calendar import fetch_month
from .feed import fetch_all_categories
from .store import get_month, get_today_filings, save_filings, save_month

KST = ZoneInfo("Asia/Seoul")

dart_bp = Blueprint(
    "dart",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/dart",
)

settings = get_settings()
supabase_client = get_supabase_client(settings.supabase_url, settings.supabase_key)


@dart_bp.route("/api/widgets/dart/filings", methods=["GET"])
def filings():
    try:
        cached = get_today_filings(supabase_client)
    except Exception:
        return jsonify({"error": "DART 공시를 불러오는데 실패했습니다. DB 설정을 확인해주세요."}), 502

    if cached:
        return jsonify({"filings": cached, "cached": True})

    try:
        fresh = fetch_all_categories(settings.dart_api_key)
    except Exception:
        return jsonify({"error": "DART 공시 조회에 실패했습니다. 잠시 후 다시 시도해주세요."}), 502

    try:
        save_filings(supabase_client, fresh)
    except Exception:
        pass

    return jsonify({"filings": fresh, "cached": False})


@dart_bp.route("/api/widgets/dart/calendar", methods=["GET"])
def calendar_view():
    current_month = datetime.now(KST).strftime("%Y-%m")
    year_month = request.args.get("month") or current_month

    if year_month != current_month:
        try:
            cached = get_month(supabase_client, year_month)
        except Exception:
            return jsonify({"error": "캘린더를 불러오는데 실패했습니다. DB 설정을 확인해주세요."}), 502
        if cached:
            return jsonify({"month": year_month, "items": cached, "cached": True})

    try:
        items = fetch_month(settings.dart_api_key, year_month)
    except Exception:
        return jsonify({"error": "DART 공시 조회에 실패했습니다. 잠시 후 다시 시도해주세요."}), 502

    try:
        save_month(supabase_client, year_month, items)
    except Exception:
        pass

    return jsonify({"month": year_month, "items": items, "cached": False})
