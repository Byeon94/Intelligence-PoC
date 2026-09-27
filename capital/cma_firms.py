"""증권사 공식 홈페이지의 CMA 금리 읽기 — 상위 9개사(키움 제외), 증권사별 전용 파서.

금융투자협회·금감원·공공데이터포털 어디에도 증권사별 CMA 금리를 모아 주는 공개 API 가 없어
(2026-09-27 조사), 각 증권사가 자기 CMA 안내 페이지에 게시한 금리를 직접 읽는다. 대부분은
페이지의 표를 채우는 공개 JSON 을 페이지와 같은 방식으로 호출한다(로그인·봇 차단 우회 없음).

각 fetch 함수는 {"rp_rate", "note_rate", "as_of", "url"} 을 돌려주고, 구조가 바뀌어 값을
못 찾으면 예외를 올린다(추정값을 만들지 않는다).
  - rp_rate   : RP형 CMA 개인 기본 약정수익률(세전 연 %, 가장 짧은 기본 구간)
  - note_rate : 발행어음형 CMA 개인 기본 수익률(없으면 None)
  - as_of     : 페이지에 적힌 금리 기준일(없으면 None)
  - url       : 화면에 출처로 보여줄 공식 페이지

키움증권은 금리 조회가 봇 차단(EverSafe)으로 막혀 있어 대상에서 뺐다(사용자 결정, 2026-09-27).
파서는 사이트 개편 시 깨질 수 있으므로 실패하면 capital.cma_rates 가 직전 확인값(이전값)으로
대신하고, 그마저 없으면 "확인 불가"로 둔다.
"""
from __future__ import annotations

import json
import re
from typing import Callable

import requests
from bs4 import BeautifulSoup

from main.utils import today_kst

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
_HDR = {"User-Agent": _UA, "Accept-Language": "ko-KR,ko;q=0.9"}
_TIMEOUT = 15


def _ymd(s: str | None) -> str | None:
    """'20260831' · '2026/08/31' · '2026.08.31' → '2026-08-31'."""
    m = re.search(r"(\d{4})[/.\-]?(\d{2})[/.\-]?(\d{2})", str(s or ""))
    return f"{m[1]}-{m[2]}-{m[3]}" if m else None


