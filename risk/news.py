"""심사·리스크 > 리스크 시그널 — 부정 키워드 기사(회생·워크아웃·상폐·감사의견 등) AI 선별.

네이버 뉴스에서 부정 키워드로 최근 2일 기사를 모으고(main.naver_news), Gemini 가 "특정 기업의
신용·담보가치 리스크 사건"을 다룬 기사만 최대 5건 골라 기업명·한 줄 이유를 붙인다(정책 해설·
시황 일반론은 제외). AI 를 못 쓰면 최신순 5건으로 대신 보여준다. 기사 '제목·요약'만 근거로
하도록 프롬프트로 제한한다. 하루 1회 스냅샷(risk_news_snapshots), 07:00 아침 배치에서 재생성
(흐름은 funding/news.py 와 같다).
"""
from __future__ import annotations

import logging
import re
from datetime import timedelta

from main.daily_snapshot import AI_OK, parse_json_obj, table_lock, try_ai
from main.gemini import generate_text
from main.naver_news import NewsFetchError, collect
from main.snapshot_store import get_snapshot, save_snapshot
from main.utils import stamp, today_iso, today_kst

logger = logging.getLogger(__name__)

_TABLE = "risk_news_snapshots"
_PICK = 5
_MAX_CANDIDATES = 40
# 네이버 검색은 본문까지 매칭해 무관한 기사(여행·생활 등)가 섞인다 — 제목에 리스크 단어가 있는 것만 후보로.
_RISK_WORDS = re.compile(r"상폐|상장폐지|회생|워크아웃|부도|감사의견|의견거절|관리종목|횡령|배임|신용등급|강등|"
                         r"PF|기한이익|채무불이행|디폴트|파산|퇴출|거래정지|유동성 위기|자본잠식")

KEYWORDS = ["워크아웃 신청", "회생절차 개시", "상장폐지 결정", "감사의견 거절", "관리종목 지정",
            "부도 처리", "기한이익상실", "신용등급 하향", "횡령 배임 혐의 상장사", "PF 부실 시행사"]


def _candidates() -> list[dict]:
    cutoff = (today_kst() - timedelta(days=2)).isoformat()
    pool = collect(KEYWORDS, display=15, cutoff_date=cutoff)
    pool = [it for it in pool if _RISK_WORDS.search(it["title"])]
    pool.sort(key=lambda x: x["published"], reverse=True)
    return [{"title": it["title"], "url": it["url"], "published": it["published"],
             "summary": it["summary"][:120]} for it in pool[:_MAX_CANDIDATES]]


def _pick_with_ai(part: dict) -> None:
    """try_ai 콜백 — 후보 중 최대 5건 선택 + 기업명·이유. 전부 만든 뒤 한 번에 대입."""
    cands = part["candidates"]
    listing = "\n".join(f"{i}. [{c['published']}] {c['title']} — {c['summary']}" for i, c in enumerate(cands))
    raw = generate_text(
        f"후보 기사:\n{listing}\n\n"
        "한국증권금융 심사·리스크 담당자가 담보 종목·거래 상대방 리스크를 점검하려고 한다. "
        "특정 기업(상장사·금융회사·건설사 등)의 상장폐지·관리종목·회생·워크아웃·부도·감사의견·"
        f"횡령배임·신용등급 하향·PF 부실 같은 구체적 리스크 사건을 다룬 기사를 최대 {_PICK}건 골라라. "
        "제목만 봐도 그 기업의 리스크 사건임이 드러나는 국내 기업 기사만 고르고, 해외 기업·생활·정책 해설·"
        "제도 일반론·시황 기사는 제외해라. 같은 사건은 1건만. 적합한 기사가 적으면 적게 골라도 된다. "
        "각 기사에 해당 기업명(company, 제목·요약에 나온 이름 그대로)과 리스크 요지(reason, 25자 이내)를 붙여라. "
        "제목·요약에 없는 사실은 쓰지 마라. "
        '반드시 JSON으로만: {"picks": [{"idx": 0, "company": "...", "reason": "..."}]}',
        max_output_tokens=4096,   # thinking 토큰도 이 예산을 써서 2048이면 JSON 이 잘렸다
    )
    items, used = [], set()
    for p in parse_json_obj(raw).get("picks") or []:
        try:
            idx = int(p.get("idx"))
        except (TypeError, ValueError, AttributeError):
            continue
        if 0 <= idx < len(cands) and idx not in used:
            used.add(idx)
            txt = lambda k: p.get(k).strip() if isinstance(p.get(k), str) else ""  # noqa: E731
            items.append({**cands[idx], "company": txt("company"), "reason": txt("reason")})
        if len(items) >= _PICK:
            break
    if not items:
        raise ValueError("선별 결과 없음")
    part.update(items=items, picked_by="ai")


def _select(part: dict) -> bool:
    """AI 선별 1회 시도 — 실패하면 최신순으로 채운다. 시도 횟수가 바뀌었는지 돌려준다."""
    before = part.get("gemini_attempts", 0)
    if try_ai(part, _pick_with_ai, "심사·리스크 뉴스") != AI_OK and not part.get("items"):
        part.update(items=[{**c, "company": "", "reason": ""} for c in part["candidates"][:_PICK]],
                    picked_by="latest")
    return part.get("gemini_attempts", 0) != before


def get_risk_news(rebuild: bool = False) -> dict:
    today = today_iso()
    with table_lock(_TABLE):
        snap = get_snapshot(_TABLE, today)
        if snap is None or rebuild:
            try:
                fresh = {"generated_at": stamp(), "candidates": _candidates(), "items": [],
                         "picked_by": None, "gemini_attempts": 0}
                if fresh["candidates"]:
                    _select(fresh)
                    save_snapshot(_TABLE, today, fresh)
                snap = fresh if fresh["candidates"] or snap is None else snap   # 아침 재생성 실패 시 새벽 결과 유지
            except NewsFetchError as exc:
                logger.warning("심사·리스크 뉴스 수집 실패: %s", exc)
                snap = snap or {"items": [], "candidates": [], "picked_by": None}
        elif snap.get("picked_by") == "latest" and snap.get("candidates"):
            if _select(snap):   # 앞서 AI 가 실패했으면 상한 안에서 다시 선별
                save_snapshot(_TABLE, today, snap)
    return {"generated_at": snap.get("generated_at"), "items": snap.get("items") or [],
            "picked_by": snap.get("picked_by"), "candidate_count": len(snap.get("candidates") or [])}
