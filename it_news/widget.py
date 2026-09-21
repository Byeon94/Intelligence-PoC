from flask import Blueprint, jsonify

from .curate import get_it_news_digest

it_news_bp = Blueprint(
    "it_news",
    __name__,
)

_PUBLIC = ("date", "credit", "generated_at", "briefing_at", "briefing", "briefing_note",
           "articles", "candidate_count", "gemini_attempts", "cached", "stale")


@it_news_bp.route("/api/it-news/digest")
def digest():
    # AI 선별은 /internal/warmup 배치에서만 생성한다 — 쿼리로 재생성을 트리거하지
    # 못하게 이 라우트는 항상 저장된 스냅샷만 반환한다.
    try:
        data = get_it_news_digest()
        return jsonify({k: data.get(k) for k in _PUBLIC})  # 후보 원본(candidates)은 제외
    except Exception:  # noqa: BLE001
        it_news_bp.logger.exception("IT·정보보호 뉴스 조회 실패")
        return jsonify({"error": "IT·정보보호 뉴스를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."}), 502
