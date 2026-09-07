from flask import Blueprint, jsonify, render_template, request

from .equity import get_stock_basics, search_stocks
from .financials import get_financials

credit_bp = Blueprint(
    "credit",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/credit",
)


def _safe(fn, label):
    try:
        return jsonify(fn())
    except Exception:  # noqa: BLE001 - 어떤 실패든 사용자에겐 502 메시지로
        credit_bp.logger.exception("%s 조회 실패", label)
        return jsonify({"error": f"{label} 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."}), 502


def _code_arg() -> str | None:
    code = (request.args.get("code") or "").strip()
    return code if code.isdigit() and len(code) == 6 else None


@credit_bp.route("/credit")
def credit_tab():
    """여신·심사 탭 부분 템플릿 (index.html 에서 include)."""
    return render_template("credit.html")


@credit_bp.route("/api/credit/equity/search")
def equity_search():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"items": []})
    return _safe(lambda: {"items": search_stocks(q)}, "종목 검색")


@credit_bp.route("/api/credit/equity/basics")
def equity_basics():
    code = _code_arg()
    if not code:
        return jsonify({"error": "종목코드 6자리를 입력하세요."}), 400
    return _safe(lambda: get_stock_basics(code), "기초정보")


@credit_bp.route("/api/credit/equity/financials")
def equity_financials():
    code = _code_arg()
    if not code:
        return jsonify({"error": "종목코드 6자리를 입력하세요."}), 400
    return _safe(lambda: get_financials(code), "재무정보")
