"""증권사 공식 홈페이지의 CMA 금리 읽기 — 네이버페이 CMA 비교 대상 20개 증권사 중 17곳, 증권사별 전용 파서.

금융투자협회·금감원·공공데이터포털 어디에도 증권사별 CMA 금리를 모아 주는 공개 API 가 없어
(2026-09-27 조사), 각 증권사가 자기 CMA 안내 페이지에 게시한 금리를 직접 읽는다. 대부분은
페이지의 표를 채우는 공개 JSON 을 페이지와 같은 방식으로 호출한다(로그인·봇 차단 우회 없음).

각 fetch 함수는 {"rp_rate", "note_rate", "as_of", "url"} 을 돌려주고, 구조가 바뀌어 값을
못 찾으면 예외를 올린다(추정값을 만들지 않는다).
  - rp_rate   : RP형 CMA 개인 기본 약정수익률(세전 연 %, 가장 짧은 기본 구간)
  - note_rate : 발행어음형 CMA 개인 기본 수익률(없으면 None)
  - as_of     : 페이지에 적힌 금리 기준일(없으면 None)
  - url       : 화면에 출처로 보여줄 공식 페이지

조회가 막힌 곳은 뺐다(2026-09-27): 키움(EverSafe 봇 차단), 신영(웹 방화벽 차단),
케이프(금리 응답 암호화 — 자동 수집을 막는 장치로 보고 풀지 않음),
메리츠(국내에선 되지만 Render 해외 서버 요청을 HTTP 400 으로 거절 — 사용자 결정으로 제외).
파서는 사이트 개편 시 깨질 수 있으므로 실패하면 capital.cma_rates 가 직전 확인값(이전값)으로
대신하고, 그마저 없으면 "확인 불가"로 둔다.
"""
from __future__ import annotations

import json
import re
import ssl
from datetime import timedelta
from urllib.parse import quote
from typing import Callable

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

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
    return {"rp_rate": personal(rp_tb), "note_rate": note, "as_of": _ymd(label), "url": page, "product": "RP 투자형"}


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
    return {"rp_rate": rp, "note_rate": note, "as_of": None, "url": page, "product": "CMA RP_개인"}


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
            "as_of": _ymd(rp["alyStaDt"]), "url": page, "product": "CMA RP(1~30일)"}


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
            "as_of": _ymd(rec["ANCT_DATE"]), "url": page, "product": "CMA+ RP형"}


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
            "as_of": _ymd(data.get("cma100")), "url": page, "product": "자동투자 RP(개인)"}


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
            "as_of": _ymd(body.get("기준일자")), "url": page, "product": "명품 CMA RP(개인)"}


def fetch_yuanta() -> dict:
    """유안타증권 — 자동투자상품안내 페이지가 약정금리를 채우는 정적 파일 prodRate.tbl 의 CMA-RP 1~30일.
    페이지의 '기준'은 조회일이 찍히고 파일의 기준일(2010)은 갱신되지 않아 as_of 는 비운다."""
    page = "https://www.myasset.com/myasset/static/mall/wcma/MA_0501004_P2.jsp"
    r = requests.get("https://www.myasset.com/myasset/code/prodRate.tbl", headers={**_HDR, "Referer": page}, timeout=_TIMEOUT)
    r.raise_for_status()
    t = r.content.decode("utf-8", "replace")

    def arr(name: str) -> list[str]:
        m = re.search(name + r"\s*=\s*new Array\(([^)]*)\)", t)
        if not m:
            raise ValueError(f"유안타 {name} 없음")
        return re.findall(r"'([^']*)'", m.group(1))

    frm, rate = arr("ProdRate_CMARP_from"), arr("ProdRate_CMARP_rate")
    if not rate or frm[0] != "1":
        raise ValueError("유안타 CMA-RP 표 구조 변경")
    return {"rp_rate": float(rate[0]), "note_rate": None, "as_of": None, "url": page, "product": "W-CMA(CMA-RP)"}


def fetch_eugene() -> dict:
    """유진투자증권 — CMA 안내(서버 렌더링 HTML) 'CMA-RP수익률 (YYYY . MM . DD 기준)' 표의 자유형 CMA."""
    page = "https://www.eugenefn.com/ingo/igca/igca100r.do"
    r = requests.get(page, headers=_HDR, timeout=_TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.content.decode("utf-8", "replace"), "html.parser")
    tit = next((d for d in soup.select("div.bul_tit") if "CMA-RP수익률" in d.get_text()), None)
    if tit is None:
        raise ValueError("유진 CMA-RP수익률 제목 없음")
    m = re.search(r"(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*기준", tit.get_text())
    as_of = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None
    th = next((h for h in tit.find_next("table").find_all("th") if "자유형" in h.get_text()), None)
    if th is None:
        raise ValueError("유진 자유형 CMA 행 없음")
    cell = next((c.get_text(strip=True) for c in th.find_parent("tr").find_all("td") if "%" in c.get_text()), "")
    return {"rp_rate": _pct(cell), "note_rate": None, "as_of": as_of, "url": page, "product": "챔피언CMA(자유형)"}


