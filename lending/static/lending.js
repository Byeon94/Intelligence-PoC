/* 증권대차 탭: 주식대차 / 채권대차. 대차잔고·상위종목 등 KPI 데이터는 정식 연동 전이라
   "준비중" 안내만 표시하고(lending.html), 관련 뉴스만 실데이터로 보여준다. */
(function () {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function newsHTML(items) {
    if (!items || !items.length) {
      return '<div class="lend-card"><div class="page-note">관련 뉴스를 찾지 못했습니다.</div></div>';
    }
    return '<div class="lend-card"><ul class="gal-mini-reports">' + items.map(function (n) {
      return (
        '<li><a href="' + esc(n.url || "#") + '" target="_blank" rel="noopener">' +
          '<span class="gmr-title">' + esc(n.title || "") + "</span></a></li>"
      );
    }).join("") + "</ul></div>";
  }

  var loaded = false;
  var cache = null;

  function render(d) {
    document.getElementById("lend-stock-news").innerHTML = newsHTML(d.stock.news);
    document.getElementById("lend-bond-news").innerHTML = newsHTML(d.bond.news);
  }

  function load() {
    if (loaded) return;
    loaded = true;
    fetch("/api/lending/data")
      .then(function (r) { return r.json(); })
      .then(function (d) { cache = d; render(d); })
      .catch(function () {
        loaded = false;
        var box = document.getElementById("lend-stock-news");
        if (box) box.innerHTML = '<div class="chart-error">데이터를 불러오지 못했습니다.</div>';
      });
  }

  function activateSub(sub) {
    var root = document.getElementById("lending-root");
    var bar = document.getElementById("lending-subtabs");
    if (!root || !bar) return;
    bar.querySelectorAll(".subtab-btn").forEach(function (b) {
      b.classList.toggle("active", b.dataset.sub === sub);
    });
    root.querySelectorAll(".sub-panel").forEach(function (p) {
      p.hidden = p.dataset.sub !== sub;
    });
  }

  function initSubtabs() {
    var bar = document.getElementById("lending-subtabs");
    if (!bar) return;
    bar.addEventListener("click", function (e) {
      var btn = e.target.closest(".subtab-btn");
      if (btn) activateSub(btn.dataset.sub);
    });
  }

  function visible() {
    var p = document.querySelector('.tab-panel[data-panel="lending"]');
    return p && !p.hidden;
  }
  function maybeLoad() { if (visible()) load(); }

  function boot() {
    initSubtabs();
    maybeLoad();
    var tabs = document.getElementById("main-tabs");
    if (tabs) tabs.addEventListener("click", function () { setTimeout(maybeLoad, 0); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
