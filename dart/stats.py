from datetime import datetime
from zoneinfo import ZoneInfo

from .client import count_disclosures

KST = ZoneInfo("Asia/Seoul")

STAT_CATEGORIES = [
    {"code": "kospi", "label": "유가증권시장", "corp_cls": "Y", "pblntf_ty": None},
    {"code": "kosdaq", "label": "코스닥시장", "corp_cls": "K", "pblntf_ty": None},
    {"code": "ownership", "label": "5%·임원보고", "corp_cls": None, "pblntf_ty": "D"},
]


def fetch_market_stats(api_key: str) -> dict:
    today = datetime.now(KST).date().isoformat()
    bgn_de = end_de = today.replace("-", "")

    counts = []
    for cat in STAT_CATEGORIES:
        count = count_disclosures(
            api_key, bgn_de, end_de, corp_cls=cat["corp_cls"], pblntf_ty=cat["pblntf_ty"]
        )
        counts.append({"code": cat["code"], "label": cat["label"], "count": count})

    return {"date": today, "stats": counts}
