from google.genai import Client

SYSTEM_PROMPT = (
    "너는 회사 업무에 필요한 뉴스를 정리해주는 어시스턴트야. "
    "주어진 뉴스 목록의 핵심 내용을 한국어로 간결하게 요약 정리해줘."
)

MODEL = "gemini-flash-latest"


def summarize_articles(client: Client, keyword: str, articles: list[dict]) -> str:
    if not articles:
        return f"'{keyword}' 관련 뉴스를 찾지 못했습니다."

    articles_text = "\n\n".join(
        f"제목: {a['title']}\n내용: {a['description']}\n링크: {a['link']}"
        for a in articles
    )

    response = client.models.generate_content(
        model=MODEL,
        config={"system_instruction": SYSTEM_PROMPT},
        contents=(
            f"키워드: {keyword}\n\n"
            f"다음 뉴스들을 업무에 필요한 핵심 위주로 요약 정리해줘:\n\n{articles_text}"
        ),
    )

    return response.text
