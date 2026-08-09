from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from .client import search_disclosures, viewer_url

KST = ZoneInfo("Asia/Seoul")

LOOKBACK_DAYS = 7
ITEMS_PER_CATEGORY = 5

# DART 공시 목록(report_nm)만으로는 "담보 목적" 같은 세부 사유까지는 알 수 없어서,
# 관련 가능성이 있는 공시 유형을 폭넓게 모으고 AI 해설에서 "추정"임을 명시한다.
CATEGORIES = [
    {
        "code": "collateral",
        "label": "담보대출 수요 레이더",
        "pblntf_types": ["D"],
        "keywords": ["대량보유상황보고", "특정증권등소유상황보고서"],
    },
    {
        "code": "employee_stock",
        "label": "우리사주 금융 수요",
        "pblntf_types": ["B", "C"],
        "keywords": ["증권신고서", "유상증자결정", "우리사주"],
    },
]


def _date_range() -> tuple[str, str]:
    today = datetime.now(KST).date()
    begin = today - timedelta(days=LOOKBACK_DAYS)
    return begin.strftime("%Y%m%d"), today.strftime("%Y%m%d")


def _match_category(report_nm: str, keywords: list[str]) -> bool:
    return any(kw in report_nm for kw in keywords)


def fetch_all_categories(api_key: str) -> list[dict]:
    bgn_de, end_de = _date_range()
    items = []

    for category in CATEGORIES:
        picked = []
        seen_rcept_no = set()

        for pblntf_ty in category["pblntf_types"]:
            if len(picked) >= ITEMS_PER_CATEGORY:
                break
            try:
                disclosures = search_disclosures(api_key, bgn_de, end_de, pblntf_ty=pblntf_ty)
            except (requests.exceptions.RequestException, RuntimeError):
                continue

            for d in disclosures:
                if len(picked) >= ITEMS_PER_CATEGORY:
                    break
                report_nm = d.get("report_nm", "")
                rcept_no = d.get("rcept_no", "")
                if not rcept_no or rcept_no in seen_rcept_no:
                    continue
                if not _match_category(report_nm, category["keywords"]):
                    continue
                seen_rcept_no.add(rcept_no)
                raw_dt = d.get("rcept_dt", "")
                rcept_dt = f"{raw_dt[0:4]}-{raw_dt[4:6]}-{raw_dt[6:8]}" if len(raw_dt) == 8 else None
                picked.append(
                    {
                        "category": category["code"],
                        "corp_name": d.get("corp_name", ""),
                        "stock_code": d.get("stock_code", ""),
                        "report_nm": report_nm,
                        "flr_nm": d.get("flr_nm", ""),
                        "rcept_no": rcept_no,
                        "rcept_dt": rcept_dt,
                        "source_url": viewer_url(rcept_no),
                    }
                )

        items.extend(picked)

    return items
