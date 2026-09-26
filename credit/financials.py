"""여신 > 기업분석 > 재무요약 · 실적분석.

금융감독원 DART 「단일회사 주요계정」 fnlttSinglAcnt.json
  - 연간 : bsns_year=Y, reprt_code=11011(사업보고서)
           → thstrm/frmtrm/bfefrmtrm 로 최근 3개년 한 번에.
           1~3월엔 직전 연도 사업보고서가 아직 제출 전이라 DART 가 013(조회 없음)을 주므로
           그때는 한 해 전 사업보고서로 내려간다(_latest_annual).
  - 분기 : reprt_code 11013(1Q)·11012(반기)·11014(3Q)·11011(사업) 을 조합.
           1Q·반기·3Q 보고서의 손익 thstrm_amount 는 이미 '당기 3개월' 값이라 그대로 쓰고,
           4Q 만 사업보고서(연간) − 3Q 누적(thstrm_add_amount)으로 환산한다.
           재무상태(자산·부채·자본)는 분기말 잔액이라 그대로 사용.

연결(CFS) 우선, 없으면 별도(OFS). 계정 명칭은 회사마다 조금씩 달라 동의어 집합으로 매칭.
DART_API_KEY 가 없거나 실패하면 샘플 종목(sample_data.has)만 source="sample" 로 폴백하고,
그 외 종목은 source="none" + 안내(note)만 돌려준다(재무 수치를 지어내지 않음).
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

import requests

from main.cache import ttl_cache
from main.config import get_settings
from main.utils import today_kst

from . import sample_data, store
from .corp_map import corp_code

logger = logging.getLogger(__name__)

_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"
_RCODE = {1: "11013", 2: "11012", 3: "11014", 4: "11011"}
_FLOW = ("revenue", "operating_income", "net_income")   # 손익 항목
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


def ratio(a: list, b: list, scale: float = 100.0, nd: int = 1) -> list:
    return [round(x / y * scale, nd) if x is not None and y else None for x, y in zip(a, b)]


def block(labels, rev, opi, ni, assets, liab, eq) -> dict:
    """연간·분기 공통 표 블록(금액 6종 + 비율 4종). sample_data 도 같은 형태로 쓴다."""
    return {
        "labels": labels,
        "revenue": rev, "operating_income": opi, "net_income": ni,
        "assets": assets, "liabilities": liab, "equity": eq,
        "debt_ratio": ratio(liab, eq),      # 부채총계 / 자본총계 × 100
        "op_margin": ratio(opi, rev),       # 영업이익률
        "net_margin": ratio(ni, rev),       # 순이익률
        "roe": ratio(ni, eq),               # 당기순이익 / 자본총계 × 100
    }


def recent_quarters(n: int) -> list[tuple[int, int]]:
    """직전 완료 분기부터 과거로 n개 (연도, 분기) — 최신순. 진행 중 분기는 아직 미보고라 뺀다."""
    today = today_kst()
    y, q = today.year, (today.month - 1) // 3
    if q == 0:
        y, q = y - 1, 4
    out = []
    for _ in range(n):
        out.append((y, q))
        q -= 1
        if q == 0:
            y, q = y - 1, 4
    return out


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


def _request(cc: str, key: str, year: int, rcode: str) -> dict | None:
    """DART 원 응답(JSON). 통신·파싱 실패면 None."""
    try:
        resp = requests.get(_URL, params={
            "crtfc_key": key, "corp_code": cc,
            "bsns_year": str(year), "reprt_code": rcode,
        }, timeout=12)
        return resp.json()
    except (requests.RequestException, ValueError):
        return None


def _fetch(cc: str, key: str, year: int, rcode: str) -> dict | None:
    """정상(status 000) 응답만, 그 외는 None."""
    data = _request(cc, key, year, rcode)
    return data if data and data.get("status") == "000" else None


def _latest_annual(cc: str, key: str) -> tuple[int, dict] | None:
    """가장 최근 제출된 사업보고서 (사업연도, 응답).

    직전 연도 보고서가 아직 제출 전(013, 보통 1~3월)이면 한 해 전 보고서로 내려간다.
    """
    year = today_kst().year - 1
    data = _request(cc, key, year, "11011")
    if data and data.get("status") == "013":
        year -= 1
        data = _request(cc, key, year, "11011")
    if not data or data.get("status") != "000":
        return None
    return year, data


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
    cand = recent_quarters(n + 3)             # 후보 분기(최신→과거, 미제출 대비 여유분)

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
    """기초정보 PSR 계산용 — 최근 제출된 사업보고서의 연간 매출액만. (분기 조회 없이 가볍게)"""
    key = get_settings().dart_api_key
    cc = corp_code(code) if key else None
    if not cc:
        return None
    found = _latest_annual(cc, key)
    if not found:
        return None
    return (_parse(found[1], ["thstrm_amount"]).get("revenue") or {}).get("thstrm_amount")


def _fallback(code: str, note: str) -> dict:
    """실데이터를 못 만들 때 — 샘플 종목만 샘플(source="sample"), 그 외는 빈 결과 + 안내."""
    if sample_data.has(code):
        return sample_data.financials(code)
    return {"code": code, "unit": "원", "annual": None, "quarters": None,
            "source": "none", "note": note}


@ttl_cache(60 * 60 * 6)
def get_financials(code: str) -> dict:
    cached = store.get_cached(code, "financials")
    if cached is not None:
        return cached

    key = get_settings().dart_api_key
    cc = corp_code(code) if key else None
    if not cc:
        return _fallback(code, "DART 연동이 없어 재무정보를 불러올 수 없습니다.")

    found = _latest_annual(cc, key)
    if not found:
        logger.info("DART 연간 재무 조회 실패(%s)", code)
        return _fallback(code, "재무정보를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.")
    year, data = found

    ycols = ["bfefrmtrm_amount", "frmtrm_amount", "thstrm_amount"]
    ylabels = [str(year - 2), str(year - 1), str(year)]
    ypick = _parse(data, ycols)
    yser = lambda f: [(ypick.get(f) or {}).get(c) for c in ycols]

    rev, opi, ni = yser("revenue"), yser("operating_income"), yser("net_income")
    assets, liab, eq = yser("assets"), yser("liabilities"), yser("equity")
    if not any(rev) and not any(assets):
        return _fallback(code, "DART 재무제표에서 주요 계정을 찾지 못했습니다.")

    annual = block(ylabels, rev, opi, ni, assets, liab, eq)

    quarters = None
    try:
        qrows = _quarterly(cc, key, 4)
    except (requests.RequestException, ValueError) as exc:
        logger.info("DART 분기 재무 실패(%s): %s", code, exc)
        qrows = []
    if qrows:
        col = lambda f: [r.get(f) for r in qrows]
        quarters = block([r["label"] for r in qrows], col("revenue"), col("operating_income"),
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
