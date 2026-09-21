from flask import Blueprint, jsonify, render_template, request

from .equity import get_stock_basics, search_stocks
from .esop_news import get_esop_news
from .filings import get_filings
from .financials import get_financials
from .inherit_news import get_inherit_news
from .lead_briefing import get_lead_briefings
from .leads import get_leads
from .reports import get_market_report_digest, get_reports
from .today_summary import get_today_leads_summary

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


@credit_bp.route("/api/credit/equity/filings")
def equity_filings():
    code = _code_arg()
    if not code:
        return jsonify({"error": "종목코드 6자리를 입력하세요."}), 400
    return _safe(lambda: get_filings(code), "공시")


@credit_bp.route("/api/credit/equity/reports")
def equity_reports():
    code = _code_arg()
    if not code:
        return jsonify({"error": "종목코드 6자리를 입력하세요."}), 400
    return _safe(lambda: get_reports(code), "리포트")


@credit_bp.route("/api/credit/market-reports")
def market_reports():
    """전사 위젯: 특정 종목이 아닌 시장 전체 증권사 리포트 동향(건수 + AI 브리핑).

    AI 브리핑은 /internal/warmup 배치에서만 생성한다 — 쿼리로 재생성을 트리거하지
    못하게 이 라우트는 항상 저장된 스냅샷만 반환한다."""
    return _safe(lambda: get_market_report_digest(), "시장 리포트 동향")


@credit_bp.route("/api/credit/leads")
def leads():
    """여신·심사 메인 화면: 코스피·코스닥 전 종목 증권담보대출·우리사주 금융 수요 리드(DART 실데이터).

    수집 자체는 코스피·코스닥 전 종목을 훑어 수 분이 걸리고 DART 호출량도 많아,
    /internal/warmup 배치에서만 force=True 로 수행한다. 이 라우트는 절대 force 를
    받지 않고(쿼리로도 재수집을 못 트리거하게) 저장된 스냅샷만 읽는다.
    """
    return _safe(lambda: get_leads(), "증권담보대출·우리사주 리드")


@credit_bp.route("/api/credit/today-summary")
def today_summary():
    """여신·심사 전체 탭의 "오늘 신규 리드" — 홈 대시보드 알림과 반드시 같은
    계산(credit.today_summary.get_today_leads_summary)을 써서 화면마다 건수가
    어긋나지 않게 한다."""
    return _safe(lambda: get_today_leads_summary(), "오늘 신규 리드")


@credit_bp.route("/api/credit/inherit-news")
def inherit_news():
    """여신·심사 메인 화면: 상속·증여 관련 뉴스 동향(참고용, AI 관련도 판단).

    AI 판단은 /internal/warmup 배치에서만 수행한다 — 쿼리로 재생성을 트리거하지
    못하게 이 라우트는 항상 저장된 스냅샷만 반환한다."""
    return _safe(lambda: get_inherit_news(), "상속·증여 뉴스 동향")


@credit_bp.route("/api/credit/esop-news")
def esop_news():
    """여신·심사 메인 화면: 우리사주(유상증자·IPO) 관련 뉴스 동향(참고용, AI 관련도 판단).

    AI 판단은 /internal/warmup 배치에서만 수행한다 — 쿼리로 재생성을 트리거하지
    못하게 이 라우트는 항상 저장된 스냅샷만 반환한다."""
    return _safe(lambda: get_esop_news(), "우리사주 뉴스 동향")


@credit_bp.route("/api/credit/lead-briefings")
def lead_briefings():
    """여신·심사 메인 화면(전체 탭): 증권담보대출·우리사주 리드에 대한 AI 브리핑.

    AI 브리핑은 /internal/warmup 배치에서만 생성한다 — 쿼리로 재생성을 트리거하지
    못하게 이 라우트는 항상 저장된 스냅샷만 반환한다."""
    return _safe(lambda: get_lead_briefings(), "리드 AI 브리핑")
