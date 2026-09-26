"""증권대차 탭 — 공매도·주식대차 / 채권대차 관련 뉴스 3건씩(네이버 뉴스 검색, 실데이터).

하루 1회 수집해 스냅샷으로 캐시한다. 대차잔고·상위종목 등 KPI 는 정식 연동 전이라 화면에
"준비중" 안내만 있고(lending.html), 이 뉴스 목록만 실제 검색 결과다.

네이버 검색이 한 주제라도 통째로 실패하면(NewsFetchError) 그 결과를 오늘 스냅샷으로 굳히지
않는다 — 모든 주제가 실패하면 가장 최근 스냅샷을 대신 돌려주고, 일부만 실패하면 이번 응답에만
쓰고 다음 요청에서 다시 수집한다.
"""
from __future__ import annotations

import logging
import re

from main.daily_snapshot import table_lock
from main.naver_news import NewsFetchError, collect
from main.snapshot_store import get_snapshot, latest_snapshot, save_snapshot
from main.utils import today_iso

logger = logging.getLogger(__name__)

_TABLE = "lending_news_snapshots"

_TOPICS = {
    "stock": ["공매도", "주식 대차잔고"],
    "bond": ["채권대차", "국채 대차거래"],
}

# "공매도" 단독 검색은 가상자산 관련 기사(청산·강제청산 등)까지 끌어와 무관한 기사가
# 섞이는 경우가 있어, 증권시장과 무관해 보이는 코인 관련 기사만 걸러낸다.
_CRYPTO_NOISE = re.compile(r"코인|가상자산|비트코인|이더리움|ZEC|NFT|암호화폐|스테이블코인")


def _topic_news(keywords: list[str], limit: int = 3) -> list[dict]:
    """주제별 관련도순 검색 결과를 최신순 limit 건으로(화면은 날짜만 쓰므로 published=날짜)."""
    pool = collect(keywords, display=10, sort="sim", exclude=_CRYPTO_NOISE)
    pool.sort(key=lambda x: x["published"], reverse=True)
    return [{"title": it["title"], "url": it["url"], "published": it["published_date"]}
            for it in pool[:limit]]


_SCHEMA_V = 2  # v2: 가상자산(코인) 관련 잡음 기사 제외 필터 추가


def get_lending_news(rebuild: bool = False) -> dict:
    """rebuild=True(07:00 아침 배치)면 오늘 스냅샷이 있어도 다시 검색한다. 한 주제라도 실패하면
    교체하지 않고 기존 스냅샷을 유지한다."""
    today = today_iso()
    with table_lock(_TABLE):
        snap = get_snapshot(_TABLE, today)
        if snap is not None and snap.get("v") != _SCHEMA_V:
            snap = None
        if snap is not None and not rebuild:
            return snap

        payload: dict = {"v": _SCHEMA_V}
        failed = []
        for topic, kws in _TOPICS.items():
            try:
                payload[topic] = _topic_news(kws)
            except NewsFetchError as exc:
                logger.warning("대차 뉴스 검색 실패(%s): %s", topic, exc)
                payload[topic] = []
                failed.append(topic)

        if failed and snap is not None:
            return snap   # 아침 재검색 실패 → 새벽 스냅샷 유지
        if len(failed) == len(_TOPICS):
            stale = latest_snapshot(_TABLE)
            if stale is not None:
                return {**stale, "stale": True}
            return payload
        if not failed:
            save_snapshot(_TABLE, today, payload)
        return payload
