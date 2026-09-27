/* 모든 화면 JS가 같이 쓰는 헬퍼 — window.KSFC 로 노출한다.
 * index.html·sector_page.html 에서 다른 화면 스크립트보다 먼저 로드해야 한다.
 *
 *   KSFC.esc(s)            innerHTML 에 넣을 문자열 이스케이프(& < > " ')
 *   KSFC.safeUrl(u)        http(s) 링크만 통과, 그 외(javascript: 등)는 "#"
 *   KSFC.get(url)          fetch → JSON. HTTP 오류면 서버의 {error} 메시지로 reject
 *   KSFC.CIRCLED           ①②③… 번호 표기
 *   KSFC.bindBriefMore(el, n)  AI 브리핑 첫 줄만 보이고 나머지 n건은 "더보기"로 펼침
 */
(function () {
  "use strict";

  var ESC_MAP = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return ESC_MAP[c]; });
  }

  function safeUrl(u) {
    u = String(u || "").trim();
    return /^https?:\/\//i.test(u) ? u : "#";
  }

  function get(url) {
    return fetch(url).then(function (r) {
      return r.text().then(function (t) {
        var j;
        try { j = t ? JSON.parse(t) : {}; } catch (e) { throw new Error("응답을 해석하지 못했습니다"); }
        if (!r.ok) throw new Error(j.error || "요청 실패");
        return j;
      });
    });
  }

  var CIRCLED = ["①", "②", "③", "④", "⑤", "⑥"];

  // 정책 / 뉴스 탭 AI 브리핑: 모바일에서 브리핑이 화면을 다 차지하면 아래 목록이
  // 있다는 걸 알아채기 어려워, 첫 줄만 보여주고 나머지는 버튼으로 펼친다.
  // bodyEl 을 innerHTML 로 다시 그리면 버튼도 같이 사라지므로 렌더할 때마다 다시 호출하면 된다.
  function bindBriefMore(bodyEl, moreCount) {
    if (!bodyEl || moreCount < 1) return;
    bodyEl.classList.add("brief-collapsed");
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "brief-more-btn";
    function sync() {
      var collapsed = bodyEl.classList.contains("brief-collapsed");
      btn.textContent = collapsed ? "더보기 (" + moreCount + "건) ▾" : "접기 ▴";
      btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
    }
    btn.addEventListener("click", function () {
      bodyEl.classList.toggle("brief-collapsed");
      sync();
    });
    sync();
    bodyEl.appendChild(btn);
  }

  window.KSFC = { esc: esc, safeUrl: safeUrl, get: get, CIRCLED: CIRCLED, bindBriefMore: bindBriefMore };
})();
