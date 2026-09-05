from flask import Blueprint, jsonify, render_template

from .cma import get_cma_mix, get_cma_rates, get_cma_summary
from .liquidity import get_liquidity_summary, get_liquidity_trend
from .turnover import get_turnover_summary, get_turnover_trend

capital_bp = Blueprint(
    "capital",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/capital",
)


def _safe(fn, label):
    try:
        return jsonify(fn())
    except Exception:  # noqa: BLE001 - 어떤 실패든 사용자에겐 502 메시지로
        capital_bp.logger.exception("%s 조회 실패", label)
        return jsonify({"error": f"{label} 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."}), 502


@capital_bp.route("/capital")
def capital_tab():
    """자본시장 탭 부분 템플릿 (index.html 에서 include)."""
    return render_template("capital.html")


@capital_bp.route("/api/capital/liquidity/summary")
def liquidity_summary():
    return _safe(get_liquidity_summary, "증시자금 요약")


@capital_bp.route("/api/capital/liquidity/trend")
def liquidity_trend():
    return _safe(lambda: get_liquidity_trend(24), "증시자금 추이")


@capital_bp.route("/api/capital/turnover/summary")
def turnover_summary():
    return _safe(get_turnover_summary, "거래대금 요약")


@capital_bp.route("/api/capital/turnover/trend")
def turnover_trend():
    return _safe(lambda: get_turnover_trend(24), "거래대금 추이")


@capital_bp.route("/api/capital/cma/summary")
def cma_summary():
    return _safe(get_cma_summary, "CMA 요약")


@capital_bp.route("/api/capital/cma/mix")
def cma_mix():
    return _safe(get_cma_mix, "CMA 유형별 점유율")


@capital_bp.route("/api/capital/cma/rates")
def cma_rates():
    return _safe(get_cma_rates, "증권사별 CMA 금리")
