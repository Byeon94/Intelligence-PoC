"""자본시장 > 발행시장 일정 수집.

- IPO 수요예측 / 공모청약 / 신규상장 : 38커뮤니케이션(38.co.kr) 스크랩 (EUC-KR)
- 유상증자 결정 공시 : 금융감독원 DART OpenAPI (DART_API_KEY 있을 때만)

정규화 이벤트: {date, end, type, company, detail, url}
  type ∈ {"수요예측", "청약", "상장", "유상증자"}

수집 함수는 (이벤트, 실패한 소스 이름 목록)을 돌려준다 — 호출부(calendar.py)가 일부 소스
실패를 "오늘 일정 없음"과 구분해 나중에 다시 수집할 수 있게 하기 위함.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from main.config import get_settings
from main.utils import today_kst, ymd_to_iso

logger = logging.getLogger(__name__)
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36"

_38_URL = "http://www.38.co.kr/html/fund/index.htm?o={view}"
_38_VIEWS = [
    ("수요예측", "r"),
    ("청약", "k"),
    ("상장", "nw"),  # 시기에 따라 항목이 없을 수 있음(그래도 시도)
]

_DATE_RE = re.compile(r"(\d{4})\.(\d{2})\.(\d{2})(?:\s*~\s*(\d{2})\.(\d{2}))?")


def _first_dates(text: str) -> tuple[str, str | None]:
    """'2026.09.22~09.23' → ('2026-09-22', '2026-09-23'). 날짜가 없으면 ('', None)."""
    m = _DATE_RE.search(text or "")
    if not m:
        return "", None
    y, mo, d = m.group(1), m.group(2), m.group(3)
    start = f"{y}-{mo}-{d}"
    end = f"{y}-{m.group(4)}-{m.group(5)}" if m.group(4) else None
    return start, end


def _find_table(soup: BeautifulSoup):
    """일정 표 = 헤더에 '종목명'·날짜·주간사/공모가가 함께 있는 첫 table."""
    for t in soup.find_all("table"):
        h = t.get_text(" ", strip=True)
        if "종목명" in h and _DATE_RE.search(h) and ("주간사" in h or "주관사" in h or "공모가" in h):
            return t
    return None


def _parse_row(tr, base_url: str) -> dict | None:
    """표의 한 행 → {company, url, detail, date, end}. 종목 행이 아니면 None."""
    tds = tr.find_all("td")
    if len(tds) < 4:
        return None
    a = tr.find("a", href=re.compile(r"o=v"))
    cells = [re.sub(r"\s+", " ", td.get_text(" ", strip=True)) for td in tds]
    name = cells[0].strip()
    if not a or not name or name.startswith("종목") or "공모뉴스" in cells[0]:
        return None
    start, end = _first_dates(cells[1])
    if not start:
        # 보기(view)마다 칼럼 순서가 달라 날짜가 뒤 칼럼에 있을 수 있음
        for c in cells[2:4]:
            start, end = _first_dates(c)
            if start:
                break
    if not start:
        return None
    hope = next((c for c in cells if "~" in c and "," in c), "")
    lead = cells[-1] if cells[-1] and cells[-1] != "-" else cells[-2]
    detail = " · ".join(x for x in [f"희망 {hope}원" if hope else "", lead] if x)
    return {
        "company": name,
        # href 는 "/html/fund/?o=v&no=…" 같은 루트 기준 경로 — 페이지 URL 기준으로 풀어야
        # 경로가 중복되지 않는다.
        "url": urljoin(base_url, a["href"]),
        "detail": detail,
        "date": start,
        "end": end,
    }


def _fetch_38(view: str) -> list[dict]:
    r = requests.get(_38_URL.format(view=view), headers={"User-Agent": _UA}, timeout=15)
    r.raise_for_status()
    r.encoding = "euc-kr"
    table = _find_table(BeautifulSoup(r.text, "html.parser"))
    if table is None:
        return []
    rows = (_parse_row(tr, r.url) for tr in table.find_all("tr"))
    return [row for row in rows if row]


def collect_ipo() -> tuple[list[dict], list[str]]:
    """38커뮤니케이션 3개 보기. 네트워크 실패한 보기는 두 번째 값에 '38:수요예측' 식으로 담는다."""
    events: list[dict] = []
    failed: list[str] = []
    for label, view in _38_VIEWS:
        try:
            for row in _fetch_38(view):
                events.append({**row, "type": label})
        except requests.RequestException as exc:
            logger.warning("38커뮤니케이션 %s 수집 실패: %s", label, exc)
            failed.append(f"38:{label}")
    return events, failed


def collect_rights() -> tuple[list[dict], list[str]]:
    """이번 달(KST) DART 유상증자 결정 공시(최대 15건). DART_API_KEY 없으면 ([], [])."""
    key = get_settings().dart_api_key
    if not key:
        return [], []
    today = today_kst()
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
            status = data.get("status")
            if status == "013":   # 조회된 데이터 없음 — 실패 아님
                break
            if status != "000":   # 키 오류·요청 제한 등
                raise ValueError(f"DART status {status}: {data.get('message')}")
            for it in data.get("list", []):
                nm = it.get("report_nm", "")
                if "유상증자결정" not in nm or it.get("corp_cls") not in ("Y", "K"):
                    continue
                name = it.get("corp_name", "")
                if any(e["company"] == name for e in out):
                    continue
                dt = ymd_to_iso(it.get("rcept_dt"))
                out.append({
                    "company": name,
                    "type": "유상증자",
                    "date": dt if len(dt) == 10 else "",
                    "end": None,
                    "detail": "유상증자 결정" + (" (정정)" if "정정" in nm else ""),
                    "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={it.get('rcept_no')}",
                })
            if len(data.get("list", [])) < 100:
                break
    except (requests.RequestException, ValueError) as exc:
        logger.warning("DART 유상증자 공시 수집 실패: %s", exc)
        return out[:15], ["DART"]
    return out[:15], []
