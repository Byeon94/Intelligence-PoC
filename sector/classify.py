"""전 상장종목 업종 분류(Gemini) — 배치 전용.

KRX가 전 종목 업종분류를 무료로 제공하지 않아, Gemini에 종목코드·종목명을 배치로 보내
SECTOR_TAXONOMY 중 하나로 분류시킨다. 업종 구성은 거의 바뀌지 않으므로 매일이 아니라
_REFRESH_DAYS 이상 지났을 때만 재분류하고, 그 사이엔 저장된 스냅샷을 그대로 쓴다.

호출 비용(순차 Gemini 배치 호출 ~20회, 수 분 소요) 때문에 실제 재분류는 반드시
refresh_sector_classification()으로만 하고, 이는 /internal/warmup 배치에서만 부른다.
화면(get_sector_map 등)은 get_cached_classification()으로 저장된 결과만 읽어, 첫 방문
사용자 요청이 대기 중 Gemini 배치를 트리거하는 일이 없게 한다(credit/leads.py 와 동일한
"배치 전용" 원칙).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from credit.equity import listed_snapshot
from main.gemini import generate_text
from main.snapshot_store import get_snapshot, save_snapshot

from .constituents import SECTOR_TAXONOMY

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

_TABLE = "sector_classification_snapshots"
_KEY = "latest"
_REFRESH_DAYS = 30      # 업종 구성은 거의 안 바뀌므로 이 이상 지나야 재분류
_BATCH_SIZE = 150

_PROMPT_TMPL = (
    "아래는 한국 코스피·코스닥 상장회사 목록(종목코드 종목명)이다. 각 회사를 다음 업종 "
    "카테고리 중 정확히 하나로 분류해줘. 명확히 맞는 카테고리가 없으면 반드시 '기타'로 분류해. "
    "추측이 아니라 사업 내용을 기준으로 판단하고, 목록의 모든 코드를 빠짐없이 포함해.\n\n"
    "업종 카테고리: " + ", ".join(SECTOR_TAXONOMY) + "\n\n"
    "회사 목록:\n{companies}\n\n"
    "설명 없이 JSON 배열만 출력해:\n"
    '[{{"code":"005930","sector":"반도체 및 관련장비"}}, ...]'
)


def _classify_batch(stocks: list[dict]) -> dict[str, str]:
    companies_txt = "\n".join(f"{s['code']} {s['name']}" for s in stocks)
    prompt = _PROMPT_TMPL.format(companies=companies_txt)
    text = generate_text(prompt, max_output_tokens=8192, thinking=False)
    a, b = text.find("["), text.rfind("]")
    if a < 0 or b < 0:
        raise ValueError("JSON 배열 응답 없음")
    arr = json.loads(text[a : b + 1])
    valid = set(SECTOR_TAXONOMY)
    out: dict[str, str] = {}
    for item in arr:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        sector = str(item.get("sector") or "").strip()
        if len(code) == 6 and code.isdigit() and sector in valid:
            out[code] = sector
    return out


def _classify_all(stocks: list[dict]) -> dict[str, str]:
    result: dict[str, str] = {}
    for i in range(0, len(stocks), _BATCH_SIZE):
        batch = stocks[i : i + _BATCH_SIZE]
        try:
            got = _classify_batch(batch)
            result.update(got)
            logger.info("업종 분류 배치 %d~%d: %d/%d건", i, i + len(batch), len(got), len(batch))
        except Exception as exc:  # noqa: BLE001 - 배치 하나 실패해도 나머지는 계속
            logger.warning("업종 분류 배치 실패(%d~%d): %s", i, i + len(batch), exc)
    return result


def get_cached_classification() -> dict[str, str]:
    """저장된 최신 분류 스냅샷만 읽는다(Gemini 호출 없음) — 화면 요청에서 안전하게 쓰기 위함."""
    snap = get_snapshot(_TABLE, _KEY)
    return (snap or {}).get("classified") or {}


def refresh_sector_classification(force: bool = False) -> dict[str, str]:
    """스냅샷이 없거나 _REFRESH_DAYS 이상 지났을 때만 Gemini로 전 종목을 재분류해 저장한다.

    호출 비용이 크므로(전 상장종목을 배치로 나눠 순차 Gemini 호출) /internal/warmup
    배치에서만 호출해야 한다(화면 라우트에서 직접 호출 금지).
    """
    snap = get_snapshot(_TABLE, _KEY)
    if snap and snap.get("classified") and not force:
        generated = _parse_dt(snap.get("generated_at"))
        if generated and datetime.now(KST) - generated < timedelta(days=_REFRESH_DAYS):
            return snap["classified"]

    stocks = [s for s in listed_snapshot() if s.get("code") and s.get("name")]
    if not stocks:
        logger.info("업종 분류: 전 종목 스냅샷을 못 가져와 건너뜀")
        return (snap or {}).get("classified") or {}

    classified = _classify_all(stocks)
    if len(classified) < len(stocks) * 0.5:
        # 절반도 못 채우면 부분 실패로 보고 이전 스냅샷을 그대로 유지(덮어쓰지 않음)
        logger.warning("업종 분류 결과가 너무 적어(%d/%d) 저장하지 않음", len(classified), len(stocks))
        return (snap or {}).get("classified") or {}

    payload = {
        "generated_at": datetime.now(KST).isoformat(),
        "count": len(classified),
        "total_stocks": len(stocks),
        "classified": classified,
    }
    save_snapshot(_TABLE, _KEY, payload)
    logger.info("업종 분류 갱신 완료: %d/%d건", len(classified), len(stocks))
    return classified


def _parse_dt(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None