def fetch_db() -> dict:
    """DB증권 — happy+ CMA 안내 페이지가 부르는 getCMAInterestRate.do. PER_INT=RP형 개인, PER_DT=기준일."""
    page = "https://www.dbsec.co.kr/product/cma/pr_CmaInfo_viw.do"
    r = requests.get("https://www.dbsec.co.kr/online/accservice/getCMAInterestRate.do",
                     headers={**_HDR, "Referer": page, "X-Requested-With": "XMLHttpRequest"}, timeout=_TIMEOUT)
    r.raise_for_status()
    d = r.json()
    return {"rp_rate": float(d["PER_INT"]), "note_rate": None, "as_of": _ymd(d.get("PER_DT")),
            "url": page, "product": "happy+ CMA RP형"}


class _LegacyTLS(HTTPAdapter):
    """ibks.com 은 OpenSSL3 기본 보안 수준(SECLEVEL=2) 핸드셰이크를 거절한다 — 이 사이트 요청에만 호환 설정."""
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


def fetch_ibk() -> dict:
    """IBK투자증권 — CMA 수익률 페이지(EUC-KR, 서버 렌더링) '수익률 (YYYY.MM.DD 기준 RP, 세전) CMA RP형 연 X%'."""
    page = "https://www.ibks.com/fundproduct/cma/cmaservice_Rate.do"
    s = requests.Session()
    s.mount("https://www.ibks.com", _LegacyTLS())
    r = s.get(page, headers=_HDR, timeout=_TIMEOUT)
    r.raise_for_status()
    text = BeautifulSoup(r.content.decode("euc-kr", "replace"), "html.parser").get_text(" ", strip=True)
    m = re.search(r"수익률\s*\((\d{4})\.(\d{1,2})\.(\d{1,2})\s*기준[^)]*\)\s*CMA\s*RP형\s*연\s*([\d.]+)\s*%", text)
    if not m:
        raise ValueError("IBK CMA RP 금리 없음")
    y, mo, dd, rate = m.groups()
    return {"rp_rate": float(rate), "note_rate": None, "as_of": f"{y}-{int(mo):02d}-{int(dd):02d}",
            "url": page, "product": "CMA RP형"}


def fetch_sk() -> dict:
    """SK증권 — Magic CMA 페이지가 부르는 MAGIC_CMA_DATA_Q.cmd 의 o_rp_int_rt. 응답의 날짜는 조회일이라 as_of 는 비운다."""
    page = "https://www.sks.co.kr/main/product/cma/mCMA/html/PD_04001_T01.htm"
    r = requests.post("https://www.sks.co.kr/main/product/rp/MAGIC_CMA_DATA_Q.cmd", data={},
                      headers={**_HDR, "Referer": page, "X-Requested-With": "XMLHttpRequest"}, timeout=_TIMEOUT)
    r.raise_for_status()
    out = json.loads(r.content.decode("utf-8", "replace"))["output"]
    if out.get("h_errcode"):
        raise ValueError("SK 응답 오류")
    return {"rp_rate": _pct(str(out.get("o_rp_int_rt", "")) + "%"), "note_rate": None, "as_of": None,
            "url": page, "product": "Magic CMA RP형"}


def fetch_daol() -> dict:
    """다올투자증권 — CMA 안내 페이지가 부르는 rPInterest.jspx(getRPInfo). 단일 금리·기준일."""
    page = "https://www.daolsecurities.com/customer/guide/cmaProduct01.jsp"
    r = requests.post("https://www.daolsecurities.com/common/include/rPInterest.jspx?cmd=getRPInfo&templet-bypass=true",
                      data={}, headers={**_HDR, "Referer": page, "X-Requested-With": "XMLHttpRequest"}, timeout=_TIMEOUT)
    r.raise_for_status()
    j = json.loads(r.text)
    return {"rp_rate": float(j["rp_rate"]), "note_rate": None, "as_of": _ymd(j.get("start_date")),
            "url": page, "product": "CMA(RP 운용)"}


