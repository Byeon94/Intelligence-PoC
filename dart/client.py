import requests

DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DART_VIEWER_URL = "https://dart.fss.or.kr/dsaf001/main.do"

# 013 = 조회된 데이터가 없습니다 (정상 상황, 오류 아님)
_OK_STATUS = {"000", "013"}


def _request(
    api_key: str,
    bgn_de: str,
    end_de: str,
    pblntf_ty: str | None,
    pblntf_detail_ty: str | None,
    page_no: int,
    page_count: int,
    corp_cls: str | None = None,
) -> dict:
    params = {
        "crtfc_key": api_key,
        "bgn_de": bgn_de,
        "end_de": end_de,
        "page_no": page_no,
        "page_count": page_count,
    }
    if pblntf_ty:
        params["pblntf_ty"] = pblntf_ty
    if pblntf_detail_ty:
        params["pblntf_detail_ty"] = pblntf_detail_ty
    if corp_cls:
        params["corp_cls"] = corp_cls

    response = requests.get(DART_LIST_URL, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    if data.get("status") not in _OK_STATUS:
        raise RuntimeError(f"DART API 오류: {data.get('status')} {data.get('message')}")

    return data


def search_disclosures(
    api_key: str,
    bgn_de: str,
    end_de: str,
    pblntf_ty: str | None = None,
    pblntf_detail_ty: str | None = None,
    page_count: int = 100,
) -> list[dict]:
    data = _request(api_key, bgn_de, end_de, pblntf_ty, pblntf_detail_ty, page_no=1, page_count=page_count)
    return data.get("list") or []


def search_all_disclosures(
    api_key: str,
    bgn_de: str,
    end_de: str,
    pblntf_ty: str | None = None,
    pblntf_detail_ty: str | None = None,
    max_pages: int = 10,
) -> list[dict]:
    items = []
    page_no = 1
    while page_no <= max_pages:
        data = _request(api_key, bgn_de, end_de, pblntf_ty, pblntf_detail_ty, page_no=page_no, page_count=100)
        items.extend(data.get("list") or [])
        if page_no >= data.get("total_page", 1):
            break
        page_no += 1
    return items


def count_disclosures(
    api_key: str,
    bgn_de: str,
    end_de: str,
    corp_cls: str | None = None,
    pblntf_ty: str | None = None,
) -> int:
    data = _request(
        api_key, bgn_de, end_de, pblntf_ty, None, page_no=1, page_count=1, corp_cls=corp_cls
    )
    return data.get("total_count", 0)


def viewer_url(rcept_no: str) -> str:
    return f"{DART_VIEWER_URL}?rcpNo={rcept_no}"
