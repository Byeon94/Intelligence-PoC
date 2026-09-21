from flask import Blueprint, jsonify

from .calendar import get_issuance_digest

issuance_bp = Blueprint(
    "issuance", __name__,
    static_folder="static", static_url_path="/static/issuance",
)


@issuance_bp.route("/api/issuance/digest")
def digest():
    # AI 브리핑은 /internal/warmup 배치에서만 생성한다 — 쿼리로 재생성을 트리거하지
    # 못하게 이 라우트는 항상 저장된 스냅샷만 반환한다(credit/leads.py 와 동일한 원칙).
    try:
        return jsonify(get_issuance_digest())
    except Exception:  # noqa: BLE001
        issuance_bp.logger.exception("발행시장 다이제스트 조회 실패")
        return jsonify({"error": "발행시장 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."}), 502