def fetch_woori() -> dict:
    """우리투자증권 — 펀드슈퍼마켓 채권 > 'RP형 CMA' 탭이 부르는 selectRpInfo.do 의 CMAInfo(적용이율·기준일).
    CMA Note 는 종금형이라 발행어음형 칸에 넣지 않는다."""
    page = "https://fundsupermarket.wooriib.com/fmc/FMC3090020/main.do?tabNum=5"
    r = requests.post("https://fundsupermarket.wooriib.com/fmc/FMC3090020/selectRpInfo.do", data={},
                      headers={**_HDR, "Referer": page, "X-Requested-With": "XMLHttpRequest"}, timeout=_TIMEOUT)
    r.raise_for_status()
    cma = r.json()["CMAInfo"]
    return {"rp_rate": float(cma["APP_RATE"]), "note_rate": None, "as_of": _ymd(cma.get("START_DATE")),
            "url": page, "product": "RP형 CMA"}


def fetch_hanwha() -> dict:
    """한화투자증권 — Smart CMA '수익률 비교' 표(정적 HTML)의 RP형 가장 낮은 금액 구간(1백만원 미만).
    표에 날짜가 없어, 소개 페이지 문구 '(금액 구간별 세전, 연 a% ~ b%, YYYY.MM.DD 기준)'의 범위가 표와 같을 때만 그 날짜를 쓴다."""
    page = "https://www.hanwhawm.com/static/finance/cma/FI222_1p.htm"
    r = requests.get(page, headers=_HDR, timeout=_TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.content.decode("utf-8", "replace"), "html.parser")
    tbl = next((t for t in soup.find_all("table")
                if t.caption and "수익률" in t.caption.get_text() and "RP형" in t.get_text()), None)
    if tbl is None:
        raise ValueError("한화 수익률 표 없음")
    tiers = []
    for tr in tbl.find_all("tr"):
        tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(tds) == 2 and "%" in tds[1]:
            tiers.append((tds[0], _pct(tds[1])))
    if not tiers or "미만" not in tiers[0][0]:
        raise ValueError("한화 금액 구간 구조 변경")
    as_of = None
    r2 = requests.get("https://www.hanwhawm.com/static/finance/cma/FI200_1p.htm", headers=_HDR, timeout=_TIMEOUT)
    if r2.ok:
        txt = re.sub(r"\s+", " ", BeautifulSoup(r2.content.decode("utf-8", "replace"), "html.parser").get_text(" "))
        m = re.search(r"CMA RP형[^()]{0,40}\(\s*금액 구간별 세전,\s*연\s*([\d.]+)%\s*~\s*([\d.]+)%,\s*(\d{4})\.(\d{1,2})\.(\d{1,2})\s*기준", txt)
        rates = [t[1] for t in tiers]
        if m and float(m.group(1)) == min(rates) and float(m.group(2)) == max(rates):
            as_of = f"{m.group(3)}-{int(m.group(4)):02d}-{int(m.group(5)):02d}"
    return {"rp_rate": tiers[0][1], "note_rate": None, "as_of": as_of, "url": page,
            "product": f"Smart CMA RP형({tiers[0][0]})"}


def fetch_hmsec() -> dict:
    """현대차증권 — The H CMA 안내의 '그 외 개인/법인계좌는 RP형 CMA적용 : 연 X% (기준일자 : YYYY-MM-DD)'.
    같은 페이지의 '디지털 RP형 CMA'(앱 신규 개설 전용)는 기본 금리가 아니라 쓰지 않는다."""
    page = "https://www.hmsec.com/goMenu.do?scr_menu_id=PD0201"
    r = requests.get(page, headers=_HDR, timeout=_TIMEOUT)
    r.raise_for_status()
    txt = re.sub(r"\s+", " ", BeautifulSoup(r.content.decode("utf-8", "replace"), "html.parser").get_text(" "))
    m = re.search(r"RP형 CMA\s*적용\s*:\s*연\s*([\d.]+)\s*%\s*\(\s*기준일자\s*:\s*(\d{4}-\d{2}-\d{2})\s*\)", txt)
    if not m:
        raise ValueError("현대차 RP형 CMA 문구 없음")
    return {"rp_rate": float(m.group(1)), "note_rate": None, "as_of": m.group(2), "url": page,
            "product": "The H CMA RP형"}


