import requests

from .naver_news import search_news

NEWS_CATEGORIES = [
    {
        "code": "ksfc",
        "label": "한국증권금융 뉴스",
        "keywords": ["투자자예탁금", "우리사주", "공매도", "융자", "대주"],
    },
    {
        "code": "finance",
        "label": "금융 뉴스",
        "keywords": ["주식시장", "채권시장", "증권시장"],
    },
    {
        "code": "investment",
        "label": "투자 뉴스",
        "keywords": ["상속", "대출", "IPO", "매각", "PEF", "유상증자"],
    },
    {
        "code": "it",
        "label": "IT관련 뉴스",
        "keywords": ["AI", "코인", "IT감사", "정보보호"],
    },
]

ARTICLES_PER_CATEGORY = 3


def _pick_category_articles(category: dict, client_id: str, client_secret: str) -> list[dict]:
    seen_links = set()
    picked = []
    for keyword in category["keywords"]:
        if len(picked) >= ARTICLES_PER_CATEGORY:
            break
        try:
            articles = search_news(keyword, client_id=client_id, client_secret=client_secret, display=3)
        except requests.exceptions.RequestException:
            continue
        for article in articles:
            if len(picked) >= ARTICLES_PER_CATEGORY:
                break
            if article["link"] in seen_links:
                continue
            seen_links.add(article["link"])
            picked.append(
                {
                    "category": category["code"],
                    "keyword": keyword,
                    "title": article["title"],
                    "description": article["description"],
                    "link": article["link"],
                    "published_label": article["pubDate"],
                }
            )
    return picked


def fetch_all_categories(client_id: str, client_secret: str) -> list[dict]:
    items = []
    for category in NEWS_CATEGORIES:
        items.extend(_pick_category_articles(category, client_id, client_secret))
    return items
