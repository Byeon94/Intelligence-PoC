"""단기자금 탭 — 원화(시장금리·기준금리·스프레드) / 외화(환율·한미 정책금리) 요약.

한국은행 ECOS(funding.ecos) 실데이터이고, 미국 목표금리만 뉴욕 연준(funding.nyfed)을 쓴다. 샘플 폴백은 없다 — 키 미설정·API 장애면 예외가
올라가고 화면에 오류 문구가 뜬다. ECOS 일별 통계는 보통 1영업일 늦게 올라오므로 각 지표에
실제 기준일(date)을 함께 내려준다.
"""
from __future__ import annotations

from .ecos import fetch_series
from .nyfed import fed_target_range

# ── 원화: 817Y002 시장금리(일별) + 722Y001 기준금리 ──────────────────────────
_RATE_STAT, _BASE_STAT, _BASE_ITEM = "817Y002", "722Y001", "0101000"
WON_ITEMS = [   # (키, 항목코드, 화면 라벨)
    ("base", _BASE_ITEM, "한국은행 기준금리"),
    ("call", "010101000", "콜금리(1일)"),
    ("kofr", "010901000", "KOFR"),
    ("cd", "010502000", "CD(91일)"),
    ("cp", "010503000", "CP(91일)"),
    ("msb", "010400000", "통안증권(91일)"),
]
SPREADS = [     # (라벨, 높은 쪽, 낮은 쪽) — bp
    ("콜 − 기준금리", "call", "base"),
    ("CD − 콜", "cd", "call"),
    ("CP − CD", "cp", "cd"),
]
_TREND_KEYS = [("base", "기준금리"), ("call", "콜"), ("cd", "CD 91일"), ("cp", "CP 91일")]
_TREND_POINTS = 65      # 약 3개월(영업일)
_LOOKBACK_DAYS = 130    # 3개월 추이 + 1주 전 비교에 충분한 달력일

# ── 외화: 731Y001 대원화환율(일별) + 미국 목표금리(뉴욕 연준, funding.nyfed) ───────
_FX_STAT = "731Y001"
FX_ITEMS = [
    ("usd", "0000001", "원/달러"),
    ("jpy", "0000002", "원/100엔"),
    ("eur", "0000003", "원/유로"),
    ("cny", "0000053", "원/위안"),
]


def _bp(a: float | None, b: float | None) -> int | None:
    return None if a is None or b is None else round((a - b) * 100)


def _latest(series: list[tuple[str, float]]) -> dict:
    """마지막 값·기준일·직전 관측치 대비 변동."""
    if not series:
        return {"value": None, "date": None, "prev": None}
    date, value = series[-1]
    prev = series[-2][1] if len(series) > 1 else None
    return {"value": value, "date": date, "prev": prev}


def _value_on(series: list[tuple[str, float]], date: str) -> float | None:
    """date 당일(없으면 그 이전 가장 가까운 날)의 값 — 기준금리처럼 매일 값이 있는 시계열 정렬용."""
    found = None
    for d, v in series:
        if d > date:
            break
        found = v
    return found


def _short(date: str) -> str:
    """'2026-09-22' → '9/22'(차트 x축)."""
    _, m, d = date.split("-")
    return f"{int(m)}/{int(d)}"


def get_won_summary() -> dict:
    rates = fetch_series(_RATE_STAT, "D", _LOOKBACK_DAYS)
    base = fetch_series(_BASE_STAT, "D", _LOOKBACK_DAYS, _BASE_ITEM).get(_BASE_ITEM, [])
    series = {key: (base if key == "base" else rates.get(code, [])) for key, code, _ in WON_ITEMS}

    items = []
    for key, _code, label in WON_ITEMS:
        last = _latest(series[key])
        items.append({"key": key, "label": label, "value": last["value"], "date": last["date"],
                      "change_bp": _bp(last["value"], last["prev"])})

    # 시장금리 영업일(콜금리 관측일)을 기준 축으로 쓰고, 기준금리는 그 날짜 값으로 맞춘다.
    axis = [d for d, _ in series["call"]]
    if not axis:
        raise RuntimeError("콜금리 데이터가 없습니다.")

    def on(key: str, date: str) -> float | None:
        return _value_on(series[key], date)

    today_d = axis[-1]
    week_d = axis[-6] if len(axis) >= 6 else axis[0]   # 5영업일 전
    spreads = [{"label": label,
                "value_bp": _bp(on(hi, today_d), on(lo, today_d)),
                "week_ago_bp": _bp(on(hi, week_d), on(lo, week_d))}
               for label, hi, lo in SPREADS]

    trend_axis = axis[-_TREND_POINTS:]
    return {
        "source": "live",
        "as_of": today_d,
        "items": items,
        "spreads": spreads,
        "spread_dates": {"today": today_d, "week_ago": week_d},
        "trend": {
            "labels": [_short(d) for d in trend_axis],
            "series": [{"key": k, "name": name, "values": [on(k, d) for d in trend_axis]}
                       for k, name in _TREND_KEYS],
        },
    }


def get_fx_summary() -> dict:
    fx = fetch_series(_FX_STAT, "D", _LOOKBACK_DAYS)
    items = []
    for key, code, label in FX_ITEMS:
        last = _latest(fx.get(code, []))
        chg = None if last["value"] is None or last["prev"] is None else last["value"] - last["prev"]
        pct = None if chg is None or not last["prev"] else chg / last["prev"] * 100
        items.append({"key": key, "label": label, "value": last["value"], "date": last["date"],
                      "change": chg, "change_pct": pct})

    usd = fx.get("0000001", [])[-_TREND_POINTS:]
    if not usd:
        raise RuntimeError("원/달러 환율 데이터가 없습니다.")

    # 한·미 정책금리(상단 기준): 한국은 기준금리(최신값은 일별, 추이는 월별 722Y001), 미국은
    # 뉴욕 연준 목표금리 범위 상단(일별). 월별 추이는 각 달 마지막 값, 이번 달은 최신 일별 값.
    base = fetch_series(_BASE_STAT, "D", _LOOKBACK_DAYS, _BASE_ITEM).get(_BASE_ITEM, [])
    base_m = fetch_series(_BASE_STAT, "M", 800, _BASE_ITEM).get(_BASE_ITEM, [])
    fed = fed_target_range(800)
    kr = _latest(base)
    us_last = fed[-1]
    kr_m = dict(base_m)
    if kr["date"]:
        kr_m[kr["date"][:7]] = kr["value"]
    us_m: dict[str, float] = {}
    for r in fed:                      # 날짜 오름차순 → 달마다 마지막 값이 남는다
        us_m[r["date"][:7]] = r["upper"]
    months = sorted(set(kr_m) | set(us_m))[-24:]

    return {
        "source": "live",
        "as_of": usd[-1][0],
        "items": items,
        "usd_trend": {"labels": [_short(d) for d, _ in usd], "values": [v for _, v in usd]},
        "policy": {
            "kr": {"value": kr["value"], "date": kr["date"]},
            "us": {"value": us_last["upper"], "lower": us_last["lower"], "date": us_last["date"]},
            "gap_bp": _bp(kr["value"], us_last["upper"]),
            "trend": {"labels": months,
                      "kr": [kr_m.get(m) for m in months],
                      "us": [us_m.get(m) for m in months]},
        },
    }
