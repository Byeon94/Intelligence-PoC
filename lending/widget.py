from flask import Blueprint, jsonify, render_template

from .news import get_lending_news
from .sample import BOND_LENDING, STOCK_LENDING

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
        lending_bp.logger.exception("증권대차 뉴스 조회 실패")
        news = {"stock": [], "bond": []}
    return jsonify({
        "stock": {**STOCK_LENDING, "news": news.get("stock", [])},
        "bond": {**BOND_LENDING, "news": news.get("bond", [])},
    })
