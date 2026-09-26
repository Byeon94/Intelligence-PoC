"""정책·규제 탭 라우트 — 화면(/policy)과 다이제스트 API(/api/policy/digest).

API 는 policy.briefing 의 일일 스냅샷에서 화면이 쓰는 필드만 내보낸다
(브리핑 근거용 상세 본문 body·gemini_attempts 등 내부 필드 제외).
"""
from flask import Blueprint, jsonify, render_template

from .briefing import get_policy_digest

policy_bp = Blueprint(
    "policy",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/policy",
)

_PUBLIC = ("date", "as_of", "press_count", "affiliate_count", "generated_at",
           "groups", "affiliate_groups", "failed",
           "briefing", "briefing_at", "briefing_note", "cached", "stale")
_ITEM_PUBLIC = ("org", "org_name", "badge", "title", "url", "dept", "date", "link_only")


def _public_groups(groups: list[dict] | None) -> list[dict]:
    return [
        {**{k: v for k, v in g.items() if k != "items"},
         "items": [{k: it[k] for k in _ITEM_PUBLIC if k in it} for it in g.get("items") or []]}
        for g in groups or []
    ]


@policy_bp.route("/policy")
def policy_tab():
    return render_template("policy.html")


@policy_bp.route("/api/policy/digest")
def digest():
    # 쿼리 파라미터는 받지 않는다(강제 재생성 없음). 오늘 스냅샷이 아직 없으면 이 요청이
    # 스크랩·AI 브리핑을 수행하고(보통은 /internal/warmup 이 먼저 만들어 둠), 있으면 저장본을 준다.
    try:
        data = get_policy_digest()
    except Exception:  # noqa: BLE001
        policy_bp.logger.exception("정책 다이제스트 조회 실패")
        return jsonify({"error": "정책·규제 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."}), 502
    out = {k: data.get(k) for k in _PUBLIC}
    out["groups"] = _public_groups(data.get("groups"))
    out["affiliate_groups"] = _public_groups(data.get("affiliate_groups"))
    return jsonify(out)
