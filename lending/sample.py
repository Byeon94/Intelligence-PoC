"""증권대차 탭 화면 데이터.

예탁결제원(KSD)·KRX의 종목별 대차잔고·공매도 비중 등은 무료 공개 API로
제공되지 않아(계약·유료 데이터 영역), 연구보고서 예시화면과 동일한 구조의
샘플 값으로 화면을 구성한다. 화면 UI/구조 검증용이며, 실 데이터 계약 체결
시 이 모듈만 실제 조회 로직으로 교체하면 된다. (관련 뉴스만 실데이터: lending/news.py)
"""
from __future__ import annotations

STOCK_LENDING = {
    "kpi": [
        {"label": "주식 대차잔고", "value": "82.4조", "change": "1.1조", "change_period": "주간", "up": True},
        {"label": "공매도 거래비중", "value": "4.8%", "change": "0.6%p", "change_period": "", "up": True},
        {"label": "대차체결(일)", "value": "2.1조", "change": "18%", "change_period": "", "up": True},
        {"label": "리콜 급증 종목", "value": "3종목", "change": "상환요구 동향", "change_period": "", "up": None},
    ],
    "top_stocks": [
        {"name": "○○바이오", "balance": "1.8조", "change": "+22%", "up": True,
         "short_ratio": "12.4%", "signal": "숏 집중", "signal_type": "warn"},
        {"name": "□□전자", "balance": "1.2조", "change": "-8%", "up": False,
         "short_ratio": "3.1%", "signal": "숏커버 추정", "signal_type": "info"},
        {"name": "△△화학", "balance": "0.9조", "change": "+15%", "up": True,
         "short_ratio": "8.7%", "signal": "숏 증가", "signal_type": "warn"},
    ],
    "footnote": "대차 수요 변화 = 중개 비즈니스 볼륨 + 담보종목 수급 리스크 양면 시그널 — 심사·리스크 탭 연동",
    "alert": {
        "badge": "제도",
        "title": "공매도 전산시스템 의무화 후속조치",
        "source": "금융위 오늘",
        "ai_note": "대차거래 기관간 잔고관리 요건 강화 — 중개 시스템 대응 필요 항목 3건 식별. 정책·대관 탭 연동.",
    },
}

BOND_LENDING = {
    "kpi": [
        {"label": "채권 대차잔고", "value": "138조", "change": "3.2조", "change_period": "주간", "up": True},
        {"label": "국고채 비중", "value": "78%", "change": "보합", "change_period": "", "up": None},
        {"label": "대차체결(일)", "value": "3.4조", "change": "11%", "change_period": "", "up": True},
        {"label": "대차료율(국고 지표물)", "value": "12bp", "change": "2bp", "change_period": "", "up": True},
    ],
    "alert": {
        "badge": "주시",
        "title": "국고 10년 지표물 대차수요 증가 — 금리 상승 베팅 추정",
        "source": "예탁원 공개 통계",
        "ai_note": "10년 지표물 대차잔고 주간 +8%. 선물 미결제약정 증가와 동행 — 듀레이션 숏 포지션 확대 가능성. 마켓 탭 금리·크레딧 연동.",
    },
    "table": [
        {"group": "국고 3년 지표물", "balance": "18.2조", "change": "+4%", "up": True, "rate": "9bp", "note": "선물 베이시스 연계"},
        {"group": "국고 10년 지표물", "balance": "22.6조", "change": "+8%", "up": True, "rate": "12bp", "note": "수요 증가"},
        {"group": "통안채", "balance": "9.4조", "change": "—", "up": None, "rate": "7bp", "note": "—"},
        {"group": "크레딧 (은행채 등)", "balance": "4.1조", "change": "-2%", "up": False, "rate": "15bp", "note": "—"},
    ],
}
