/* 리서치·뉴스 탭: AI 뉴스 브리핑(3줄 + 재생성) + AI 선별 뉴스 피드 */
(function () {
  "use strict";
  var CIRCLED = ["①", "②", "③"];

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function renderBrief(d) {
    var box = document.getElementById("rs-brief");
    if (!box) return;
    var when = d.briefing_at || d.generated_at || d.date || "";
    var head =
      '<div class="brief-head">' +
        '<span class="brief-label">💬 AI 뉴스 브리핑</span>' +
        '<span class="brief-when">' + esc(when) + " 생성</span>" +
        '<button type="button" class="brief-regen" id="rs-regen">↻ 재생성</button>' +
      "</div>";
    var bullets = (d.briefing || []).filter(Boolean).slice(0, 3);
    if (!bullets.length) {
      box.innerHTML = head + '<div class="brief-note">' +
        esc(d.briefing_note || "브리핑을 사용할 수 없습니다.") + "</div>";
      bindRegen();
      return;
    }
    box.innerHTML = head +
      '<ol class="brief-list">' +
        bullets.map(function (b, i) {
          return '<li><span class="bl-no">' + (CIRCLED[i] || i + 1) + "</span>" +
                 '<span class="bl-tx">' + esc(b) + "</span></li>";
        }).join("") +
      "</ol>" +
      (d.briefing_note ? '<div class="brief-note">' + esc(d.briefing_note) + "</div>" : "") +
      '<div class="brief-meta">📌 네이버 뉴스에서 당일 수집한 기사 중 한국증권금융 업무 관련 항목을 AI가 선별·요약합니다.</div>';
    bindRegen();
  }

  function bindRegen() {
    var btn = document.getElementById("rs-regen");
    if (!btn) return;
    btn.addEventListener("click", function () {
      btn.disabled = true;
      btn.textContent = "재생성 중…";
      fetchDigest(true);
    });
  }

  function renderFeed(d) {
    var wrap = document.getElementById("rs-feed");
    if (!wrap) return;
    var arts = d.articles || [];
    if (!arts.length) {
      wrap.innerHTML = '<div class="chart-error">' +
        esc(d.briefing_note || "선별된 기사가 없습니다.") + "</div>";
      return;
    }
    wrap.innerHTML = arts.map(function (a, i) {
      return (
        '<a class="news-item" href="' + esc(a.url) + '" target="_blank" rel="noopener">' +
          '<div class="ni-rank">' + (i + 1) + "</div>" +
          '<div class="ni-body">' +
            '<div class="ni-top"><span class="ni-tag">' + esc(a.tag || "일반") + "</span>" +
              '<span class="ni-date">' + esc(a.published || "") + "</span></div>" +
            '<div class="ni-title">' + esc(a.title) + "</div>" +
            (a.reason ? '<div class="ni-reason">' + esc(a.reason) + "</div>" : "") +
          "</div>" +
        "</a>"
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
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
