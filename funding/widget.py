"""단기자금 탭 블루프린트 — 탭 템플릿(/funding)과 원화·외화 요약 JSON API(ECOS 실데이터)."""
import logging

from flask import Blueprint, jsonify, render_template

from .briefs import get_funding_briefs
from .money_market import get_fx_summary, get_won_summary
from .news import get_funding_news

logger = logging.getLogger(__name__)

funding_bp = Blueprint(
    "funding",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/funding",
)


def _safe(fn, label):
    try:
        return jsonify(fn())
    except Exception:  # noqa: BLE001 - 어떤 실패든 사용자에겐 502 메시지로
        logger.exception("%s 조회 실패", label)
        return jsonify({"error": f"{label} 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."}), 502


@funding_bp.route("/funding")
def funding_tab():
    """단기자금 탭 부분 템플릿 (index.html 에서 include)."""
    return render_template("funding.html")


@funding_bp.route("/api/funding/won")
def won_summary():
    return _safe(get_won_summary, "원화 단기자금")


@funding_bp.route("/api/funding/fx")
def fx_summary():
    return _safe(get_fx_summary, "외화 자금")


@funding_bp.route("/api/funding/briefs")
def briefs():
    """원화 탭 시황 브리프(KIDB·한국자금중개 PDF AI 요약). 새 자료가 있을 때만 AI 를 부른다."""
    return _safe(get_funding_briefs, "단기자금 시황 브리프")


@funding_bp.route("/api/funding/news")
def news():
    """원화·외화 관련 뉴스 추천(하루 1회 스냅샷)."""
    return _safe(get_funding_news, "단기자금 관련 뉴스")
