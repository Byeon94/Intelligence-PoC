import time
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request

from main.config import get_settings
from main.supabase_client import get_supabase_client

from .calendar import fetch_month
from .feed import fetch_all_categories
from .stats import fetch_market_stats
from .store import (
    get_calendar_refresh_date,
    get_month,
    get_today_filings,
    mark_calendar_refreshed,
    save_filings,
    save_month,
)

_STATS_CACHE_TTL_SECONDS = 300
_stats_cache: dict[str, object] = {"data": None, "ts": 0.0}

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


@dart_bp.route("/api/widgets/dart/stats", methods=["GET"])
def stats():
    now = time.time()
    if _stats_cache["data"] is not None and now - _stats_cache["ts"] < _STATS_CACHE_TTL_SECONDS:
        return jsonify(_stats_cache["data"])

    try:
        data = fetch_market_stats(settings.dart_api_key)
    except Exception:
        return jsonify({"error": "공시 현황을 가져오는데 실패했습니다. 잠시 후 다시 시도해주세요."}), 502

    _stats_cache["data"] = data
    _stats_cache["ts"] = now
    return jsonify(data)


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
    today = datetime.now(KST).date().isoformat()
    current_month = datetime.now(KST).strftime("%Y-%m")
    year_month = request.args.get("month") or current_month

    try:
        refreshed_on = get_calendar_refresh_date(supabase_client, year_month)
    except Exception:
        refreshed_on = None

    # 지난달은 한 번 갱신해두면 다시 바뀔 일이 없고, 이번달은 하루 한 번만 새로 갱신한다.
    is_fresh = refreshed_on is not None and (year_month != current_month or refreshed_on == today)

    if is_fresh:
        try:
            cached = get_month(supabase_client, year_month)
        except Exception:
            cached = None
        if cached:
            return jsonify({"month": year_month, "items": cached, "cached": True})

    try:
        items = fetch_month(settings.dart_api_key, year_month)
    except Exception:
        try:
            cached = get_month(supabase_client, year_month)
        except Exception:
            cached = None
        if cached:
            return jsonify({"month": year_month, "items": cached, "cached": True, "stale": True})
        return jsonify({"error": "DART 공시 조회에 실패했습니다. 잠시 후 다시 시도해주세요."}), 502

    try:
        save_month(supabase_client, year_month, items)
        mark_calendar_refreshed(supabase_client, year_month, today)
    except Exception:
        pass

    return jsonify({"month": year_month, "items": items, "cached": False})
