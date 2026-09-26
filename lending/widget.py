"""증권대차 탭 라우트 — 탭 부분 템플릿과 관련 뉴스 API(/api/lending/data)."""
import logging

from flask import Blueprint, jsonify, render_template

from .news import get_lending_news

logger = logging.getLogger(__name__)

lending_bp = Blueprint(
    "lending",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/lending",
)


@lending_bp.route("/lending")
def lending_tab():
    return render_template("lending.html")


@lending_bp.route("/api/lending/data")
def data():
    try:
        news = get_lending_news()
    except Exception:  # noqa: BLE001
        logger.exception("증권대차 뉴스 조회 실패")
        news = {"stock": [], "bond": []}
    return jsonify({
        "stock": {"news": news.get("stock", [])},
        "bond": {"news": news.get("bond", [])},
    })
