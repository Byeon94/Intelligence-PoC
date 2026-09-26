/* 뉴스 탭: AI 뉴스 브리핑(3줄 + 재생성) + AI 선별 뉴스 피드 */
(function () {
  "use strict";
  var CIRCLED = ["①", "②", "③"];

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  // AI 브리핑을 더보기 없이 바로 펼쳐서 보여준다(예전엔 홈 대시보드와 중복 노출을
  // 줄이려고 기본 접어뒀는데, 이 화면에 들어온 사용자는 바로 보고 싶어함).
  function renderBrief(d) {
    var box = document.getElementById("rs-brief");
    if (!box) return;
    var when = d.briefing_at || d.generated_at || d.date || "";
    var head =
      '<div class="brief-head">' +
        '<span class="brief-label">💬 AI 뉴스 브리핑</span>' +
        '<span class="brief-when">' + esc(when) + " 생성</span>" +
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
    box.innerHTML = head + '<div class="brief-body" id="rs-brief-body">' + body + "</div>";
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

  // 오늘 선별된 기사를 쭉 나열하지 않고, AI가 붙인 태그(키워드)별로 묶는다. 예전엔
  // 태그 그룹을 전부 세로로 쌓아두고 #키워드 칩을 누르면 그 위치로 스크롤만 했는데,
  // 그러면 밑에 있는 태그를 보려고 계속 내려야 했다. 이제 칩은 탭처럼 동작해서
  // 누른 태그의 기사만(그리드로) 보여주고 나머지는 감춘다 — 기본은 "전체".
  var feedGroups = {};
  var feedOrder = [];
  var feedActiveTag = null; // null = 전체

  function drawFeed() {
    var wrap = document.getElementById("rs-feed");
    if (!wrap) return;
    var tags = feedActiveTag ? [feedActiveTag] : feedOrder;
    wrap.innerHTML = tags.map(function (tag) {
      var items = feedGroups[tag];
      return (
        '<div class="ni-group">' +
          (feedActiveTag ? "" :
            '<div class="ni-group-head"><span class="ni-group-tag">' + esc(tag) + "</span>" +
              '<span class="ni-group-count">' + items.length + "건</span></div>") +
          '<div class="ni-group-items">' +
            items.map(function (it) { return newsItemHTML(it.a, it.rank); }).join("") +
          "</div>" +
        "</div>"
      );
    }).join("");
  }

  function drawKeywordNav() {
    var nav = document.getElementById("rs-keyword-nav");
    if (!nav) return;
    var total = feedOrder.reduce(function (n, tag) { return n + feedGroups[tag].length; }, 0);
    var chips = ['<button type="button" class="ni-kw-chip' + (feedActiveTag === null ? " active" : "") +
      '" data-tag="">전체 <span class="ni-kw-chip-n">' + total + "</span></button>"];
    feedOrder.forEach(function (tag) {
      chips.push('<button type="button" class="ni-kw-chip' + (feedActiveTag === tag ? " active" : "") +
        '" data-tag="' + esc(tag) + '">#' + esc(tag) +
        ' <span class="ni-kw-chip-n">' + feedGroups[tag].length + "</span></button>");
    });
    nav.innerHTML = chips.join("");
    nav.querySelectorAll(".ni-kw-chip").forEach(function (chip) {
      chip.addEventListener("click", function () {
        feedActiveTag = chip.dataset.tag || null;
        nav.querySelectorAll(".ni-kw-chip").forEach(function (c) {
          c.classList.toggle("active", c === chip);
        });
        drawFeed();
      });
    });
  }

  function renderFeed(d) {
    var wrap = document.getElementById("rs-feed");
    var nav = document.getElementById("rs-keyword-nav");
    var countEl = document.getElementById("rs-feed-count");
    if (!wrap) return;
    var arts = d.articles || [];
    if (countEl) countEl.textContent = "한국증권금융 업무 관련 " + arts.length + "건";
    if (!arts.length) {
      wrap.innerHTML = '<div class="chart-error">' +
        esc(d.briefing_note || "선별된 기사가 없습니다.") + "</div>";
      if (nav) nav.innerHTML = "";
      return;
    }
    feedGroups = {};
    feedOrder = [];
    feedActiveTag = null;
    arts.forEach(function (a, i) {
      var tag = a.tag || "일반";
      if (!feedGroups[tag]) { feedGroups[tag] = []; feedOrder.push(tag); }
      feedGroups[tag].push({ a: a, rank: i + 1 });
    });
    drawKeywordNav();
    drawFeed();
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
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
