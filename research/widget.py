"""뉴스 탭 라우트 — 화면(/research)과 다이제스트 API(/api/research/digest).

API 는 research.curate 의 일일 스냅샷에서 화면이 쓰는 필드만 내보낸다(후보 원본 제외).
"""
from flask import Blueprint, jsonify, render_template

from .curate import get_research_digest

research_bp = Blueprint(
    "research",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/research",
)

_PUBLIC = ("date", "generated_at", "briefing_at", "briefing", "briefing_note",
           "articles", "candidate_count", "cached", "stale")


@research_bp.route("/research")
def research_tab():
    return render_template("research.html")


@research_bp.route("/api/research/digest")
def digest():
    # 쿼리 파라미터는 받지 않는다(강제 재생성 없음). 오늘 스냅샷이 아직 없으면 이 요청이
    # 수집·AI 선별을 수행하고(보통은 /internal/warmup 이 먼저 만들어 둠), 있으면 저장본을 준다.
    try:
        data = get_research_digest()
        return jsonify({k: data.get(k) for k in _PUBLIC})  # 후보 원본(candidates)은 제외
    except Exception:  # noqa: BLE001
        research_bp.logger.exception("뉴스 다이제스트 조회 실패")
        return jsonify({"error": "뉴스 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."}), 502
