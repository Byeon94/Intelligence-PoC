import re
import time
from datetime import datetime, timedelta

import requests

# KOFIA 종합통계 포털의 상세 통계 페이지는 자체 BI 리포팅 엔진(Cleopatra)이
# 내부 API로 렌더링하며 해당 API는 브라우저 정상 접근 흐름에서만 통과되는
# 웹방화벽(WAF) 뒤에 있어 우회하지 않는다. 대신 메인 페이지(stat/main.do)에
# 서버 렌더링되어 있는 주요 지표 위젯 HTML을 그대로 파싱한다.
KOFIA_MAIN_URL = "https://freesis.kofia.or.kr/stat/main.do"

# {메인 페이지 위젯 라벨: 화면에 보여줄 이름}
FUND_FLOW_ITEMS = [
    {"label": "투자자예탁금", "name": "투자자예탁금"},
    {"label": "신용융자", "name": "신용거래융자"},
]

CACHE_TTL_SECONDS = 300
_cache: dict[str, object] = {"data": None, "ts": 0.0}

_WIDGET_RE = re.compile(
    r'<dt class="chart-name"><a[^>]*>(?P<label>[^<]+)</a></dt>\s*'
    r'<dd class="etc"><span class="dan">(?P<unit>[^<]*)</span>\s*\|\s*'
    r'<span class="date">(?P<date>[^<]*)</span></dd>\s*'
    r'<dd class="chart-num">\s*<span class="num1">(?P<value>[^<]*)</span>\s*'
    r'(?:<span class="num2[ab]">(?P<change>[^<]*)</span>\s*)?'
    r'<span class="num3">(?P<pct>[^<]*)</span>'
)


def _parse_as_of(date_text: str) -> str:
    month, day = (int(p) for p in date_text.split("/"))
    today = datetime.now()
    candidate = today.replace(month=month, day=day)
    if candidate > today + timedelta(days=3):
        candidate = candidate.replace(year=today.year - 1)
    return candidate.date().isoformat()


def _fetch_main_widgets() -> dict[str, dict]:
    response = requests.get(
        KOFIA_MAIN_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=10
    )
    response.raise_for_status()
    response.encoding = "utf-8"

    widgets = {}
    for m in _WIDGET_RE.finditer(response.text):
        widgets[m.group("label").strip()] = {
            "value": float(m.group("value").replace(",", "")),
            "change": float((m.group("change") or "0").replace(",", "")),
            "change_pct": float(m.group("pct").replace("%", "")),
            "as_of": _parse_as_of(m.group("date").strip()),
        }
    return widgets


def get_fund_flow_indicators(use_cache: bool = True) -> list[dict]:
    now = time.time()
    if use_cache and _cache["data"] is not None and now - _cache["ts"] < CACHE_TTL_SECONDS:
        return _cache["data"]

    widgets = _fetch_main_widgets()

    results = []
    for item in FUND_FLOW_ITEMS:
        raw = widgets.get(item["label"])
        if raw is None:
            continue
        # 백만원 단위로 내려오는 값을 조원 단위로 환산해 표시한다.
        results.append(
            {
                "name": item["name"],
                "value": raw["value"] / 1_000_000,
                "unit": "조원",
                "change": raw["change"] / 1_000_000,
                "change_pct": raw["change_pct"],
                "as_of": raw["as_of"],
            }
        )

    _cache["data"] = results
    _cache["ts"] = now
    return results
