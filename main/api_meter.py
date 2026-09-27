"""외부 API 호출 횟수 카운터 — 배치 결과 알림(main/batch_report.py)의 "기관별 호출 수"용.

모든 모듈이 requests(get/post·Session)를 쓰므로 requests.Session.send 한 곳에 카운터를 달아
호스트별로 센다(모듈마다 계측 코드를 넣지 않기 위함). Gemini(google-genai, httpx)는 requests 를
안 거치므로 main/gemini.generate_text 에서 count("gemini") 로 따로 센다.

카운터는 프로세스 메모리 누적값이다. 배치 전후 snapshot() 차이로 "이번 배치 동안의 호출 수"를
구한다(같은 시간에 들어온 화면 요청의 호출도 섞일 수 있음 — 새벽엔 거의 없다).
"""
from __future__ import annotations

import threading
from collections import Counter
from urllib.parse import urlsplit

import requests

_lock = threading.Lock()
_counts: Counter[str] = Counter()

# 호스트 → 알림에 보일 이름(접미사 일치). 목록에 없는 호스트는 "기타(호스트)"로 묶는다.
_HOST_LABELS = [
    ("opendart.fss.or.kr", "금감원 DART"),
    ("dart.fss.or.kr", "금감원 DART"),
    ("openapi.naver.com", "네이버 검색 API"),
    ("naver.com", "네이버(금융·뉴스 페이지)"),
    ("ecos.bok.or.kr", "한국은행 ECOS"),
    ("bok.or.kr", "한국은행(보도자료)"),
    ("apis.data.go.kr", "공공데이터포털"),
    ("markets.newyorkfed.org", "뉴욕 연준"),
    ("finance.yahoo.com", "Yahoo Finance"),
    ("kmbco.com", "한국자금중개"),
    ("fsc.go.kr", "금융위원회"),
    ("fss.or.kr", "금융감독원"),
    ("hankyung.com", "한경"),
    ("freesis.kofia.or.kr", "금투협 FreeSIS"),
    ("kofia.or.kr", "금융투자협회"),
]
_EXCLUDE = ("api.telegram.org", "supabase.co")   # 알림 발송·DB 저장은 외부 데이터 호출이 아님


def label_for(host: str) -> str:
    host = (host or "").lower()
    for suffix, label in _HOST_LABELS:
        if host == suffix or host.endswith("." + suffix):
            return label
    return f"기타({host})" if host else "기타"


def count(label: str, n: int = 1) -> None:
    with _lock:
        _counts[label] += n


def snapshot() -> Counter[str]:
    with _lock:
        return Counter(_counts)


_orig_send = requests.Session.send


def _counting_send(self, request, **kwargs):
    host = urlsplit(request.url).hostname or ""
    if not host.endswith(_EXCLUDE):
        count(label_for(host))
    return _orig_send(self, request, **kwargs)


def install() -> None:
    """앱 시작 시 한 번 — requests.Session.send 를 카운팅 래퍼로 교체(중복 설치 무시)."""
    if requests.Session.send is not _counting_send:
        requests.Session.send = _counting_send
