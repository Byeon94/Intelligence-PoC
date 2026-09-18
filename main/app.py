import logging
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, jsonify, render_template, request

from capital.cma import get_cma_rates
from capital.issuance.calendar import get_issuance_digest
from capital.issuance.widget import issuance_bp
from capital.widget import capital_bp
from credit.reports import get_market_report_digest
from credit.widget import credit_bp
from it_news.curate import get_it_news_digest
from it_news.widget import it_news_bp
from main.config import get_settings
from main.home import get_home_summary
from policy.briefing import get_policy_digest
from policy.widget import policy_bp
from research.curate import get_research_digest
from research.widget import research_bp

logger = logging.getLogger(__name__)

app = Flask(__name__)
# PoC: 정적 파일(css/js)도 캐시하지 않아 기기 간 최신본이 바로 반영되게 한다.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.register_blueprint(capital_bp)
app.register_blueprint(policy_bp)
app.register_blueprint(research_bp)
app.register_blueprint(issuance_bp)
app.register_blueprint(credit_bp)
app.register_blueprint(it_news_bp)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/home/summary")
def home_summary():
    try:
        return jsonify(get_home_summary())
    except Exception:  # noqa: BLE001
        logger.exception("홈 요약 조회 실패")
        return jsonify({"error": "홈 요약을 불러오지 못했습니다."}), 502


_warmup_lock = threading.Lock()


def _run_warmup() -> None:
    if not _warmup_lock.acquire(blocking=False):
        return
    try:
        try:
            get_policy_digest()
        except Exception:  # noqa: BLE001
            logger.exception("정책·규제 워밍업 실패")
        try:
            get_research_digest()
        except Exception:  # noqa: BLE001
            logger.exception("리서치·뉴스 워밍업 실패")
        try:
            get_issuance_digest()
        except Exception:  # noqa: BLE001
            logger.exception("발행시장 워밍업 실패")
        try:
            get_cma_rates()
        except Exception:  # noqa: BLE001
            logger.exception("CMA 금리 워밍업 실패")
        try:
            get_market_report_digest()
        except Exception:  # noqa: BLE001
            logger.exception("시장 리포트 동향 워밍업 실패")
        try:
            get_it_news_digest()
        except Exception:  # noqa: BLE001
            logger.exception("IT·정보보호 뉴스 워밍업 실패")
    finally:
        _warmup_lock.release()


@app.route("/internal/warmup")
def warmup():
    """매일 아침 외부 스케줄러가 호출 → 정책·규제/리서치·뉴스/발행시장/CMA금리/시장 리포트
    동향/IT·정보보호 뉴스 스냅샷을 미리 생성.

    스크랩+AI 요약이 gunicorn 응답 타임아웃(120초)을 넘을 수 있어 즉시 202를
    응답하고, 실제 작업은 백그라운드 스레드에서 이어간다.
    """
    key = get_settings().warmup_key
    if not key or request.args.get("key") != key:
        return jsonify({"error": "unauthorized"}), 403
    if _warmup_lock.locked():
        return jsonify({"status": "already_running"}), 202
    threading.Thread(target=_run_warmup, daemon=True).start()
    return jsonify({"status": "started"}), 202


@app.after_request
def _no_store(resp):
    # HTML·CSS·JS 모두 캐시하지 않아 기기 간(특히 모바일) 최신본이 바로 반영되게 한다.
    if resp.mimetype in ("text/html", "text/css", "application/javascript", "text/javascript"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


if __name__ == "__main__":
    # threaded=True: 개발 서버도 탭이 동시에 던지는 여러 API 호출을 병렬 처리
    # (프로덕션은 gunicorn --workers 2). 미설정 시 요청이 직렬화돼 느린 1건이
    # 형제 요청의 'Failed to fetch' 를 유발할 수 있다.
    app.run(debug=True, port=5000, threaded=True)
