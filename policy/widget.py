from flask import Blueprint, jsonify, render_template

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
    # AI 브리핑은 /internal/warmup 배치에서만 생성한다 — 쿼리로 재생성을 트리거하지
    # 못하게 이 라우트는 항상 저장된 스냅샷만 반환한다.
    try:
        return jsonify(get_policy_digest())
    except Exception:  # noqa: BLE001
        policy_bp.logger.exception("정책 다이제스트 조회 실패")
        return jsonify({"error": "정책·규제 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."}), 502
