"""자본시장 > 발행시장 API 블루프린트(/api/issuance/digest) + issuance.js 정적 파일."""
from flask import Blueprint, jsonify

from .calendar import get_issuance_digest

issuance_bp = Blueprint(
    "issuance", __name__,
    static_folder="static", static_url_path="/static/issuance",
)


@issuance_bp.route("/api/issuance/digest")
def digest():
    # 쿼리로 재생성(force)을 트리거할 수는 없다 — 보통은 새벽 배치(/internal/warmup)가 만든
    # 스냅샷을 그대로 돌려준다. 배치 전에 온 첫 요청이면 여기서 수집·AI 브리핑을 할 수 있지만
    # table_lock 으로 동시 요청의 중복 호출이 막히고, 시도 횟수는 스냅샷당 상한을 따른다.
    try:
        return jsonify(get_issuance_digest())
    except Exception:  # noqa: BLE001
        issuance_bp.logger.exception("발행시장 다이제스트 조회 실패")
        return jsonify({"error": "발행시장 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."}), 502
