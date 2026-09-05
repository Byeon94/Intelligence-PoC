from flask import Blueprint, jsonify, render_template, request

from .curate import get_research_digest

research_bp = Blueprint(
    "research",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/research",
)

_PUBLIC = ("date", "generated_at", "briefing_at", "briefing", "briefing_note",
           "articles", "candidate_count", "gemini_attempts", "cached", "stale")


@research_bp.route("/research")
def research_tab():
    return render_template("research.html")


@research_bp.route("/api/research/digest")
def digest():
    force = request.args.get("refresh") in ("1", "true", "yes")
    try:
        data = get_research_digest(force=force)
        return jsonify({k: data.get(k) for k in _PUBLIC})  # 후보 원본(candidates)은 제외
    except Exception:  # noqa: BLE001
        research_bp.logger.exception("리서치 다이제스트 조회 실패")
        return jsonify({"error": "리서치·뉴스 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."}), 502
