"""단기자금 > 원화 — 자금중개사 일일 시황 PDF를 AI로 요약한 "시황 브리프" 2종.

- KIDB 머니마켓브리프: kidb.com 자금 자료실 게시판 최신 글 → 첨부 PDF(직접 링크)
- 한국자금중개 시황 브리프: kmbco.com "콜 레포 시장 동향" 목록 최신 행 → 첨부 PDF(POST 다운로드)

흐름(출처별 테이블 락 안에서): 목록에서 최신 자료(날짜·링크) 확인(30분 캐시) → 그 자료 날짜의
스냅샷이 이미 요약돼 있으면 그대로 반환 → 없으면 PDF를 내려받아 Gemini 에 첨부해 요약(try_ai,
스냅샷당 시도 상한) → 저장. 즉 AI 호출은 "새 자료가 올라왔을 때 출처당 1회"뿐이다.
요약은 PDF 에 적힌 수치만 인용하도록 프롬프트로 제한한다.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from main.cache import ttl_cache
from main.config import get_settings
from main.daily_snapshot import AI_CAPPED, AI_FAILED, AI_NO_KEY, parse_json_obj, table_lock, try_ai
from main.gemini import generate_text
from main.snapshot_store import get_snapshot, latest_snapshot, save_snapshot
from main.utils import stamp

logger = logging.getLogger(__name__)

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"}

_KIDB_LIST = "https://www.kidb.com/bbs/board.php?bo_table=money"
_KMB_LIST = "https://www.kmbco.com/kor/trendi/money_trend.do"
_KMB_DOWNLOAD = "https://www.kmbco.com/common/downloadFile.do"

SOURCES = {   # 키 → (화면 이름, 스냅샷 테이블 — 자료 날짜별 1행)
    "kidb": ("KIDB 머니마켓브리프", "funding_kidb_brief_snapshots"),
    "kmb": ("한국자금중개 시황 브리프", "funding_kmb_brief_snapshots"),
}

_MAX_BULLETS = 6

_SYSTEM_PROMPT = (
    "너는 한국증권금융(KSFC) 단기자금 운용 담당자를 위한 시황 요약 어시스턴트야. 첨부 PDF는 "
    "자금중개회사가 매일 내는 단기자금(콜·RP·CD·CP·전단채·통안채·MMF·외화자금) 시황 자료다.\n"
    f"PDF 내용만 근거로 핵심 {_MAX_BULLETS}개 항목을 뽑아라.\n"
    "- 각 항목은 head(주제, 2~10자, 예: '콜', 'CD·CP', '전단채·CP 발행', 'MMF', '통안·국고 단기물', "
    "'기일물 RP', '외화자금(스왑)', '거래량', '딜러 코멘트')와 text(핵심 수치를 넣은 한 문장, 90자 이내)로 쓴다.\n"
    "- text 는 head 단어를 반복하지 말고 수치부터 간결하게 써라(개조식, '~함/~임' 체). "
    "예: head '콜', text '3.074%(9/22, −0.4bp), 기준금리 대비 +7bp — 지준 2.5조 잉여, 익일물 거래 12.7조'.\n"
    "- 수치·날짜는 PDF에 있는 것만 그대로 인용하고, 전일 대비 변동은 괄호로 표기해라(예: 3.074%(−0.4bp)). "
    "PDF에 없는 내용·수치를 지어내지 마라. PDF에 없는 주제는 건너뛰어라.\n"
    "- 영어 단어를 섞지 말고 한국어로 써라(콜·RP·CD·CP·MMF 같은 시장 용어 약어는 허용).\n"
    "- summary: 전체를 종합해 오늘 단기자금 시장의 흐름과 KSFC 단기자금 운용 시사점을 한 문장, 80자 이내로.\n"
    '반드시 JSON으로만 답해: {"bullets": [{"head": "...", "text": "..."}], "summary": "..."}'
)


def _get(url: str, **kw) -> requests.Response:
    resp = requests.get(url, headers=_UA, timeout=20, **kw)
    resp.raise_for_status()
    return resp


# ── 최신 자료 찾기(목록 페이지) ─────────────────────────────────────────────
@ttl_cache(60 * 30)
def _latest_kidb() -> dict:
    """KIDB 게시판 첫 글 → {"date", "title", "url"(게시글), "pdf_url"}."""
    soup = BeautifulSoup(_get(_KIDB_LIST).text, "html.parser")
    for a in soup.select('a[href*="bo_table=money"][href*="wr_id="]'):
        title = a.get_text(" ", strip=True)
        m = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", title)
        if "머니마켓" in title and m:
            post_url = urljoin(_KIDB_LIST, a["href"])
            post = BeautifulSoup(_get(post_url).text, "html.parser")
            link = post.select_one('a[href*="/data/file/money/"][href$=".pdf"]')
            if not link:
                raise RuntimeError("KIDB 게시글에서 PDF 첨부를 찾지 못했습니다.")
            return {"date": "-".join(m.groups()), "title": title, "url": post_url,
                    "pdf_url": urljoin(post_url, link["href"])}
    raise RuntimeError("KIDB 목록에서 머니마켓브리프 글을 찾지 못했습니다.")


@ttl_cache(60 * 30)
def _latest_kmb() -> dict:
    """한국자금중개 목록 첫 행 → {"date", "title", "url"(목록), "seq", "t_type"}."""
    soup = BeautifulSoup(_get(_KMB_LIST).text, "html.parser")
    for tr in soup.select("tr"):
        a = tr.select_one('a[href*="fnFileDown"]')
        title_td = tr.select_one("td.left")
        if not a or not title_td:
            continue
        title = title_td.get_text(" ", strip=True)
        m_date = re.search(r"(\d{4})-(\d{2})-(\d{2})", title)
        m_arg = re.search(r"fnFileDown\('(\d+)'\s*,\s*'(\d+)'\)", a["href"])
        if m_date and m_arg:
            return {"date": "-".join(m_date.groups()), "title": title, "url": _KMB_LIST,
                    "seq": m_arg.group(1), "t_type": m_arg.group(2)}
    raise RuntimeError("한국자금중개 목록에서 시장 동향 자료를 찾지 못했습니다.")


def _latest(key: str) -> dict:
    return _latest_kidb() if key == "kidb" else _latest_kmb()


def _download_pdf(key: str, meta: dict) -> bytes:
    if key == "kidb":
        data = _get(meta["pdf_url"]).content
    else:
        resp = requests.post(_KMB_DOWNLOAD, data={"seq": meta["seq"], "t_type": meta["t_type"]},
                             headers={**_UA, "Referer": _KMB_LIST}, timeout=30)
        resp.raise_for_status()
        data = resp.content
    if not data.startswith(b"%PDF"):
        raise RuntimeError(f"{SOURCES[key][0]} 첨부가 PDF가 아닙니다.")
    return data


# ── AI 요약 ────────────────────────────────────────────────────────────────
def _text(v) -> str:
    return v.strip() if isinstance(v, str) else ""


def _summarize(key: str, payload: dict) -> None:
    """try_ai 콜백 — PDF 첨부 요약. 전부 만든 뒤 한 번에 대입(실패 시 payload 불변)."""
    pdf = _download_pdf(key, payload)
    raw = generate_text(
        f"첨부한 '{payload['title']}' 자료를 요약해줘.",
        system_instruction=_SYSTEM_PROMPT, max_output_tokens=2048, pdf=pdf,
    )
    obj = parse_json_obj(raw)
    bullets = []
    for b in obj.get("bullets") or []:
        if isinstance(b, dict) and _text(b.get("head")) and _text(b.get("text")):
            bullets.append({"head": _text(b["head"]), "text": _text(b["text"])})
    if len(bullets) < 2:
        raise ValueError("요약 항목이 부족합니다")
    payload.update(bullets=bullets[:_MAX_BULLETS], summary=_text(obj.get("summary")) or None,
                   briefed_at=stamp(), note=None)


def get_brief(key: str) -> dict:
    name, table = SOURCES[key]
    with table_lock(table):
        try:
            meta = _latest(key)
        except Exception as exc:  # noqa: BLE001 - 사이트 장애 → 마지막 저장본
            logger.warning("%s 목록 조회 실패: %s", name, exc)
            stale = latest_snapshot(table)
            if stale:
                return {**stale, "stale": True}
            raise

        snap = get_snapshot(table, meta["date"])
        if snap is None:
            snap = {"key": key, "name": name, "doc_date": meta["date"], "title": meta["title"],
                    "url": meta["url"], "pdf_url": meta.get("pdf_url"),
                    "seq": meta.get("seq"), "t_type": meta.get("t_type"),
                    "bullets": None, "summary": None, "briefed_at": None, "note": None,
                    "gemini_attempts": 0}
        if not snap.get("bullets"):
            status = try_ai(snap, lambda p: _summarize(key, p), name)
            if status == AI_NO_KEY:
                snap["note"] = "AI 요약은 GEMINI_API_KEY 등록 후 제공됩니다. 원문에서 확인해주세요."
            elif status == AI_CAPPED:
                cap = get_settings().ai_retries_per_snapshot
                snap["note"] = f"AI 요약 재시도 한도({cap}회)에 도달했습니다. 원문에서 확인해주세요."
            elif status == AI_FAILED:
                snap["note"] = "AI 요약에 실패했습니다. 잠시 후 다시 시도합니다."
            save_snapshot(table, meta["date"], snap)
        return snap


_PUBLIC = ("key", "name", "doc_date", "title", "url", "bullets", "summary", "briefed_at", "note", "stale")


def get_funding_briefs() -> dict:
    """원화 탭 시황 브리프 2종 — 한쪽이 실패해도 다른 쪽은 보여준다."""
    items = []
    for key, (name, _table) in SOURCES.items():
        try:
            snap = get_brief(key)
            items.append({k: snap.get(k) for k in _PUBLIC})
        except Exception as exc:  # noqa: BLE001
            logger.exception("%s 조회 실패", name)
            items.append({"key": key, "name": name, "error": f"{name}를 불러오지 못했습니다.",
                          "reason": _reason(exc), "url": _LIST_URLS[key]})
    return {"items": items}


# 실패 시 화면에 원문 게시판 링크를 대신 보여준다(요약은 못 해도 원문은 바로 볼 수 있게).
_LIST_URLS = {"kidb": _KIDB_LIST, "kmb": _KMB_LIST}


def _reason(exc: Exception) -> str:
    """오류 원인 코드(진단용) — 예: 'HTTP 403'. 서버 내부 정보는 담지 않는다."""
    resp = getattr(exc, "response", None)
    if resp is not None and getattr(resp, "status_code", None):
        return f"HTTP {resp.status_code}"
    return type(exc).__name__
