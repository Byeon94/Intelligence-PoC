"""여신·심사 메인 화면 — 우리사주(유상증자·IPO) 관련 뉴스 동향(참고용, AI 관련도 판단).

DART 공시(leads.py)는 유상증자·IPO 접수 사실만 잡고, 실제 우리사주조합 배정 규모·
청약 경쟁률·직원 반응 같은 내용은 공시 원문보다 언론 보도가 먼저·자세히 다루는
경우가 많아, 네이버 뉴스에서 우리사주 배정·청약 관련 기사를 모으고 Gemini로
무관한 기사(우리사주 제도 일반론 등)를 걸러 보완 정보로 보여준다.

어디까지나 언론 보도 기반 참고 정보다 — 실제 배정 물량·청약률은 DART 공시 원문에서
별도 확인이 필요하며, Gemini 판단도 주어진 기사 '제목'만 근거로 하고 제목에 없는
사실을 지어내지 않도록 프롬프트로 제약한다(inherit_news.py 와 동일한 원칙).

하루 1회 수집해 스냅샷으로 캐시(main.snapshot_store).
"""
from __future__ import annotations

import html as _html
import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import requests

from main.config import get_settings
from main.gemini import generate_text
from main.snapshot_store import get_snapshot, save_snapshot

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

_ENDPOINT = "https://openapi.naver.com/v1/search/news.json"
_TABLE = "credit_esop_news_snapshots"

_KEYWORDS = ["우리사주조합 배정", "우리사주 청약", "유상증자 우리사주", "공모주 우리사주"]
_STRIP_TAG = re.compile(r"<[^>]+>")

_SYSTEM_PROMPT = (
    "너는 한국증권금융(KSFC) 여신심사 담당자를 위한 리서치 어시스턴트야.\n"
    "아래는 뉴스 기사 제목 목록이다. 특정 상장(예정) 회사의 '유상증자' 또는 'IPO(공모)'에서 "
    "우리사주조합이 주식을 배정받거나 청약하는 이벤트를 다루는 기사만 관련 있다고 판단해라. "
    "우리사주 제도 자체에 대한 일반론·법 개정 기사처럼 특정 회사의 배정·청약과 무관한 기사는 "
    "관련 없음으로 처리해.\n"
    "각 줄에 대해 제목에 적힌 내용만 근거로 판단하고, 제목에 없는 회사명·금액·수량·날짜를 "
    "지어내지 마.\n"
    "출력 형식: 각 줄에 '번호. 판단' — 관련 있으면 어느 회사·어떤 맥락인지 한 문장으로, "
    "관련 없으면 정확히 '관련 없음'이라고만 써. 번호는 입력 목록의 순번과 반드시 일치시켜라. "
    "다른 설명·소제목 없이 목록만 출력해."
)


def _clean(text: str) -> str:
    return _html.unescape(_STRIP_TAG.sub("", text or "")).strip()


def _headers() -> dict:
    s = get_settings()
    if not (s.naver_client_id and s.naver_client_secret):
        raise RuntimeError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 미설정")
    return {
        "X-Naver-Client-Id": s.naver_client_id,
        "X-Naver-Client-Secret": s.naver_client_secret,
    }


def _search(keyword: str, display: int = 15) -> list[dict]:
    resp = requests.get(
        _ENDPOINT, headers=_headers(),
        params={"query": keyword, "display": display, "sort": "date"},
        timeout=10,
    )
    resp.raise_for_status()
    out = []
    for it in resp.json().get("items", []):
        try:
            pub = parsedate_to_datetime(it["pubDate"]).astimezone(KST)
        except (KeyError, ValueError, TypeError):
            continue
        out.append({
            "title": _clean(it.get("title")),
            "url": it.get("originallink") or it.get("link"),
            "published": pub.date().isoformat(),
        })
    return out


def _collect_candidates(limit: int = 20) -> list[dict]:
    seen: set[str] = set()
    pool: list[dict] = []
    for kw in _KEYWORDS:
        try:
            items = _search(kw)
        except requests.RequestException as exc:
            logger.warning("우리사주 뉴스 검색 실패(%s): %s", kw, exc)
            continue
        for it in items:
            key = re.sub(r"\W+", "", it["title"])[:40]
            if not key or key in seen:
                continue
            seen.add(key)
            pool.append(it)
    pool.sort(key=lambda x: x["published"], reverse=True)
    return pool[:limit]


def _filter_with_ai(candidates: list[dict]) -> list[dict]:
    if not candidates:
        return []
    listing = "\n".join(f"{i + 1}. {c['title']}" for i, c in enumerate(candidates))
    try:
        resp = generate_text(
            f"뉴스 제목 목록:\n{listing}",
            system_instruction=_SYSTEM_PROMPT,
            max_output_tokens=1024,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("우리사주 뉴스 AI 판단 실패: %s", exc)
        return []

    verdicts: dict[int, str] = {}
    for line in resp.splitlines():
        m = re.match(r"\s*(\d+)\.\s*(.+)", line)
        if m:
            verdicts[int(m.group(1))] = m.group(2).strip()

    out = []
    for i, c in enumerate(candidates, 1):
        note = verdicts.get(i)
        if not note or "관련 없음" in note:
            continue
        out.append({**c, "ai_note": note})
    return out[:8]


_SCHEMA_V = 1


def get_esop_news(force: bool = False) -> dict:
    today = datetime.now(KST).date().isoformat()
    if not force:
        snap = get_snapshot(_TABLE, today)
        if snap is not None and snap.get("v") == _SCHEMA_V:
            return snap
    candidates = _collect_candidates()
    items = _filter_with_ai(candidates)
    payload = {"items": items, "v": _SCHEMA_V}
    save_snapshot(_TABLE, today, payload)
    return payload