def fetch_mirae_naver() -> dict:
    """미래에셋증권 CMA-RP 네이버통장 — 정적 상품 페이지에 없고 공지 'RP 상품별 약정수익률 변경 안내'에만 있다.
    공지 게시판을 '네이버통장'으로 검색(최근 1년, 사이트 기본 검색)해 최신 공지 표의 '1,000만원 이하' 변경 후 금리를 읽고,
    초과 구간은 상품명에 함께 적는다. as_of 는 공지의 적용일."""
    base = "https://securities.miraeasset.com/bbs/board/message/"
    today = today_kst()
    start = today - timedelta(days=364)
    q = (f"categoryId=66&searchType=19&searchText={quote('네이버통장'.encode('euc-kr'))}"
         f"&searchStartYear={start.year}&searchStartMonth={start.month:02d}&searchStartDay={start.day:02d}"
         f"&searchEndYear={today.year}&searchEndMonth={today.month:02d}&searchEndDay={today.day:02d}"
         "&curPage=1&startId=zzzzz~&startPage=1&listType=1")
    r = requests.get(base + "list.do?" + q, headers=_HDR, timeout=_TIMEOUT)
    r.raise_for_status()
    ids = re.findall(r"javascript:view\('(\d+)'", r.content.decode("cp949", "replace"))
    for mid in ids[:5]:
        url = f"{base}view.do?categoryId=66&messageId={mid}"
        v = requests.get(url, headers=_HDR, timeout=_TIMEOUT)
        v.raise_for_status()
        soup = BeautifulSoup(v.content.decode("cp949", "replace"), "html.parser")
        rows = [[c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])] for tr in soup.find_all("tr")]
        for i, row in enumerate(rows):
            if len(row) >= 4 and re.sub(r"\s", "", row[0]).endswith("네이버통장") and "이하" in row[1]:
                pcts = [c for c in row if re.fullmatch(r"\d+\.\d+%", c)]
                if len(pcts) < 2:
                    continue
                low = _pct(pcts[1])   # 변경 후
                nxt = rows[i + 1] if i + 1 < len(rows) else []
                npc = [c for c in nxt if re.fullmatch(r"\d+\.\d+%", c)]
                txt = re.sub(r"\s+", " ", soup.get_text(" "))
                m = (re.search(r"네이버\s*통장\s*:\s*약정수익률\s*(\d{4})\.(\d{2})\.(\d{2})부터 적용", txt)
                     or re.search(r"시행일\s*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", txt))
                as_of = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None
                label = row[1].replace(" ", "")
                over = f", 초과 {_pct(npc[1]):.2f}%" if len(npc) >= 2 else ""
                return {"rp_rate": low, "note_rate": None, "as_of": as_of, "url": url,
                        "product": f"CMA-RP 네이버통장({label}{over})"}
    raise ValueError("미래에셋 네이버통장 금리 공지 없음(최근 1년)")


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
    return {"rp_rate": _personal_rate(rp_table), "note_rate": note, "as_of": None, "url": page, "product": "하나CMA RP형(개인)"}


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
    return {"rp_rate": _pct(rates[types.index("CMA - RP")]), "note_rate": note, "as_of": None, "url": page, "product": "CMA - RP"}


# (증권사명, 파서 또는 None, 파서가 없을 때 보여줄 공식 페이지) — 네이버페이 CMA 비교 20개사 중 신영·케이프·메리츠 제외 17곳
FIRMS: list[tuple[str, Callable[[], dict] | None, str | None]] = [
    ("미래에셋증권", fetch_mirae, None),
    ("미래에셋증권", fetch_mirae_naver, None),   # 네이버 제휴 상품(네이버페이에 보이는 금리)
    ("한국투자증권", fetch_kis, None),
    ("NH투자증권", fetch_nh, None),
    ("삼성증권", fetch_samsung, None),
    ("KB증권", fetch_kb, None),
    ("신한투자증권", fetch_shinhan, None),
    ("하나증권", fetch_hana, None),
    ("대신증권", fetch_daishin, None),
    ("유안타증권", fetch_yuanta, None),
    ("유진투자증권", fetch_eugene, None),
    ("DB증권", fetch_db, None),
    ("IBK투자증권", fetch_ibk, None),
    ("SK증권", fetch_sk, None),
    ("다올투자증권", fetch_daol, None),
    ("우리투자증권", fetch_woori, None),
    ("한화투자증권", fetch_hanwha, None),
    ("현대차증권", fetch_hmsec, None),
]


def fetch_firm(fn: Callable[[], dict]) -> dict:
    """파서 실행 + 값 검증(0~20% 범위). 실패는 예외 그대로."""
    out = fn()
    return {"rp_rate": _plausible(out["rp_rate"]), "note_rate": _plausible(out.get("note_rate")),
            "as_of": out.get("as_of"), "url": out["url"], "product": out.get("product")}
