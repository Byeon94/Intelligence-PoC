from flask import Blueprint, jsonify, request

from .calendar import get_issuance_digest

issuance_bp = Blueprint(
    "issuance", __name__,
    static_folder="static", static_url_path="/static/issuance",
)


@issuance_bp.route("/api/issuance/digest")
def digest():
    force = request.args.get("refresh") in ("1", "true", "yes")
    try:
        return jsonify(get_issuance_digest(force=force))
    except Exception:  # noqa: BLE001
        issuance_bp.logger.exception("발행시장 다이제스트 조회 실패")
        return jsonify({"error": "발행시장 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."}), 502
