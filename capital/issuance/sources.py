"""발행시장 일정 수집.

- IPO 수요예측 / 공모청약 / 신규상장 : 38커뮤니케이션(38.co.kr) 스크랩 (EUC-KR)
- 유상증자 결정 공시 : 금융감독원 DART OpenAPI (DART_API_KEY 있을 때만)

정규화 이벤트: {date, end, type, company, detail, url}
  type ∈ {"수요예측", "청약", "상장", "유상증자"}
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from main.config import get_settings

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36"

_38_VIEWS = [
    ("수요예측", "r"),
    ("청약", "k"),
    ("상장", "nw"),  # 페이지 구조상 항목이 없을 수 있음(그래도 시도)
]

# 상장(o=nw) 표는 헤더가 '신규상장일' 형태라 별도 처리

_DATE_RE = re.compile(r"(\d{4})\.(\d{2})\.(\d{2})(?:\s*~\s*(\d{2})\.(\d{2}))?")


def _first_dates(text: str) -> tuple[str, str | None]:
    m = _DATE_RE.search(text or "")
    if not m:
        return "", None
    y, mo, d = m.group(1), m.group(2), m.group(3)
    start = f"{y}-{mo}-{d}"
    end = f"{y}-{m.group(4)}-{m.group(5)}" if m.group(4) else None
    return start, end


def _fetch_38(view: str) -> list[dict]:
    r = requests.get(
        f"http://www.38.co.kr/html/fund/index.htm?o={view}",
        headers={"User-Agent": _UA}, timeout=15,
    )
    r.raise_for_status()
    r.encoding = "euc-kr"
    soup = BeautifulSoup(r.text, "html.parser")

    table = None
    for t in soup.find_all("table"):
        h = t.get_text(" ", strip=True)
        if "종목명" in h and _DATE_RE.search(h) and ("주간사" in h or "주관사" in h or "공모가" in h):
            table = t
            break
    if table is None:
        return []

    rows: list[dict] = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        a = tr.find("a", href=re.compile(r"o=v"))
        cells = [re.sub(r"\s+", " ", td.get_text(" ", strip=True)) for td in tds]
        name = cells[0].strip()
        if not a or not name or name.startswith("종목") or "공모뉴스" in cells[0]:
            continue
        start, end = _first_dates(cells[1])
        if not start:
            # 날짜가 다른 칼럼에 있을 수 있음
            for c in cells[1:4]:
                start, end = _first_dates(c)
                if start:
                    break
        if not start:
            continue
        hope = next((c for c in cells if "~" in c and "," in c), "")
        lead = cells[-1] if cells[-1] and cells[-1] != "-" else (cells[-2] if len(cells) > 1 else "")
        detail = " · ".join(x for x in [f"희망 {hope}원" if hope else "", lead] if x)
        rows.append({
            "company": name,
            "url": "http://www.38.co.kr/html/fund/" + a["href"].lstrip("./"),
            "detail": detail,
        })
        _stamp(rows[-1], start, end)
    return rows


def _stamp(ev: dict, start: str, end: str | None) -> None:
    ev["date"] = start
    ev["end"] = end


def collect_ipo() -> list[dict]:
    events: list[dict] = []
    for label, view in _38_VIEWS:
        try:
            for row in _fetch_38(view):
                events.append({**row, "type": label})
        except requests.RequestException as exc:
            logger.warning("38커뮤니케이션 %s 수집 실패: %s", label, exc)
    return events


def collect_rights(months_back: int = 0) -> list[dict]:
    """DART 유상증자 결정 공시. DART_API_KEY 없으면 빈 리스트."""
    key = get_settings().dart_api_key
    if not key:
        return []
    today = datetime.now(KST).date()
    bgn = today.replace(day=1).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    out: list[dict] = []
    try:
        for page in (1, 2):
            resp = requests.get(
                "https://opendart.fss.or.kr/api/list.json",
                params={"crtfc_key": key, "bgn_de": bgn, "end_de": end,
                        "pblntf_ty": "B", "page_no": page, "page_count": 100},
                timeout=15,
            )
            data = resp.json()
            if data.get("status") != "000":
                break
            for it in data.get("list", []):
                nm = it.get("report_nm", "")
                if "유상증자결정" not in nm or it.get("corp_cls") not in ("Y", "K"):
                    continue
                name = it.get("corp_name", "")
                if any(e["company"] == name for e in out):
                    continue
                dt = it.get("rcept_dt", "")
                out.append({
                    "company": name,
                    "type": "유상증자",
                    "date": f"{dt[:4]}-{dt[4:6]}-{dt[6:]}" if len(dt) == 8 else "",
                    "end": None,
                    "detail": "유상증자 결정" + (" (정정)" if "정정" in nm else ""),
                    "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={it.get('rcept_no')}",
                })
            if len(data.get("list", [])) < 100:
                break
    except (requests.RequestException, ValueError) as exc:
        logger.warning("DART 유상증자 공시 수집 실패: %s", exc)
    return out[:15]