def _pct(text: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", str(text or ""))
    if not m:
        raise ValueError(f"금리 없음: {text!r}")
    return float(m.group(1))


def _plausible(rate: float | None) -> float | None:
    if rate is not None and not 0 < rate < 20:
        raise ValueError(f"비정상 금리 {rate}")
    return None if rate is None else round(rate, 2)


# ── 증권사별 파서 ─────────────────────────────────────────────────────────
def fetch_kis() -> dict:
    """한국투자증권 — CMA 안내(서버 렌더링 HTML). 'RP 투자형' 표 개인 1일~30일, '발행어음 투자형' 표 개인 1일."""
    page = "https://securities.koreainvestment.com/main/mall/opencma/CmaInfo.jsp?cmd=TF02bb010000"
    r = requests.get(page, headers=_HDR, timeout=_TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.content.decode("utf-8", "replace"), "html.parser")

    def table_with(kw: str):
        for tb in soup.find_all("table"):
            cap = tb.find("caption")
            if cap and kw in cap.get_text():
                return tb
        raise ValueError(f"한투 표 '{kw}' 없음")

    def personal(tb) -> float:
        for tr in tb.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if "개인" in cells and cells.index("개인") + 1 < len(cells):
                return _pct(cells[cells.index("개인") + 1])
        raise ValueError("한투 개인 금리 없음")

    rp_tb = table_with("RP 투자형")
    try:
        note = personal(table_with("발행어음 투자형"))
    except ValueError:
        note = None
    label = rp_tb.find_previous(string=re.compile("기준일"))
    return {"rp_rate": personal(rp_tb), "note_rate": note, "as_of": _ymd(label), "url": page}


def fetch_mirae() -> dict:
    """미래에셋증권 — 금융상품 > RP 페이지(EUC-KR) 'CMA' 표의 CMA RP_개인 + 발행어음 페이지가 부르는 a15.json
    (grid01 의 종류코드 01 = CMA). RP 페이지에 기준일이 없고 a15 의 날짜는 발행어음 기준일이라 as_of 는 비운다."""
    base = "https://securities.miraeasset.com"
    page, note_page = base + "/hks/hks4033/n01.do", base + "/hks/hks3001/r02.do"
    r = requests.get(page, headers=_HDR, timeout=_TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.content.decode("cp949", "replace"), "html.parser")
    rp = None
    for tb in soup.find_all("table"):
        cap = tb.find("caption")
        if cap and cap.get_text(strip=True) == "CMA":
            for tr in tb.find_all("tr"):
                cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
                if any(c.startswith("CMA RP_개인") for c in cells):
                    rp = _pct(cells[-1])
            break
    if rp is None:
        raise ValueError("미래에셋 CMA RP_개인 없음")
    note = None
    try:
        j = requests.post(base + "/hks/hks3000/a15.json", timeout=_TIMEOUT,
                          headers={**_HDR, "X-Requested-With": "XMLHttpRequest", "Referer": note_page}).json()
        if j.get("returnCode") == "0":
            note = next((float(x["ctrt_irt"]) for x in j.get("grid01", []) if x.get("isu_bill_itm_tcd") == "01"), None)
    except (requests.RequestException, ValueError, KeyError):
        note = None   # 발행어음 금리만 못 읽어도 RP 금리는 보여준다
    return {"rp_rate": rp, "note_rate": note, "as_of": None, "url": page}


def fetch_nh() -> dict:
    """NH투자증권 — 모바일 CMA 페이지가 부르는 TR(H4063). RKRW221=CMA RP 1~30일, 등급 05(블루)=기본."""
    page = "https://m.nhsec.com/finance/cma/cma/cmaView?pdCd=CMA030"
    r = requests.post("https://m.nhsec.com/finance/cma/cma/commonTr.json", data={"trName": "H4063"},
                      headers={**_HDR, "Referer": page, "X-Requested-With": "XMLHttpRequest"}, timeout=_TIMEOUT)
    r.raise_for_status()
    blk = r.json()["H4063"]
    if blk.get("code") != "T000":
        raise ValueError(f"NH H4063 code={blk.get('code')}")
    rows = blk["H4063OutBlock1"]
    rp = next(x for x in rows if x["iemCd"] == "RKRW221" and x["cusGrdCd"] == "05")
    note = next((x for x in rows if x["iemCd"] == "NHKRCMA030"), None)
    return {"rp_rate": float(rp["sumIntRt"]), "note_rate": float(note["sumIntRt"]) if note else None,
            "as_of": _ymd(rp["alyStaDt"]), "url": page}


def fetch_samsung() -> dict:
    """삼성증권 — CMA+ 안내 페이지가 부르는 getAihr103p.do(개인 RP 약정수익률). 발행어음형 CMA 없음."""
    page = "https://www.samsungpop.com/ux/kor/finance/cma/cma/info.do"
    s = requests.Session()
    s.headers.update(_HDR)
    s.get(page, timeout=_TIMEOUT)   # 세션 쿠키
    r = s.post("https://www.samsungpop.com/ux/kor/finance/cma/cma/getAihr103p.do", data="",
               headers={"Referer": page, "X-Requested-With": "XMLHttpRequest",
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}, timeout=_TIMEOUT)
    r.raise_for_status()
    j = r.json()
    if j.get("errMsg") or j.get("errorMsg"):
        raise ValueError("삼성증권 응답 오류")
    rec = j["result"]["outRec1"]
    return {"rp_rate": float(rec["A_NDVL_RP_ANCT_YILD"]), "note_rate": None,
            "as_of": _ymd(rec["ANCT_DATE"]), "url": page}


def fetch_kb() -> dict:
    """KB증권 — CMA 수익률 안내 표를 채우는 JSON. cma111=개인 RP, cma112=개인 발행어음, cma100=기준일."""
    page = "https://www.kbsec.com/go.able?linkcd=m01030002"
    r = requests.get("https://www.kbsec.com/ndataweb/json/main/rate_manage_cma.json",
                     headers={**_HDR, "Referer": page}, timeout=_TIMEOUT)
    r.raise_for_status()
    data = None
    for enc in ("utf-8", "cp949"):
        try:
            data = json.loads(r.content.decode(enc))
            break
        except (UnicodeDecodeError, ValueError):
            continue
    if not isinstance(data, dict):
        raise ValueError("KB 응답 파싱 실패")
    return {"rp_rate": _pct(data["cma111"]), "note_rate": _pct(data["cma112"]),
            "as_of": _ymd(data.get("cma100")), "url": page}


def fetch_meritz() -> dict:
    """메리츠증권 — RP형 CMA 페이지가 부르는 RPErtSearch.go(RP10000, 1~30일). 발행어음형 CMA 탭은 비활성."""
    page = "https://home.imeritz.com/meritzcma/CmaRp.do"
    r = requests.post("https://home.imeritz.com/meritzcma/RPErtSearch.go",
                      data={"iscd": "RP10000", "aplyDate": today_kst().strftime("%Y.%m.%d")},
                      headers={**_HDR, "Referer": page, "X-Requested-With": "XMLHttpRequest"}, timeout=_TIMEOUT)
    r.raise_for_status()
    j = json.loads(r.text)
    if str(j.get("sysCode")) != "0":
        raise ValueError("메리츠 응답 오류")
    rows = [x for x in (j.get("resultList") or [[]])[0] if x.get("Iscd") == "RP10000"]
    if not rows:
        raise ValueError("메리츠 RP10000 없음")
    return {"rp_rate": float(rows[0]["AplyInrt"]), "note_rate": None,
            "as_of": _ymd(rows[0].get("InrtAplyDate")), "url": page}


def fetch_shinhan() -> dict:
    """신한투자증권 — 명품 CMA 소개 페이지가 부르는 data.do. 종목코드 2000=명품 CMA RP(개인) 1개월."""
    page = "https://www.shinhansec.com/siw/wealth-management/cma/info/view.do"
    r = requests.post("https://www.shinhansec.com/siw/wealth-management/cma/info/data.do", data="{}",
                      headers={**_HDR, "Referer": page, "X-Requested-With": "XMLHttpRequest",
                               "Accept": "application/json", "Content-Type": "application/json; charset=UTF-8"},
                      timeout=_TIMEOUT)
    r.raise_for_status()
    body = r.json()["body"]
    row = next(x for x in body["list01"] if x.get("종목코드") == "2000")
    return {"rp_rate": float(row["1개월수익율"]), "note_rate": None,
            "as_of": _ymd(body.get("기준일자")), "url": page}


def _caption_table(soup: BeautifulSoup, caption: str):
    cap = soup.find("caption", string=lambda s: s and caption in s)
    if cap is None:
        raise ValueError(f"표 '{caption}' 없음")
    return cap.find_parent("table")


def _personal_rate(table) -> float:
    """표에서 '개인' 행의 첫 금리."""
    for tr in table.select("tbody tr"):
        th = tr.find("th")
        if th and "개인" in th.get_text():
            return _pct(tr.find("td").get_text())
    raise ValueError("개인 금리 없음")


def fetch_hana() -> dict:
    """하나증권 — 하나CMA 상품안내(서버 렌더링 HTML). RP형 개인 1일~90일, 발행어음형 개인 1일. 기준일 표기 없음."""
    page = "https://www.hanaw.com/main/finance/CMA/FP_040300_P.cmd"
    r = requests.get(page, headers=_HDR, timeout=_TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.content.decode("utf-8", "replace"), "html.parser")
    rp_table = _caption_table(soup, "RP형 CMA 수익률")
    heads = [th.get_text(strip=True) for th in rp_table.select("thead th")]
    if len(heads) < 2 or "1일" not in heads[1]:
        raise ValueError("하나 RP 표 구조 변경")
    try:
        note = _personal_rate(_caption_table(soup, "발행어음형 수익률"))
    except ValueError:
        note = None
    return {"rp_rate": _personal_rate(rp_table), "note_rate": note, "as_of": None, "url": page}


def fetch_daishin() -> dict:
    """대신증권 — CMA안내(서버 렌더링 HTML) 'CMA상품 유형 안내' 표의 CMA - RP 수익률.

    페이지의 '(YYYY.MM.DD 개인고객 기준)'은 조회일이 찍히는 것으로 보여 금리 기준일로 쓰지 않는다.
    """
    page = "https://www.daishin.com/g.ds?m=1001&p=909&v=592"
    r = requests.get(page, headers=_HDR, timeout=_TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.content.decode("utf-8", "replace"), "html.parser")
    table = _caption_table(soup, "CMA상품 유형 안내")
    types = rates = None
    for tr in table.select("tbody tr"):
        label = tr.find("th").get_text(strip=True)
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if label == "상품유형":
            types = cells
        elif label == "수익률":
            rates = cells
    if not types or not rates or len(types) != len(rates) or "CMA - RP" not in types:
        raise ValueError("대신 표 구조 변경")
    note = next((_pct(rt) for t, rt in zip(types, rates) if "발행어음" in t), None)
    return {"rp_rate": _pct(rates[types.index("CMA - RP")]), "note_rate": note, "as_of": None, "url": page}


# (증권사명, 파서 또는 None, 파서가 없을 때 보여줄 공식 페이지) — 자기자본 기준 상위 10개사 중 키움증권 제외 9곳
FIRMS: list[tuple[str, Callable[[], dict] | None, str | None]] = [
    ("미래에셋증권", fetch_mirae, None),
    ("한국투자증권", fetch_kis, None),
    ("NH투자증권", fetch_nh, None),
    ("삼성증권", fetch_samsung, None),
    ("KB증권", fetch_kb, None),
    ("메리츠증권", fetch_meritz, None),
    ("신한투자증권", fetch_shinhan, None),
    ("하나증권", fetch_hana, None),
    ("대신증권", fetch_daishin, None),
]


def fetch_firm(fn: Callable[[], dict]) -> dict:
    """파서 실행 + 값 검증(0~20% 범위). 실패는 예외 그대로."""
    out = fn()
    return {"rp_rate": _plausible(out["rp_rate"]), "note_rate": _plausible(out.get("note_rate")),
            "as_of": out.get("as_of"), "url": out["url"]}
