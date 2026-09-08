/* 정책·규제 탭: AI 브리핑(3줄 요약 + 재생성) + 기관별 보도자료 */
(function () {
  "use strict";

  var CIRCLED = ["①", "②", "③", "④", "⑤", "⑥"];

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function renderBriefing(d) {
    var box = document.getElementById("pol-brief");
    if (!box) return;

    var when = d.briefing_at || d.generated_at || d.date || "";
    var head =
      '<div class="brief-head">' +
        '<span class="brief-label">💬 AI 정책 브리핑</span>' +
        '<span class="brief-when">' + esc(when) + " 생성</span>" +
        '<button type="button" class="brief-regen" id="pol-regen">↻ 재생성</button>' +
      "</div>";

    if (!d.briefing) {
      box.innerHTML = head +
        '<div class="brief-note">' + esc(d.briefing_note || "AI 브리핑을 사용할 수 없습니다.") + "</div>";
      bindRegen();
      return;
    }
    var bullets = d.briefing
      .split("\n")
      .map(function (l) { return l.replace(/^\s*[-•*]\s*/, "").trim(); })
      .map(function (l) { return l.replace(/\s*·?\s*출처[:：].*$/, "").trim(); })
      .filter(Boolean)
      .map(function (l) {
        // 한 줄 분량으로 축약: 첫 문장까지만, 그래도 길면 잘라서 …
        var cut = l.match(/^(.{25,90}?[.!?。](?=\s|$))/);
        var s = cut ? cut[1] : l;
        if (s.length > 95) s = s.slice(0, 92).replace(/[\s,·]+\S*$/, "") + "…";
        return s;
      })
      .slice(0, 3);

    box.innerHTML = head +
      '<ol class="brief-list">' +
        bullets.map(function (b, i) {
          return '<li><span class="bl-no">' + (CIRCLED[i] || (i + 1)) + "</span>" +
                 '<span class="bl-tx">' + esc(b) + "</span></li>";
        }).join("") +
      "</ol>" +
      (d.briefing_note ? '<div class="brief-note">' + esc(d.briefing_note) + "</div>" : "") +
      '<div class="brief-meta">📌 위 요약은 당일 수집된 공식 보도자료를 기반으로 AI가 자동 생성합니다.' +
        (d.stale ? " · 이전 자료" : "") + "</div>";
    bindRegen();
  }

  function bindRegen() {
    var btn = document.getElementById("pol-regen");
    if (!btn) return;
    btn.addEventListener("click", function () {
      btn.disabled = true;
      btn.textContent = "재생성 중…";
      fetchDigest(true);
    });
  }

  var ORG_NAMES = {
    FSC: "금융위", FSS: "금감원", BOK: "한국은행", MOEF: "재경부",
    KRX: "한국거래소", KDIC: "예보", KSD: "예탁결제원", KOFIA: "금투협",
  };

  function renderGroups(d) {
    renderGroupsInto("pol-groups", d.groups || [], d.failed, ["FSC", "FSS", "BOK", "MOEF"]);
    renderGroupsInto("pol-aff-groups", d.affiliate_groups || [], d.failed, ["KRX", "KDIC", "KSD", "KOFIA"]);
  }

  function renderGroupsInto(elId, groups, failed, scope) {
    var wrap = document.getElementById(elId);
    if (!wrap) return;
    if (!groups.length) {
      wrap.innerHTML = '<div class="chart-error">보도자료를 가져오지 못했습니다.</div>';
      return;
    }
    wrap.innerHTML = groups.map(function (g) {
      var rows = (g.items || []).map(function (it) {
        if (it.link_only) {
          return (
            '<a class="pol-item pol-link" href="' + esc(it.url) + '" target="_blank" rel="noopener">' +
              '<div class="pi-title">🔗 ' + esc(it.title) + "</div>" +
            "</a>"
          );
        }
        return (
          '<a class="pol-item" href="' + esc(it.url) + '" target="_blank" rel="noopener">' +
            '<div class="pi-top"><span class="pi-date">' + esc(it.date || "") + "</span>" +
              (it.dept ? '<span class="pi-dept">' + esc(it.dept) + "</span>" : "") + "</div>" +
            '<div class="pi-title">' + esc(it.title) + "</div>" +
          "</a>"
        );
      }).join("");
      return (
        '<div class="pol-group">' +
          '<div class="pg-head"><span class="pg-badge">' + esc(g.badge) + "</span>" +
            '<span class="pg-name">' + esc(g.org_name) + "</span></div>" +
          rows +
        "</div>"
      );
    }).join("");

    var miss = (failed || []).filter(function (f) { return scope.indexOf(f) >= 0; });
    if (miss.length) {
      wrap.insertAdjacentHTML("beforeend",
        '<div class="brief-note">일부 기관을 불러오지 못했습니다: ' +
        miss.map(function (f) { return ORG_NAMES[f] || f; }).join(", ") + "</div>");
    }
  }

  function fetchDigest(refresh) {
    var url = "/api/policy/digest" + (refresh ? "?refresh=1" : "");
    fetch(url)
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "요청 실패"); return j; }); })
      .then(function (d) {
        var sum = document.getElementById("pol-summary");
        if (sum) {
          var n = (d.press_count != null ? d.press_count : "-");
          sum.innerHTML =
            "조회 기준일 <b>" + esc(d.as_of || d.date || "-") + "</b>" +
            ' <span class="ps-sep">·</span> 금융당국 보도자료 <b>' + esc(n) + "건</b>" +
            ' <span class="ps-sep">·</span> 유관기관 <b>' + esc(d.affiliate_count != null ? d.affiliate_count : "-") + "건</b>" +
            ' <span class="ps-sep">·</span> ' + esc(d.generated_at || "") + " 수집" +
            (d.stale ? ' <span class="ps-sep">·</span> 이전 자료' : "");
        }
        var asof = document.getElementById("pol-asof");
        if (asof) asof.textContent = "";
        renderBriefing(d);
        renderGroups(d);
      })
      .catch(function (e) {
        var box = document.getElementById("pol-brief");
        if (box) box.innerHTML = '<div class="chart-error">' + esc(e.message) + "</div>";
      });
  }

  function initSubtabs() {
    var bar = document.getElementById("pol-subtabs");
    if (!bar || bar.dataset.bound) return;
    bar.dataset.bound = "1";
    bar.addEventListener("click", function (e) {
      var btn = e.target.closest(".subtab-btn");
      if (!btn) return;
      var sub = btn.dataset.sub;
      bar.querySelectorAll(".subtab-btn").forEach(function (b) {
        b.classList.toggle("active", b === btn);
      });
      document.querySelectorAll('#policy-root .sub-panel').forEach(function (p) {
        p.hidden = p.dataset.sub !== sub;
      });
    });
  }

  var loaded = false;
  function load() {
    if (loaded) return;
    loaded = true;
    initSubtabs();
    fetchDigest(false);
  }

  function visible() {
    var p = document.querySelector('.tab-panel[data-panel="policy"]');
    return p && !p.hidden;
  }
  function maybe() { if (visible()) load(); }

  function boot() {
    maybe();
    var tabs = document.getElementById("main-tabs");
    if (tabs) tabs.addEventListener("click", function () { setTimeout(maybe, 0); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
