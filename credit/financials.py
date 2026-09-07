"""여신·심사 > 기업분석 > 재무요약 · 실적분석.

금융감독원 DART 「단일회사 주요계정」 fnlttSinglAcnt.json
  - 연간 : bsns_year=Y, reprt_code=11011(사업보고서)
           → thstrm/frmtrm/bfefrmtrm 로 최근 3개년 한 번에.
  - 분기 : reprt_code 11013(1Q)·11012(반기)·11014(3Q)·11011(사업) 을 조합.
           손익(매출·영업이익·순이익)은 '누적' 값이라 직전 분기 누적을 빼서 단일 분기로 환산.
           재무상태(자산·부채·자본)는 분기말 잔액이라 그대로 사용.

연결(CFS) 우선, 없으면 별도(OFS). 계정 명칭은 회사마다 조금씩 달라 동의어 집합으로 매칭.
DART_API_KEY 가 없거나 실패하면 sample_data 로 폴백한다(source="sample").
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import requests

from capital._cache import ttl_cache
from main.config import get_settings

from . import sample_data, store
from .corp_map import corp_code

logger = logging.getLogger(__name__)

_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"
_RCODE = {1: "11013", 2: "11012", 3: "11014", 4: "11011"}
_FLOW = ("revenue", "operating_income", "net_income")   # 손익(누적) 항목
_STOCK = ("assets", "liabilities", "equity")            # 재무상태(잔액) 항목

# (계정 동의어, 결과 필드)
_ACCOUNTS: tuple[tuple[set[str], str], ...] = (
    ({"매출액", "수익(매출액)", "영업수익"}, "revenue"),
    ({"영업이익", "영업이익(손실)"}, "operating_income"),
    ({"당기순이익", "당기순이익(손실)", "당기순이익(당기순손실)"}, "net_income"),
    ({"자산총계"}, "assets"),
    ({"부채총계"}, "liabilities"),
    ({"자본총계"}, "equity"),
)


def _amt(v) -> int | None:
    try:
        return int(str(v).replace(",", "").strip())
    except (TypeError, ValueError, AttributeError):
        return None


def _ratio(a: list, b: list, scale: float = 100.0, nd: int = 1) -> list:
    return [round(x / y * scale, nd) if x is not None and y else None for x, y in zip(a, b)]


def _parse(data: dict, amount_cols: list[str]) -> dict:
    """DART 응답 list 에서 {필드: {amount_col: 금액}} 추출. 연결(CFS) 우선."""
    picked: dict[str, dict] = {}
    for want_fs in ("CFS", "OFS"):
        for it in data.get("list", []):
            if it.get("fs_div") != want_fs:
                continue
            nm = it.get("account_nm")
            for names, field in _ACCOUNTS:
                if nm in names and field not in picked:
                    picked[field] = {c: _amt(it.get(c)) for c in amount_cols}
        if "revenue" in picked and "assets" in picked:
            break
    return picked


def _fetch(cc: str, key: str, year: int, rcode: str) -> dict | None:
    try:
        resp = requests.get(_URL, params={
            "crtfc_key": key, "corp_code": cc,
            "bsns_year": str(year), "reprt_code": rcode,
        }, timeout=12)
        data = resp.json()
    except (requests.RequestException, ValueError):
        return None
    if data.get("status") != "000":
        return None
    return data


def _block(labels, rev, opi, ni, assets, liab, eq) -> dict:
    return {
        "labels": labels,
        "revenue": rev, "operating_income": opi, "net_income": ni,
        "assets": assets, "liabilities": liab, "equity": eq,
        "debt_ratio": _ratio(liab, eq),      # 부채총계 / 자본총계 × 100
        "op_margin": _ratio(opi, rev),       # 영업이익률
        "net_margin": _ratio(ni, rev),       # 순이익률
        "roe": _ratio(ni, eq),               # 당기순이익 / 자본총계 × 100
    }


def _q_single(data: dict | None) -> dict | None:
    """1~3분기·반기 보고서 파싱: thstrm_amount 가 이미 '당기 3개월', BS 는 분기말 잔액.

    (DART fnlttSinglAcnt: 분기·반기 보고서의 손익 thstrm_amount = 3개월,
     thstrm_add_amount = 당기 누적. 사업보고서엔 add 가 없음.)
    """
    if not data:
        return None
    p = _parse(data, ["thstrm_amount", "thstrm_add_amount"])
    if not p:
        return None
    return {f: v.get("thstrm_amount") for f, v in p.items()}


def _q4_from(ann: dict | None, q3: dict | None) -> dict | None:
    """4분기 = 사업보고서(연간) − 3분기 누적. BS 는 연말 잔액 그대로."""
    if not ann:
        return None
    pa = _parse(ann, ["thstrm_amount"])
    p3 = _parse(q3, ["thstrm_add_amount"]) if q3 else {}
    row: dict = {}
    for f in _STOCK:
        row[f] = (pa.get(f) or {}).get("thstrm_amount")
    for f in _FLOW:
        yr = (pa.get(f) or {}).get("thstrm_amount")
        c9 = (p3.get(f) or {}).get("thstrm_add_amount")
        row[f] = yr - c9 if (yr is not None and c9 is not None) else None
    return row


def _quarterly(cc: str, key: str, n: int = 4) -> list[dict]:
    """최근 n개 분기(단일 분기 기준) 재무. 필요한 DART 보고서를 병렬로 받아 조립."""
    today = date.today()
    y, q = today.year, (today.month - 1) // 3 + 1
    q -= 1                                    # 진행 중 분기는 아직 미보고
    if q == 0:
        y, q = y - 1, 4

    # 후보 분기(최신→과거, 미제출 대비 여유분)
    cand: list[tuple[int, int]] = []
    yy, qq = y, q
    for _ in range(n + 3):
        cand.append((yy, qq))
        qq -= 1
        if qq == 0:
            yy, qq = yy - 1, 4

    # 필요한 (연도, reprt_code) 집합 → 병렬 fetch
    need: set[tuple[int, str]] = set()
    for (yy, qq) in cand:
        if qq == 4:
            need.add((yy, "11011"))
            need.add((yy, "11014"))
        else:
            need.add((yy, _RCODE[qq]))

    with ThreadPoolExecutor(max_workers=6) as ex:
        raw = dict(ex.map(lambda it: (it, _fetch(cc, key, it[0], it[1])), need))

    out: list[dict] = []
    for (yy, qq) in cand:
        if len(out) >= n:
            break
        if qq == 4:
            row = _q4_from(raw.get((yy, "11011")), raw.get((yy, "11014")))
        else:
            row = _q_single(raw.get((yy, _RCODE[qq])))
        if row and any(row.get(f) is not None for f in _FLOW + _STOCK):
            out.append({"label": f"{yy} {qq}Q", **{f: row.get(f) for f in _FLOW + _STOCK}})
    out.reverse()
    return out


@ttl_cache(60 * 60 * 6)
def annual_revenue(code: str) -> int | None:
    """기초정보 PSR 계산용 — 최근 연간 매출액만 1콜로. (분기 조회 없이 가볍게)"""
    key = get_settings().dart_api_key
    cc = corp_code(code) if key else None
    if not cc:
        return None
    data = _fetch(cc, key, date.today().year - 1, "11011")
    if not data:
        return None
    return (_parse(data, ["thstrm_amount"]).get("revenue") or {}).get("thstrm_amount")


@ttl_cache(60 * 60 * 6)
def get_financials(code: str) -> dict:
    cached = store.get_cached(code, "financials")
    if cached is not None:
        return cached

    key = get_settings().dart_api_key
    cc = corp_code(code) if key else None
    if not cc:
        return sample_data.financials(code)

    year = date.today().year - 1
    data = _fetch(cc, key, year, "11011")
    if not data:
        logger.info("DART 연간 재무 조회 실패(%s)", code)
        return sample_data.financials(code)

    ycols = ["bfefrmtrm_amount", "frmtrm_amount", "thstrm_amount"]
    ylabels = [str(year - 2), str(year - 1), str(year)]
    ypick = _parse(data, ycols)
    yser = lambda f: [(ypick.get(f) or {}).get(c) for c in ycols]

    rev, opi, ni = yser("revenue"), yser("operating_income"), yser("net_income")
    assets, liab, eq = yser("assets"), yser("liabilities"), yser("equity")
    if not any(rev) and not any(assets):
        return sample_data.financials(code)

    annual = _block(ylabels, rev, opi, ni, assets, liab, eq)

    quarters = None
    try:
        qrows = _quarterly(cc, key, 4)
    except (requests.RequestException, ValueError) as exc:
        logger.info("DART 분기 재무 실패(%s): %s", code, exc)
        qrows = []
    if qrows:
        col = lambda f: [r.get(f) for r in qrows]
        quarters = _block([r["label"] for r in qrows], col("revenue"), col("operating_income"),
                          col("net_income"), col("assets"), col("liabilities"), col("equity"))

    result = {
        "code": code,
        "unit": "원",
        "fiscal_year": str(year),
        **annual,                 # 실적분석 차트가 top-level revenue/labels 등을 사용
        "annual": annual,
        "quarters": quarters,
        "source": "live",
    }
    store.save_cached(code, "financials", result)
    return result
