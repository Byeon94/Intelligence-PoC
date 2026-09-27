"""심사·리스크 탭 블루프린트 — 탭 템플릿(/risk)과 리스크 시그널·워치·섹터·뉴스 JSON API."""
import logging

from flask import Blueprint, jsonify, render_template

from .news import get_risk_news
from .signals import get_signals
from .watch import get_watch_sector

logger = logging.getLogger(__name__)

risk_bp = Blueprint(
    "risk",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/risk",
)


def _safe(fn, label):
    try:
        return jsonify(fn())
    except Exception:  # noqa: BLE001 - 어떤 실패든 사용자에겐 502 메시지로
        logger.exception("%s 조회 실패", label)
        return jsonify({"error": f"{label} 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."}), 502


@risk_bp.route("/risk")
def risk_tab():
    """심사·리스크 탭 부분 템플릿 (index.html 에서 include)."""
    return render_template("risk.html")


@risk_bp.route("/api/risk/signals")
def signals():
    """DART 거래소공시 리스크 시그널(스냅샷, 1시간마다 갱신) + 급락 종목."""
    return _safe(get_signals, "리스크 시그널")


@risk_bp.route("/api/risk/watch")
def watch():
    """워치 유니버스(시총 상위 30) · 섹터 리스크 히트."""
    return _safe(get_watch_sector, "워치·섹터")


@risk_bp.route("/api/risk/news")
def news():
    """부정 키워드 기사 AI 선별(하루 1회 스냅샷)."""
    return _safe(get_risk_news, "리스크 관련 뉴스")
