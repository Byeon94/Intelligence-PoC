from flask import Blueprint, jsonify
from google.genai import Client

from main.config import get_settings
from main.supabase_client import get_supabase_client

from .policy_data import fetch_policy_updates
from .store import get_latest_updates, get_today_updates, save_updates

policy_bp = Blueprint(
    "policy",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/policy",
)

settings = get_settings()
gemini_clients = [Client(api_key=settings.gemini_api_key)]
if settings.gemini_api_key_2:
    gemini_clients.append(Client(api_key=settings.gemini_api_key_2))
supabase_client = get_supabase_client(settings.supabase_url, settings.supabase_key)


@policy_bp.route("/api/widgets/policy/updates", methods=["GET"])
def updates():
    try:
        cached = get_today_updates(supabase_client)
    except Exception:
        return jsonify({"error": "정책 동향 데이터를 불러오는데 실패했습니다. DB 설정을 확인해주세요."}), 502

    if cached:
        return jsonify({"updates": cached, "cached": True})

    try:
        fresh = fetch_policy_updates(gemini_clients)
    except Exception:
        try:
            stale = get_latest_updates(supabase_client)
        except Exception:
            stale = []
        if stale:
            return jsonify({"updates": stale, "cached": True, "stale": True})
        return jsonify({"error": "정책 동향 데이터를 가져오는데 실패했습니다. 잠시 후 다시 시도해주세요."}), 502

    try:
        save_updates(supabase_client, fresh)
    except Exception:
        pass

    return jsonify({"updates": fresh, "cached": False})
