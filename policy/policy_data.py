import json
from datetime import datetime
from zoneinfo import ZoneInfo

from google.genai import Client, types
from google.genai import errors as genai_errors

KST = ZoneInfo("Asia/Seoul")

MODEL = "gemini-3.5-flash"

AUTHORITY_ORGS = [
    {"code": "FSC", "name": "금융위원회", "badge": "금융위"},
    {"code": "BOK", "name": "한국은행", "badge": "한은"},
    {"code": "MOEF", "name": "재정경제부", "badge": "재경부"},
    {"code": "FSS", "name": "금융감독원", "badge": "금감원"},
]

AFFILIATE_ORGS = [
    {"code": "KRX", "name": "한국거래소", "badge": "거래소"},
    {"code": "KSD", "name": "한국예탁결제원", "badge": "예탁원"},
    {"code": "KOFIA", "name": "금융투자협회", "badge": "금투협"},
]

ASSEMBLY_BILLS = [
    {"code": "CAPMKT", "name": "자본시장법 개정안", "badge": "자본시장법"},
    {"code": "DIGIASSET", "name": "디지털자산기본법", "badge": "디지털자산기본법"},
]

RESEARCH_ORGS = [
    {"code": "KCMI", "name": "자본시장연구원", "badge": "자본연"},
    {"code": "KIF", "name": "금융연구원", "badge": "금융연"},
]

ALL_ENTITIES = (
    [{**o, "category": "authority"} for o in AUTHORITY_ORGS]
    + [{**o, "category": "affiliate"} for o in AFFILIATE_ORGS]
    + [{**b, "category": "assembly"} for b in ASSEMBLY_BILLS]
    + [{**r, "category": "research"} for r in RESEARCH_ORGS]
)

_ENTITY_BY_CODE = {e["code"]: e for e in ALL_ENTITIES}


def _build_prompt() -> str:
    org_lines = "\n".join(f"- {o['name']} ({o['code']})" for o in AUTHORITY_ORGS + AFFILIATE_ORGS)
    bill_lines = "\n".join(f"- {b['name']} ({b['code']})" for b in ASSEMBLY_BILLS)
    research_lines = "\n".join(f"- {r['name']} ({r['code']})" for r in RESEARCH_ORGS)
    return (
        "너는 국내 금융 정책·제도 동향을 수집하는 리서치 어시스턴트야. "
        "구글 검색으로 아래 세 그룹에 대한 최신 정보를 각각 찾아줘.\n\n"
        f"[그룹 1] 금융당국·유관기관 공식 홈페이지 공지사항·보도자료 (기관마다 1건씩):\n{org_lines}\n\n"
        f"[그룹 2] 국회에 계류 중인 아래 법안의 최신 심사 진행 상황 (법안마다 1건씩):\n{bill_lines}\n\n"
        f"[그룹 3] 아래 연구기관이 최근 발간한 보고서 (기관마다 1건씩):\n{research_lines}\n\n"
        "각 대상마다 가장 최근 항목 1건만 선택해서, 다른 설명이나 마크다운 코드블록 없이 "
        "아래 형식의 JSON 배열 텍스트만 출력해:\n\n"
        "[\n"
        "  {\n"
        '    "code": "FSC",\n'
        '    "title": "실제 발표·보도·법안 심사·보고서 제목",\n'
        '    "summary": "핵심 내용 1~2문장 요약",\n'
        '    "tags": ["#해시태그1", "#해시태그2"],\n'
        '    "source_label": "공식 보도자료 / 뉴스 보도 / 공고 / 국회 의안정보시스템 / 발간자료 중 하나",\n'
        '    "source_url": "실제 출처 URL",\n'
        '    "published_label": "6/17 또는 오늘 같은 날짜 표시"\n'
        "  }\n"
        "]\n\n"
        "실제 검색으로 확인한 사실만 담고 절대 지어내지 마. 항목을 찾지 못한 대상은 배열에서 제외해."
    )


def _extract_json_array(text: str) -> list[dict]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("Gemini 응답에서 JSON 배열을 찾을 수 없습니다.")
    return json.loads(cleaned[start : end + 1])


def _generate(client: Client) -> str:
    response = client.models.generate_content(
        model=MODEL,
        config={
            "tools": [types.Tool(googleSearch=types.GoogleSearch())],
            "max_output_tokens": 12288,
        },
        contents=_build_prompt(),
    )
    return response.text


def fetch_policy_updates(clients: list[Client]) -> list[dict]:
    text = None
    for i, client in enumerate(clients):
        is_last = i == len(clients) - 1
        try:
            text = _generate(client)
            break
        except genai_errors.APIError as e:
            if e.code == 429 and not is_last:
                continue
            raise

    items = _extract_json_array(text)
    today = datetime.now(KST).date().isoformat()

    results = []
    for item in items:
        entity = _ENTITY_BY_CODE.get(item.get("code"))
        if not entity:
            continue
        results.append(
            {
                "category": entity["category"],
                "org_code": entity["code"],
                "org_name": entity["name"],
                "title": item.get("title", ""),
                "summary": item.get("summary", ""),
                "tags": item.get("tags") or [],
                "source_label": item.get("source_label") or "뉴스 보도",
                "source_url": item.get("source_url"),
                "published_label": item.get("published_label") or "",
                "fetched_date": today,
            }
        )
    return results
