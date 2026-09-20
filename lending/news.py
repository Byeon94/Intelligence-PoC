"""증권대차 탭 — 공매도·주식대차 / 채권대차 관련 뉴스 3건씩(네이버 뉴스 API, 실데이터).

하루 1회 수집해 스냅샷으로 캐시. (대차잔고·상위종목 등 KPI는 sample.py 예시값이지만
이 뉴스 목록은 실제 검색 결과다.)
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
from main.snapshot_store import get_snapshot, save_snapshot

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

_ENDPOINT = "https://openapi.naver.com/v1/search/news.json"
_TABLE = "lending_news_snapshots"

_TOPICS = {
    "stock": ["공매도", "주식 대차잔고"],
    "bond": ["채권대차", "국채 대차거래"],
}

_STRIP_TAG = re.compile(r"<[^>]+>")
# "공매도" 단독 검색은 가상자산 관련 기사(청산·강제청산 등)까지 끌어와 무관한 기사가
# 섞이는 경우가 있어, 증권시장과 무관해 보이는 코인 관련 기사만 걸러낸다.
_CRYPTO_NOISE = re.compile(r"코인|가상자산|비트코인|이더리움|ZEC|NFT|암호화폐|스테이블코인")


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


def _search(keyword: str, display: int = 10) -> list[dict]:
    resp = requests.get(
        _ENDPOINT, headers=_headers(),
        params={"query": keyword, "display": display, "sort": "sim"},
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


def _collect(keywords: list[str], limit: int = 3) -> list[dict]:
    seen: set[str] = set()
    pool: list[dict] = []
    for kw in keywords:
        try:
            items = _search(kw)
        except requests.RequestException as exc:
            logger.warning("대차 뉴스 검색 실패(%s): %s", kw, exc)
            continue
        for it in items:
            if _CRYPTO_NOISE.search(it["title"]):
                continue
            key = re.sub(r"\W+", "", it["title"])[:40]
            if not key or key in seen:
                continue
            seen.add(key)
            pool.append(it)
    pool.sort(key=lambda x: x["published"], reverse=True)
    return pool[:limit]


_SCHEMA_V = 2  # v2: 가상자산(코인) 관련 잡음 기사 제외 필터 추가


def get_lending_news() -> dict:
    today = datetime.now(KST).date().isoformat()
    snap = get_snapshot(_TABLE, today)
    if snap is not None and snap.get("v") != _SCHEMA_V:
        snap = None
    if snap is not None:
        return snap
    payload = {topic: _collect(kws) for topic, kws in _TOPICS.items()}
    payload["v"] = _SCHEMA_V
    save_snapshot(_TABLE, today, payload)
    return payload
