/* 증권대차 탭: 주식대차 / 채권대차 (KPI·상위종목·AI 해설은 예시 데이터, 관련 뉴스는 실데이터) */
(function () {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function chgClass(up) {
    return up === true ? "up" : (up === false ? "down" : "flat");
  }

  function kpiHTML(items) {
    return (items || []).map(function (k) {
      var arrow = k.up === true ? "▲ " : (k.up === false ? "▼ " : "");
      var sub = k.change_period ? " (" + esc(k.change_period) + ")" : "";
      return (
        '<div class="kpi">' +
          '<div class="k-label">' + esc(k.label) + "</div>" +
          '<div class="k-value">' + esc(k.value) + "</div>" +
          '<div class="k-delta ' + chgClass(k.up) + '">' + arrow + esc(k.change) + sub + "</div>" +
        "</div>"
      );
    }).join("");
  }

  function stockTableHTML(d) {
    var rows = d.top_stocks || [];
    if (!rows.length) return '<div class="chart-error">데이터가 없습니다.</div>';
    var table =
      '<div class="lend-card"><table class="api-table"><thead><tr>' +
        "<th>종목</th><th>대차잔고</th><th>주간증감</th><th>공매도비중</th><th>시그널</th>" +
      "</tr></thead><tbody>" +
        rows.map(function (r) {
          return (
            "<tr><td>" + esc(r.name) + "</td>" +
            "<td>" + esc(r.balance) + "</td>" +
            '<td class="lend-chg ' + chgClass(r.up) + '">' + esc(r.change) + "</td>" +
            "<td>" + esc(r.short_ratio) + "</td>" +
            '<td><span class="lend-signal ' + esc(r.signal_type || "") + '">' + esc(r.signal) + "</span></td></tr>"
          );
        }).join("") +
      "</tbody></table>" +
      (d.footnote ? '<div class="lend-note">' + esc(d.footnote) + "</div>" : "") +
      "</div>";
    return table;
  }

  function bondTableHTML(rows) {
    if (!rows || !rows.length) return '<div class="chart-error">데이터가 없습니다.</div>';
    return (
      '<div class="lend-card"><table class="api-table"><thead><tr>' +
        "<th>종목군</th><th>대차잔고</th><th>주간증감</th><th>대차료율</th><th>비고</th>" +
      "</tr></thead><tbody>" +
        rows.map(function (r) {
          return (
            "<tr><td>" + esc(r.group) + "</td>" +
            "<td>" + esc(r.balance) + "</td>" +
            '<td class="lend-chg ' + chgClass(r.up) + '">' + esc(r.change) + "</td>" +
            "<td>" + esc(r.rate) + "</td>" +
            "<td>" + esc(r.note) + "</td></tr>"
          );
        }).join("") +
      "</tbody></table></div>"
    );
  }

  function alertHTML(a) {
    if (!a) return "";
    return (
      '<div class="lend-alert">' +
        '<div class="lend-alert-head">' +
          '<span class="pg-badge">' + esc(a.badge) + "</span>" +
          '<span class="lend-alert-title">' + esc(a.title) + "</span>" +
          '<span class="lend-alert-src">' + esc(a.source) + "</span>" +
        "</div>" +
        '<div class="lend-alert-ai">💬 AI 해설: ' + esc(a.ai_note) + "</div>" +
      "</div>"
    );
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
    document.getElementById("lend-stock-kpis").innerHTML = kpiHTML(d.stock.kpi);
    document.getElementById("lend-stock-table").innerHTML = stockTableHTML(d.stock);
    document.getElementById("lend-stock-alert").innerHTML = alertHTML(d.stock.alert);
    document.getElementById("lend-stock-news").innerHTML = newsHTML(d.stock.news);

    document.getElementById("lend-bond-kpis").innerHTML = kpiHTML(d.bond.kpi);
    document.getElementById("lend-bond-alert").innerHTML = alertHTML(d.bond.alert);
    document.getElementById("lend-bond-table").innerHTML = bondTableHTML(d.bond.table);
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
        var box = document.getElementById("lend-stock-kpis");
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
    var workTabs = document.getElementById("work-subtabs");
    if (workTabs) workTabs.addEventListener("click", function () { setTimeout(maybeLoad, 0); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
