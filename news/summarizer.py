from google.genai import Client
from google.genai import errors as genai_errors

SYSTEM_PROMPT = (
    "너는 회사 업무에 필요한 뉴스를 정리해주는 어시스턴트야. "
    "아래 규칙을 반드시 지켜서 답변해.\n"
    "- 소제목(#), 구분선(---) 없이 핵심만 담은 불릿 포인트 3~5개로만 정리해.\n"
    "- 각 불릿은 '- '로 시작하고, 한 문장으로 간결하게 작성해.\n"
    "- 불릿 외의 다른 설명이나 서두는 붙이지 마."
)

MODEL = "gemini-3.5-flash"


def summarize_articles(client: Client, keyword: str, articles: list[dict]) -> str:
    if not articles:
        return f"'{keyword}' 관련 뉴스를 찾지 못했습니다."

    articles_text = "\n\n".join(
        f"제목: {a.get('title', '')}\n내용: {a.get('description', '')}\n링크: {a.get('link', '')}"
        for a in articles
    )

    response = client.models.generate_content(
        model=MODEL,
        config={
            "system_instruction": SYSTEM_PROMPT,
            "thinking_config": {"thinking_budget": 0},
            "max_output_tokens": 800,
        },
        contents=(
            f"키워드: {keyword}\n\n"
            f"다음 뉴스들을 업무에 필요한 핵심 위주로 요약 정리해줘:\n\n{articles_text}"
        ),
    )

    return response.text


def summarize_with_fallback(clients: list[Client], keyword: str, articles: list[dict]) -> str:
    for i, client in enumerate(clients):
        is_last = i == len(clients) - 1
        try:
            return summarize_articles(client, keyword, articles)
        except genai_errors.APIError as e:
            if e.code == 429 and not is_last:
                continue
            raise
