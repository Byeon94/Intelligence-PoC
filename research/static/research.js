/* 리서치·뉴스 탭: AI 뉴스 브리핑(3줄 + 재생성) + AI 선별 뉴스 피드 */
(function () {
  "use strict";
  var CIRCLED = ["①", "②", "③"];

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  // AI 브리핑은 홈 대시보드에도 이미 표시되므로, 이 화면에서는 기본 접어두고
  // "더보기"를 눌렀을 때만 펼친다(중복 노출 최소화).
  function renderBrief(d) {
    var box = document.getElementById("rs-brief");
    if (!box) return;
    var when = d.briefing_at || d.generated_at || d.date || "";
    var head =
      '<div class="brief-head">' +
        '<span class="brief-label">💬 AI 뉴스 브리핑</span>' +
        '<span class="brief-when">' + esc(when) + " 생성</span>" +
        '<button type="button" class="brief-toggle" id="rs-brief-toggle">더보기 ↓</button>' +
      "</div>";
    var bullets = (d.briefing || []).filter(Boolean).slice(0, 3);
    var body;
    if (!bullets.length) {
      body = '<div class="brief-note">' + esc(d.briefing_note || "브리핑을 사용할 수 없습니다.") + "</div>";
    } else {
      body = '<ol class="brief-list">' +
          bullets.map(function (b, i) {
            return '<li><span class="bl-no">' + (CIRCLED[i] || i + 1) + "</span>" +
                   '<span class="bl-tx">' + esc(b) + "</span></li>";
          }).join("") +
        "</ol>" +
        (d.briefing_note ? '<div class="brief-note">' + esc(d.briefing_note) + "</div>" : "") +
        '<div class="brief-meta">📌 네이버 뉴스에서 당일 수집한 기사 중 한국증권금융 업무 관련 항목을 AI가 선별·요약합니다.</div>';
    }
    box.innerHTML = head + '<div class="brief-body" id="rs-brief-body" hidden>' + body + "</div>";
    bindBriefToggle();
  }

  function bindBriefToggle() {
    var btn = document.getElementById("rs-brief-toggle");
    var body = document.getElementById("rs-brief-body");
    if (!btn || !body) return;
    btn.addEventListener("click", function () {
      var show = body.hidden;
      body.hidden = !show;
      btn.textContent = show ? "접기 ↑" : "더보기 ↓";
    });
  }

  function newsItemHTML(a, rank) {
    return (
      '<a class="news-item" href="' + esc(a.url) + '" target="_blank" rel="noopener">' +
        '<div class="ni-rank">' + rank + "</div>" +
        '<div class="ni-body">' +
          '<div class="ni-top"><span class="ni-date">' + esc(a.published || "") + "</span></div>" +
          '<div class="ni-title">' + esc(a.title) + "</div>" +
          (a.reason ? '<div class="ni-reason">' + esc(a.reason) + "</div>" : "") +
        "</div>" +
      "</a>"
    );
  }

  // 오늘 선별된 기사를 쭉 나열하지 않고, AI가 붙인 태그(키워드)별로 묶어서 보여준다.
  // 그룹 순서는 그룹 안에서 가장 순위가 높은(=AI가 가장 관련도 높다고 본) 기사를
  // 기준으로 정해, 전체 관련도 우선순위는 그대로 유지한다.
  function renderFeed(d) {
    var wrap = document.getElementById("rs-feed");
    if (!wrap) return;
    var arts = d.articles || [];
    if (!arts.length) {
      wrap.innerHTML = '<div class="chart-error">' +
        esc(d.briefing_note || "선별된 기사가 없습니다.") + "</div>";
      return;
    }
    var groups = {};
    var order = [];
    arts.forEach(function (a, i) {
      var tag = a.tag || "일반";
      if (!groups[tag]) { groups[tag] = []; order.push(tag); }
      groups[tag].push({ a: a, rank: i + 1 });
    });
    wrap.innerHTML = order.map(function (tag) {
      var items = groups[tag];
      return (
        '<div class="ni-group">' +
          '<div class="ni-group-head"><span class="ni-group-tag">' + esc(tag) + "</span>" +
            '<span class="ni-group-count">' + items.length + "건</span></div>" +
          '<div class="ni-group-items">' +
            items.map(function (it) { return newsItemHTML(it.a, it.rank); }).join("") +
          "</div>" +
        "</div>"
      );
    }).join("");
  }

  function fetchDigest(refresh) {
    fetch("/api/research/digest" + (refresh ? "?refresh=1" : ""))
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "요청 실패"); return j; }); })
      .then(function (d) {
        var sum = document.getElementById("rs-summary");
        if (sum) {
          sum.innerHTML =
            "수집일 <b>" + esc(d.date || "-") + "</b>" +
            ' <span class="ps-sep">·</span> 후보 <b>' + esc(d.candidate_count != null ? d.candidate_count : "-") + "건</b> 중 AI 선별 <b>" +
            esc((d.articles || []).length) + "건</b>" +
            ' <span class="ps-sep">·</span> ' + esc(d.generated_at || "") + " 수집" +
            (d.stale ? ' <span class="ps-sep">·</span> 이전 자료' : "");
        }
        renderBrief(d);
        renderFeed(d);
      })
      .catch(function (e) {
        var box = document.getElementById("rs-brief");
        if (box) box.innerHTML = '<div class="chart-error">' + esc(e.message) + "</div>";
      });
  }

  var loaded = false;
  function load() { if (loaded) return; loaded = true; fetchDigest(false); }
  function visible() {
    var p = document.querySelector('.tab-panel[data-panel="research"]');
    return p && !p.hidden;
  }
  function maybe() { if (visible()) load(); }
  function boot() {
    maybe();
    var tabs = document.getElementById("main-tabs");
    if (tabs) tabs.addEventListener("click", function () { setTimeout(maybe, 0); });
    var workTabs = document.getElementById("work-subtabs");
    if (workTabs) workTabs.addEventListener("click", function () { setTimeout(maybe, 0); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
