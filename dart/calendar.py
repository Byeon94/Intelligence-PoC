import calendar as calendar_module

import requests

from .client import search_all_disclosures, viewer_url

# "공모주 캘린더"는 실제 청약/상장 예정일이 아니라, 지분증권 증권신고서가 DART에 "제출된 날"을 보여준다.
# (실제 청약 일정은 제3자배정 등 방식에 따라 없는 경우가 많고, DART 목록 API만으로는 신뢰성 있게
#  복원할 수 없어서 공시 제출일 기준으로 구성했다.)
RIGHTS_TYPES = [
    {"code": "paid_capital", "label": "유상증자", "keyword": "유상증자결정"},
    {"code": "free_capital", "label": "무상증자", "keyword": "무상증자결정"},
    {"code": "capital_reduction", "label": "감자", "keyword": "감자결정"},
    {"code": "treasury_buy", "label": "자기주식취득", "keyword": "자기주식취득"},
    {"code": "treasury_sell", "label": "자기주식처분", "keyword": "자기주식처분"},
    {"code": "dividend", "label": "배당", "keyword": "배당"},
]

CALENDAR_CATEGORIES = [
    {
        "code": "ipo",
        "label": "공모주 캘린더",
        "pblntf_ty": None,
        "pblntf_detail_ty": "C001",
        "keywords": ["증권신고서"],
    },
    {
        "code": "rights",
        "label": "주요 권리일정",
        "pblntf_ty": "B",
        "pblntf_detail_ty": None,
        "keywords": [t["keyword"] for t in RIGHTS_TYPES],
    },
]

MAX_PAGES = 10


def _classify_right(report_nm: str) -> dict | None:
    for t in RIGHTS_TYPES:
        if t["keyword"] in report_nm:
            return t
    return None


def month_range(year_month: str) -> tuple[str, str]:
    year, month = (int(p) for p in year_month.split("-"))
    last_day = calendar_module.monthrange(year, month)[1]
    return f"{year:04d}{month:02d}01", f"{year:04d}{month:02d}{last_day:02d}"


def _match(report_nm: str, keywords: list[str]) -> bool:
    return any(kw in report_nm for kw in keywords)


def fetch_month(api_key: str, year_month: str) -> list[dict]:
    bgn_de, end_de = month_range(year_month)
    items = []

    for category in CALENDAR_CATEGORIES:
        seen_rcept_no = set()
        try:
            disclosures = search_all_disclosures(
                api_key,
                bgn_de,
                end_de,
                pblntf_ty=category["pblntf_ty"],
                pblntf_detail_ty=category["pblntf_detail_ty"],
                max_pages=MAX_PAGES,
            )
        except (requests.exceptions.RequestException, RuntimeError):
            continue

        for d in disclosures:
            report_nm = d.get("report_nm", "")
            rcept_no = d.get("rcept_no", "")
            if not rcept_no or rcept_no in seen_rcept_no:
                continue
            if not _match(report_nm, category["keywords"]):
                continue
            seen_rcept_no.add(rcept_no)
            raw_dt = d.get("rcept_dt", "")
            rcept_dt = f"{raw_dt[0:4]}-{raw_dt[4:6]}-{raw_dt[6:8]}" if len(raw_dt) == 8 else None

            right_type = None
            right_label = None
            if category["code"] == "rights":
                right = _classify_right(report_nm)
                if right:
                    right_type = right["code"]
                    right_label = right["label"]

            items.append(
                {
                    "category": category["code"],
                    "corp_name": d.get("corp_name", ""),
                    "report_nm": report_nm,
                    "rcept_no": rcept_no,
                    "rcept_dt": rcept_dt,
                    "source_url": viewer_url(rcept_no),
                    "right_type": right_type,
                    "right_label": right_label,
                }
            )

    return items
