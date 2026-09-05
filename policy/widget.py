from flask import Blueprint, jsonify, render_template, request

from .briefing import get_policy_digest

policy_bp = Blueprint(
    "policy",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/policy",
)


@policy_bp.route("/policy")
def policy_tab():
    return render_template("policy.html")


@policy_bp.route("/api/policy/digest")
def digest():
    force = request.args.get("refresh") in ("1", "true", "yes")
    try:
        return jsonify(get_policy_digest(force_briefing=force))
    except Exception:  # noqa: BLE001
        policy_bp.logger.exception("정책 다이제스트 조회 실패")
        return jsonify({"error": "정책·규제 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."}), 502
