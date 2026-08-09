from flask import Blueprint, jsonify

from .fund_flow import get_fund_flow_indicators
from .market_data import get_market_indices

market_summary_bp = Blueprint(
    "market_summary",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/capital",
)


@market_summary_bp.route("/api/widgets/market-summary/indices", methods=["GET"])
def indices():
    try:
        data = get_market_indices()
    except Exception:
        return jsonify({"error": "지수 데이터를 가져오는데 실패했습니다. 잠시 후 다시 시도해주세요."}), 502

    return jsonify({"indices": data})


@market_summary_bp.route("/api/widgets/market-summary/fund-flow", methods=["GET"])
def fund_flow():
    try:
        data = get_fund_flow_indicators()
    except Exception:
        return jsonify({"error": "자금동향 데이터를 가져오는데 실패했습니다. 잠시 후 다시 시도해주세요."}), 502

    return jsonify({"fund_flow": data})
