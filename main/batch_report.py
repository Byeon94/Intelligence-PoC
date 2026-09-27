"""배치(/internal/warmup) 결과를 텔레그램으로 보고 — 업무별 성공/실패·소요시간, Gemini·외부 API 호출 수.

TELEGRAM_BOT_TOKEN·TELEGRAM_CHAT_ID 가 둘 다 있을 때만 보낸다(없으면 조용히 건너뜀).
메시지에는 건수·작업명·오류 종류만 담고 API 키·수집 데이터 내용은 넣지 않는다.
발송 실패는 로그만 남기고 배치 자체에는 영향을 주지 않는다.
"""
from __future__ import annotations

import logging
import time
from typing import Callable

import requests

from main import api_meter
from main.redact import redact
from main.config import get_settings
from main.utils import now_kst

logger = logging.getLogger(__name__)

_TG_URL = "https://api.telegram.org/bot{token}/sendMessage"
_MAX_LEN = 3900   # 텔레그램 메시지 한도(4096자) 여유


def _fmt_secs(sec: float) -> str:
    sec = int(round(sec))
    return f"{sec // 60}분 {sec % 60}초" if sec >= 60 else f"{sec}초"


def _short_error(exc: Exception) -> str:
    """오류 요약 — 'HTTP 403', 'RuntimeError: …'(80자). URL 쿼리(키 포함 가능)는 넣지 않는다."""
    resp = getattr(exc, "response", None)
    if resp is not None and getattr(resp, "status_code", None):
        return f"HTTP {resp.status_code}"
    msg = redact(str(exc)).split("?")[0].replace("\n", " ").strip()
    return f"{type(exc).__name__}: {msg[:80]}" if msg else type(exc).__name__


def run_jobs(jobs: list[tuple[str, Callable[[], object]]]) -> list[dict]:
    """작업을 순서대로 실행하며 결과를 기록한다(한 작업 실패가 다음 작업을 막지 않음)."""
    results = []
    for label, job in jobs:
        t0 = time.monotonic()
        try:
            out = job()
            item = {"label": label, "ok": True, "secs": time.monotonic() - t0}
            failed = out.get("failed") if isinstance(out, dict) else None
            if failed:   # 부분 실패(예: CMA 금리 일부 증권사) — 성공으로 세되 ⚠️ 로 사유 표시
                names = ", ".join(f"{f.get('company')}({f.get('error')})" for f in failed[:4])
                item["warn"] = names + (f" 외 {len(failed) - 4}곳" if len(failed) > 4 else "")
            results.append(item)
        except Exception as exc:  # noqa: BLE001
            logger.exception("%s 워밍업 실패", label)
            results.append({"label": label, "ok": False, "secs": time.monotonic() - t0,
                            "error": _short_error(exc)})
    return results


def _gemini_today() -> int | None:
    """오늘 Gemini 일일 예산 사용량(main/gemini.py 카운터 스냅샷)."""
    try:
        from main.gemini import daily_usage
        return daily_usage()
    except Exception:  # noqa: BLE001
        return None


def build_message(mode: str, results: list[dict], secs: float, calls: dict[str, int]) -> str:
    ok = sum(1 for r in results if r["ok"])
    head = {"morning": "07:00 아침", "leads": "수동(여신 리드)"}.get(mode, "05:00 새벽")
    lines = [f"[증금 인텔리전스] {head} 배치 {'완료' if ok == len(results) else '일부 실패'}",
             f"{now_kst():%Y-%m-%d %H:%M} · {_fmt_secs(secs)} · 성공 {ok}/{len(results)}", ""]
    for r in results:
        mark = "❌" if not r["ok"] else ("⚠️" if r.get("warn") else "✅")
        tail = f" — {r['error']}" if not r["ok"] else (f" — 일부 실패: {r['warn']}" if r.get("warn") else "")
        lines.append(f"{mark} {r['label']} ({_fmt_secs(r['secs'])}){tail}")

    s = get_settings()
    gemini_batch = calls.pop("Gemini", 0)
    used = _gemini_today()
    lines += ["", f"■ Gemini 호출: 이번 배치 {gemini_batch}회"
              + (f" · 오늘 누적 {used}/{s.gemini_max_calls_per_day}" if used is not None else "")]
    total = sum(calls.values())
    lines.append(f"■ 외부 API 호출(이번 배치): 합계 {total:,}회")
    for label, n in sorted(calls.items(), key=lambda kv: -kv[1]):
        lines.append(f"  · {label} {n:,}")
    text = "\n".join(lines)
    return text if len(text) <= _MAX_LEN else text[:_MAX_LEN] + "\n…(생략)"


def send_telegram(text: str) -> bool:
    s = get_settings()
    if not (s.telegram_bot_token and s.telegram_chat_id):
        return False
    try:
        resp = requests.post(_TG_URL.format(token=s.telegram_bot_token),
                             data={"chat_id": s.telegram_chat_id, "text": text,
                                   "disable_web_page_preview": "true"}, timeout=15)
        if not resp.ok:
            logger.warning("텔레그램 발송 실패: HTTP %s", resp.status_code)
        return resp.ok
    except requests.RequestException as exc:
        logger.warning("텔레그램 발송 실패: %s", type(exc).__name__)
        return False


def run_and_report(mode: str, jobs: list[tuple[str, Callable[[], object]]]) -> None:
    before = api_meter.snapshot()
    t0 = time.monotonic()
    results = run_jobs(jobs)
    diff = api_meter.snapshot() - before   # Counter 뺄셈: 증가분만(0 이하는 빠짐)
    try:
        send_telegram(build_message(mode, results, time.monotonic() - t0, dict(diff)))
    except Exception:  # noqa: BLE001 - 보고 실패가 배치를 깨지 않게
        logger.exception("배치 결과 보고 실패")
