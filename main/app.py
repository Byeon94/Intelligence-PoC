"""Flask 진입점 — 블루프린트 등록, 메인 화면(/), 홈 요약 API, 새벽 워밍업(/internal/warmup).

프로덕션: gunicorn 워커 1 + gthread 스레드 4(Procfile/render.yaml). 워커가 1개라 인프로세스
캐시(ttl_cache·스냅샷 메모리 폴백)와 락을 모든 요청이 공유한다.
"""
import logging
import sys
import threading
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, jsonify, render_template, request

from capital.briefing import get_market_briefing
from capital.cma import get_cma_rates
from capital.issuance.calendar import get_issuance_digest
from capital.issuance.widget import issuance_bp
from capital.widget import capital_bp
from credit.esop_news import get_esop_news
from credit.inherit_news import get_inherit_news
from credit.lead_briefing import get_lead_briefings
from credit.leads import get_leads
from credit.reports import get_market_report_digest
from credit.widget import credit_bp
from it_news.curate import get_it_news_digest
from it_news.widget import it_news_bp
from lending.news import get_lending_news
from lending.widget import lending_bp
from main.config import get_settings
from main.home import get_home_summary
from policy.briefing import get_policy_digest
from policy.widget import policy_bp
from research.curate import get_research_digest
from research.widget import research_bp
from sector.widget import sector_bp

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
app.register_blueprint(lending_bp)
app.register_blueprint(sector_bp)


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

# 매일 00:01 KST 워밍업 작업 — (로그 라벨, 함수). 순서가 의미 있다: 여신 리드 AI 브리핑은
# 앞의 리드·상속증여·우리사주 스냅샷을 방금 새로 만든 뒤에 갱신해야 한다.
# 업종별 시가총액 맵의 전종목 재분류(sector.classify.refresh_sector_classification)는
# 일부러 넣지 않는다 — API 사용량을 최소화하기 위해 필요할 때만 수동으로 돌린다. 화면은
# 항상 sector.classify.get_cached_classification() 으로 저장된 분류만 읽으므로 이 배치가
# 없어도 정상 동작한다.
_WARMUP_JOBS: list[tuple[str, Callable[[], object]]] = [
    ("정책·규제", get_policy_digest),
    ("뉴스", get_research_digest),
    ("발행시장", get_issuance_digest),
    ("CMA 금리", get_cma_rates),
    ("오늘의 시장 브리핑", get_market_briefing),   # 전영업일 마감 수치 기준(AI)
    ("시장 리포트 동향", get_market_report_digest),
    ("IT·정보보호 뉴스", get_it_news_digest),
    ("증권대차 뉴스", get_lending_news),
    # 이미 백그라운드 스레드 안이라 동기 실행(force=True)해도 안전
    ("여신 리드(증권담보대출·우리사주)", lambda: get_leads(force=True)),
    ("상속·증여 뉴스 동향", get_inherit_news),
    ("우리사주 뉴스 동향", get_esop_news),
    # 위 스냅샷들을 방금 새로 만들었으니 브리핑도 같이 갱신
    ("여신 리드 AI 브리핑", lambda: get_lead_briefings(force=True)),
]

# 매일 07:00 KST 아침 재생성(mode=morning) — 00:01 시점엔 미국 장이 아직 열려 있어 시장
# 브리핑의 '장전' 수치가 마감값이 아니고, 뉴스류는 당일 기사가 거의 없다. 그래서 이 작업들만
# 다시 만든다. 각 함수는 재생성이 실패하면 새벽 스냅샷을 그대로 유지한다.
_MORNING_JOBS: list[tuple[str, Callable[[], object]]] = [
    ("오늘의 시장 브리핑", lambda: get_market_briefing(force=True)),
    ("뉴스", lambda: get_research_digest(rebuild=True)),
    ("IT·정보보호 뉴스", lambda: get_it_news_digest(rebuild=True)),
    ("증권대차 뉴스", lambda: get_lending_news(rebuild=True)),
    ("상속·증여 뉴스 동향", lambda: get_inherit_news(rebuild=True)),
    ("우리사주 뉴스 동향", lambda: get_esop_news(rebuild=True)),
    ("여신 리드 AI 브리핑", lambda: get_lead_briefings(force=True)),   # 새 뉴스 반영
]


def _run_warmup(jobs: list[tuple[str, Callable[[], object]]]) -> None:
    if not _warmup_lock.acquire(blocking=False):
        return
    try:
        for label, job in jobs:
            try:
                job()
            except Exception:  # noqa: BLE001
                logger.exception("%s 워밍업 실패", label)
    finally:
        _warmup_lock.release()


@app.route("/internal/warmup")
def warmup():
    """GitHub Actions(.github/workflows/warmup.yml)가 하루 두 번 호출한다.

    - 00:01 KST: `?key=...` → _WARMUP_JOBS 로 그날 스냅샷을 미리 생성
    - 07:00 KST: `?key=...&mode=morning` → _MORNING_JOBS(시장 브리핑·뉴스류)만 다시 생성

    전체 스크랩+AI 요약은 수 분이 걸려 호출 측 curl --max-time(60초)이나 Render 프록시
    타임아웃을 넘기므로, 즉시 202를 응답하고 실제 작업은 백그라운드 스레드에서 이어간다.
    """
    key = get_settings().warmup_key
    if not key or request.args.get("key") != key:
        return jsonify({"error": "unauthorized"}), 403
    if _warmup_lock.locked():
        return jsonify({"status": "already_running"}), 202
    morning = request.args.get("mode") == "morning"
    jobs = _MORNING_JOBS if morning else _WARMUP_JOBS
    threading.Thread(target=_run_warmup, args=(jobs,), daemon=True).start()
    return jsonify({"status": "started", "mode": "morning" if morning else "daily"}), 202


@app.after_request
def _no_store(resp):
    # HTML·CSS·JS 모두 캐시하지 않아 기기 간(특히 모바일) 최신본이 바로 반영되게 한다.
    if resp.mimetype in ("text/html", "text/css", "application/javascript", "text/javascript"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


if __name__ == "__main__":
    # threaded=True: 개발 서버도 탭이 동시에 던지는 여러 API 호출을 병렬 처리
    # (프로덕션은 gunicorn 워커 1 + gthread 스레드 4, Procfile 참고). 미설정 시 요청이
    # 직렬화돼 느린 1건이 형제 요청의 'Failed to fetch' 를 유발할 수 있다.
    app.run(debug=True, port=5000, threaded=True)
