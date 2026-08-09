import html
import re

import requests

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"


def _clean(text: str) -> str:
    return html.unescape(re.sub(r"<.*?>", "", text))


def search_news(
    keyword: str,
    client_id: str,
    client_secret: str,
    display: int = 10,
) -> list[dict]:
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    params = {"query": keyword, "display": display, "sort": "date"}

    response = requests.get(NAVER_NEWS_URL, headers=headers, params=params, timeout=10)
    response.raise_for_status()

    items = response.json().get("items", [])
    return [
        {
            "title": _clean(item["title"]),
            "description": _clean(item["description"]),
            "link": item["link"],
            "pubDate": item.get("pubDate", ""),
        }
        for item in items
    ]
