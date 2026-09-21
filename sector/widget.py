from flask import Blueprint, jsonify, render_template

from .market_map import get_sector_map
from .value_chain import get_value_chain

sector_bp = Blueprint(
    "sector",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/sector",
)


def _safe(fn, label):
    try:
        return jsonify(fn())
    except Exception:  # noqa: BLE001 - 어떤 실패든 사용자에겐 502 메시지로
        sector_bp.logger.exception("%s 조회 실패", label)
        return jsonify({"error": f"{label} 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."}), 502


@sector_bp.route("/sector")
def sector_page():
    """전사 위젯 전용 독립 페이지(SPA 밖) — 투자금융부 이OO 과장 제작."""
    return render_template("sector_page.html")


@sector_bp.route("/api/sector/map")
def sector_map():
    return _safe(get_sector_map, "업종별 시가총액 맵")


@sector_bp.route("/api/sector/value-chain")
def sector_value_chain():
    return _safe(get_value_chain, "업종별 밸류체인")
