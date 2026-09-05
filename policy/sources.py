"""4개 금융당국 보도자료 목록 스크래퍼.

모두 서버 렌더링 HTML(또는 HTML 조각)이라 requests + BeautifulSoup 로 충분하다.
각 기관 파서는 독립적으로 try/except 처리되어 한 곳이 실패해도 나머지는 표시된다.

정규화 항목:
  {org, org_name, badge, title, url, dept, date("YYYY-MM-DD")}
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
_TIMEOUT = 15
_TOP_N = 3        # 화면 표시(기관당)
_FETCH_N = 10     # 기준일 총 건수 집계를 위해 넉넉히 수집

AUTHORITY_ORGS = [
    {"org": "FSC", "org_name": "금융위원회", "badge": "금융위"},
    {"org": "FSS", "org_name": "금융감독원", "badge": "금감원"},
    {"org": "BOK", "org_name": "한국은행", "badge": "한국은행"},
    {"org": "MOEF", "org_name": "기획재정부", "badge": "기재부"},
]
AFFILIATE_ORGS = [
    # 공식 게시판 스크랩(실데이터)이 먼저, 링크 카드로 대체하는 곳은 아래로
    {"org": "KDIC", "org_name": "예금보험공사", "badge": "예보"},
    {"org": "KOFIA", "org_name": "금융투자협회", "badge": "금투협"},
    {"org": "KRX", "org_name": "한국거래소", "badge": "거래소"},
    {"org": "KSD", "org_name": "한국예탁결제원", "badge": "예탁원"},
]
ORGS = AUTHORITY_ORGS  # 하위호환
_META = {o["org"]: o for o in AUTHORITY_ORGS + AFFILIATE_ORGS}


def _get(url: str, **kw) -> requests.Response:
    resp = requests.get(url, headers={"User-Agent": _UA}, timeout=_TIMEOUT, **kw)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp


def _norm_date(text: str) -> str:
    text = (text or "").strip()
    m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", text)
    if not m:
        return ""
    y, mo, d = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def _item(org: str, title: str, url: str, dept: str, date: str) -> dict:
    meta = _META[org]
    return {
        "org": org,
        "org_name": meta["org_name"],
        "badge": meta["badge"],
        "title": re.sub(r"\s+", " ", (title or "").strip()),
        "url": url,
        "dept": (dept or "").strip() or None,
        "date": date or "",
    }


# ── 금융위원회 ────────────────────────────────────────────────────
def fetch_fsc() -> list[dict]:
    soup = BeautifulSoup(_get("https://www.fsc.go.kr/no010101").text, "html.parser")
    out: list[dict] = []
    for li in soup.select(".board-list-wrap li"):
        a = li.select_one(".subject a")
        if not a:
            continue
        title = a.get("title") or a.get_text(strip=True)
        href = urljoin("https://www.fsc.go.kr", (a.get("href") or "").split("?")[0])
        dept = ""
        for span in li.select(".info span"):
            t = span.get_text(strip=True)
            if "담당부서" in t:
                dept = t.split(":", 1)[-1].strip()
        date = _norm_date(li.select_one(".day").get_text() if li.select_one(".day") else "")
        out.append(_item("FSC", title, href, dept, date))
        if len(out) >= _FETCH_N:
            break
    return out


# ── 금융감독원 ────────────────────────────────────────────────────
def fetch_fss() -> list[dict]:
    url = "https://www.fss.or.kr/fss/bbs/B0000188/list.do?menuNo=200218"
    soup = BeautifulSoup(_get(url).text, "html.parser")
    out: list[dict] = []
    for tr in soup.select("table tbody tr"):
        a = tr.select_one("td.title a")
        if not a:
            continue
        tds = tr.find_all("td")
        dept = tds[2].get_text(strip=True) if len(tds) > 2 else ""
        date = _norm_date(tds[3].get_text() if len(tds) > 3 else "")
        href = urljoin("https://www.fss.or.kr", a.get("href") or "")
        out.append(_item("FSS", a.get_text(strip=True), href, dept, date))
        if len(out) >= _FETCH_N:
            break
    return out


# ── 한국은행 ──────────────────────────────────────────────────────
def fetch_bok() -> list[dict]:
    url = ("https://www.bok.or.kr/portal/singl/newsData/listCont.do"
           "?menuNo=201263&pageIndex=1&pageUnit=10&targetDepth=3"
           "&depth2=200038&depth3=201263&sort=1")
    soup = BeautifulSoup(_get(url).text, "html.parser")
    box = soup.select_one("div.bd-line") or soup
    out: list[dict] = []
    for li in box.select("ul > li"):
        a = li.find("a")
        if not a or not a.get("href"):
            continue
        text = li.get_text(" ", strip=True)
        dept_m = re.search(r"담당부서\s*([^\s]+)", text)
        date = _norm_date(re.search(r"등록일\s*([\d.]+)", text).group(1)
                          if re.search(r"등록일\s*([\d.]+)", text) else "")
        href = urljoin("https://www.bok.or.kr", a.get("href"))
        out.append(_item("BOK", a.get_text(strip=True), href,
                         dept_m.group(1) if dept_m else "", date))
        if len(out) >= _FETCH_N:
            break
    return out


# ── 기획재정부 ────────────────────────────────────────────────────
def fetch_moef() -> list[dict]:
    url = "https://www.moef.go.kr/nw/nes/nesdta.do?bbsId=MOSFBBS_000000000028&menuNo=4010100"
    soup = BeautifulSoup(_get(url).text, "html.parser")
    out: list[dict] = []
    for li in soup.select("ul.boardType3 li"):
        a = li.find("a")
        if not a:
            continue
        m = re.search(r"fn_egov_select\('([^']+)'\)", a.get("href") or "")
        if not m:
            continue
        ntt = m.group(1)
        href = ("https://www.moef.go.kr/nw/nes/detailNesDtaView.do"
                f"?menuNo=4010100&searchBbsId1=MOSFBBS_000000000028&searchNttId1={ntt}")
        text = li.get_text(" ", strip=True)
        date = _norm_date(text)
        dept = ""
        dm = re.search(r"\d{4}\.\d{2}\.\d{2}\.\s*([^\s]+)", text)
        if dm:
            dept = dm.group(1)
        out.append(_item("MOEF", a.get_text(strip=True), href, dept, date))
        if len(out) >= _FETCH_N:
            break
    return out


# ── 유관기관 ──────────────────────────────────────────────────────
def fetch_kdic() -> list[dict]:
    url = "https://www.kdic.or.kr/di/medi/selectPbcrBbsList.do?cdVl=bodo"
    soup = BeautifulSoup(_get(url).text, "html.parser")
    out: list[dict] = []
    for tr in soup.select("table tbody tr"):
        a = tr.select_one("a[onclick]")
        if not a:
            continue
        m = re.search(r"detailView\('(\d+)'\s*,\s*'(\w+)'\)", a.get("onclick") or "")
        tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(tds) < 4 or not m:
            continue
        href = ("https://www.kdic.or.kr/di/medi/selectPbcrBbsDtl.do"
                f"?pstNo={m.group(1)}&bbsSeCd={m.group(2)}&cdVl=bodo")
        dept = tds[2].replace("소관부서", "").strip()
        date = _norm_date(tds[3])
        out.append(_item("KDIC", tds[1], href, dept, date))
        if len(out) >= _FETCH_N:
            break
    return out


def fetch_kofia() -> list[dict]:
    # 금융투자협회 알림마당(공지·보도). 입찰공고는 제외.
    url = "https://www.kofia.or.kr/brd/m_17/list.do"
    soup = BeautifulSoup(_get(url).text, "html.parser")
    out: list[dict] = []
    for tr in soup.select("table tbody tr"):
        a = tr.select_one("a[href*='view.do']")
        if not a:
            continue
        tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        title = a.get_text(strip=True) or (tds[1] if len(tds) > 1 else "")
        if not title or title.startswith("[입찰공고]"):
            continue
        date = next((_norm_date(t) for t in tds if _norm_date(t)), "")
        href = urljoin("https://www.kofia.or.kr/brd/m_17/", (a.get("href") or "").lstrip("./"))
        out.append(_item("KOFIA", title, href, "", date))
        if len(out) >= _FETCH_N:
            break
    return out


# 한국거래소·예탁결제원은 보도자료 페이지가 동적(WebSquare/React)이라 목록을 직접
# 불러올 수 없다. 뉴스로 대체하지 않고, 공식 보도자료 페이지로 바로 연결하는 카드만 둔다.
_LINK_ONLY = {
    "KRX": "https://open.krx.co.kr/contents/OPN/05/05000000/OPN05000000.jsp",
    "KSD": "https://www.ksd.or.kr/ko/about-ksd/ksd-news/press-release",
}


def _link_only(org: str) -> list[dict]:
    it = _item(org, "공식 보도자료 페이지에서 최신 자료를 확인하세요", _LINK_ONLY[org], "바로가기", "")
    it["link_only"] = True
    return [it]


def fetch_krx() -> list[dict]:
    return _link_only("KRX")


def fetch_ksd() -> list[dict]:
    return _link_only("KSD")


_AUTHORITY_FETCHERS = {"FSC": fetch_fsc, "FSS": fetch_fss, "BOK": fetch_bok, "MOEF": fetch_moef}
_AFFILIATE_FETCHERS = {"KRX": fetch_krx, "KDIC": fetch_kdic, "KSD": fetch_ksd, "KOFIA": fetch_kofia}


def _run(fetchers: dict) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    failed: list[str] = []
    for org, fn in fetchers.items():
        try:
            got = fn()
            if got:
                items.extend(got)
            else:
                failed.append(org)
                logger.warning("정책 스크랩 결과 없음: %s", org)
        except Exception as exc:  # noqa: BLE001
            failed.append(org)
            logger.warning("정책 스크랩 실패 %s: %s", org, exc)
    return items, failed


def fetch_all() -> tuple[list[dict], list[str]]:
    """금융당국 4곳."""
    return _run(_AUTHORITY_FETCHERS)


def fetch_affiliates() -> tuple[list[dict], list[str]]:
    """유관기관 4곳."""
    return _run(_AFFILIATE_FETCHERS)


def group_by_org(items: list[dict], per_org: int = _TOP_N,
                 order: list[dict] | None = None) -> list[dict]:
    """기관 순서 유지하며 그룹핑. 기관당 최신 per_org건만."""
    groups = []
    for meta in (order or AUTHORITY_ORGS):
        rows = sorted(
            (it for it in items if it["org"] == meta["org"]),
            key=lambda it: it["date"] or "", reverse=True,
        )
        if rows:
            groups.append({**meta, "items": rows[:per_org]})
    return groups


def reference_date(items: list[dict]) -> str:
    """조회 기준일 = 4개 기관 보도자료 중 가장 최근 날짜.

    주말·공휴일엔 해당 기관들이 자료를 내지 않으므로, 최신 날짜가 곧
    '직전 영업일'이 된다(별도 공휴일 달력 불필요).
    """
    dates = [it["date"] for it in items if it["date"]]
    return max(dates) if dates else ""


def count_on(items: list[dict], date: str) -> int:
    return sum(1 for it in items if it["date"] == date) if date else 0
