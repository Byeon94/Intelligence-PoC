"""전사 위젯 > IT·정보보호 뉴스 API(/api/it-news/digest).

it_news.curate 의 일일 스냅샷에서 위젯이 쓰는 필드만 내보낸다(후보 원본 제외).
"""
from flask import Blueprint, jsonify

from .curate import get_it_news_digest

it_news_bp = Blueprint(
    "it_news",
    __name__,
)

_PUBLIC = ("date", "credit", "generated_at", "briefing_at", "briefing", "briefing_note",
           "articles", "candidate_count", "cached", "stale")


@it_news_bp.route("/api/it-news/digest")
def digest():
    # 쿼리 파라미터는 받지 않는다(강제 재생성 없음). 오늘 스냅샷이 아직 없으면 이 요청이
    # 수집·AI 선별을 수행하고(보통은 /internal/warmup 이 먼저 만들어 둠), 있으면 저장본을 준다.
    try:
        data = get_it_news_digest()
        return jsonify({k: data.get(k) for k in _PUBLIC})  # 후보 원본(candidates)은 제외
    except Exception:  # noqa: BLE001
        it_news_bp.logger.exception("IT·정보보호 뉴스 조회 실패")
        return jsonify({"error": "IT·정보보호 뉴스를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."}), 502
