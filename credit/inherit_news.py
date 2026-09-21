"""여신·심사 메인 화면 — 상속·증여 관련 뉴스 동향(참고용, AI 관련도 판단).

DART majorstock.json 의 report_resn(leads.py)은 5% 대량보유·1%p 이상 지분 변동처럼
신고 의무 기준을 넘는 건만 잡는다. 소액 지분 증여, 비상장 지주회사를 통한 이전,
공시 전 단계 등은 API로 못 잡는 공백이 있어, 네이버 뉴스에서 오너家 지분 상속·증여
관련 기사를 모으고 Gemini로 무관한 기사(상속세 정책 등)를 걸러 보완 정보로 보여준다.

어디까지나 언론 보도 기반 참고 정보다 — 실제 지분 이전 여부·규모·시점은 DART 공시
원문에서 별도 확인이 필요하며, Gemini 판단도 주어진 기사 '제목'만 근거로 하고
제목에 없는 사실을 지어내지 않도록 프롬프트로 제약한다.

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
_TABLE = "credit_inherit_news_snapshots"

_KEYWORDS = [
    "오너 지분 증여", "최대주주 지분 상속", "지분 증여 공시", "상속 지분 매각",
    "오너家 지분 매입", "2세 승계 지분", "가업승계 지분", "특수관계인 지분 이전",
]
_STRIP_TAG = re.compile(r"<[^>]+>")

_SYSTEM_PROMPT = (
    "너는 한국증권금융(KSFC) 여신심사 담당자를 위한 리서치 어시스턴트야.\n"
    "아래는 뉴스 기사 제목 목록이다. **국내 상장회사** 오너·대주주 개인 또는 그 자녀 등 "
    "특수관계인의 '주식 상속·증여' 이벤트뿐 아니라, 경영권 승계 과정에서 나타나는 지분 "
    "매입·확대·축소·특수관계인 회사로의 지분 이전처럼 '오너家 승계·지분 이동'과 관련된 "
    "기사도 관련 있다고 판단해라(실제 상속·증여 재원 마련용 대출 수요로 이어질 수 있는 "
    "선행 신호이기 때문). 당사는 국내 여신 영업만 하므로, 버크셔 해서웨이·해외 기업처럼 "
    "국내 상장회사가 아닌 외국 기업 기사는 내용이 아무리 비슷해도 반드시 관련 없음으로 "
    "처리해. 특정 회사·인물의 지분 이동과 무관한 상속세·증여세 정책·세법 개정 같은 일반 "
    "기사도 관련 없음으로 처리해.\n"
    "각 줄에 대해 제목에 적힌 내용만 근거로 판단하고, 제목에 없는 회사명·금액·지분율· "
    "날짜를 지어내지 마.\n"
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


def _collect_candidates(limit: int = 35) -> list[dict]:
    seen: set[str] = set()
    pool: list[dict] = []
    for kw in _KEYWORDS:
        try:
            items = _search(kw)
        except requests.RequestException as exc:
            logger.warning("상속·증여 뉴스 검색 실패(%s): %s", kw, exc)
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
    """Gemini 호출 자체가 실패하면(네트워크·쿼터 등) 예외를 그대로 올린다 — 호출자가
    "전부 무관 판정"과 "호출 실패"를 구분해 실패일 때만 재시도하도록 하기 위함."""
    if not candidates:
        return []
    listing = "\n".join(f"{i + 1}. {c['title']}" for i, c in enumerate(candidates))
    resp = generate_text(
        f"뉴스 제목 목록:\n{listing}",
        system_instruction=_SYSTEM_PROMPT,
        max_output_tokens=1024,
    )
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
    return out[:15]


_SCHEMA_V = 4  # v4: 후보 뉴스와 AI 판단을 분리 저장 + gemini_attempts 재시도 상한 추가.
                # 이전엔 AI 호출이 하루 첫 시도에 실패(예: 무효 키 폴백 등)하면 빈 결과가
                # 그날 스냅샷으로 굳어버려 이후 요청도 계속 빈 목록만 봤다(2026-09-22 확인).


def _maybe_filter(payload: dict, force: bool = False) -> dict:
    """AI 판단이 비어 있으면(또는 force=True 면) 일일 한도 내에서 한 번 더 시도.

    "전부 무관 판정"과 "Gemini 호출 자체 실패"를 구분해, 호출 실패일 때만 다음 요청에서
    재시도한다(policy/briefing.py 의 _maybe_add_briefing 과 동일한 원칙).
    """
    s = get_settings()
    has = bool(payload.get("items"))
    cap = s.policy_max_gemini_calls_per_day

    if has and not force:
        return payload
    if not s.gemini_api_keys:
        return payload
    if payload.get("gemini_attempts", 0) >= cap:
        return payload

    payload["gemini_attempts"] = payload.get("gemini_attempts", 0) + 1
    try:
        payload["items"] = _filter_with_ai(payload.get("candidates") or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("상속·증여 뉴스 AI 판단 실패(%d/%d회): %s", payload["gemini_attempts"], cap, exc)
    return payload


def get_inherit_news(force: bool = False) -> dict:
    today = datetime.now(KST).date().isoformat()
    snap = get_snapshot(_TABLE, today)
    if snap is not None and snap.get("v") != _SCHEMA_V:
        snap = None

    if snap is None:
        snap = {"v": _SCHEMA_V, "candidates": _collect_candidates(), "items": [], "gemini_attempts": 0}
        save_snapshot(_TABLE, today, snap)  # 후보 목록 먼저 저장(재수집 방지, AI 판단은 아래에서)

    before = (bool(snap.get("items")), snap.get("gemini_attempts", 0))
    snap = _maybe_filter(snap, force=force)
    if (bool(snap.get("items")), snap.get("gemini_attempts", 0)) != before:
        save_snapshot(_TABLE, today, snap)

    return {"items": snap.get("items") or [], "v": _SCHEMA_V}
