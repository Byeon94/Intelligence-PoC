/* 여신·심사 탭 메인 화면: 담보대출·우리사주 금융 수요 리드 레이더(DART 실데이터) +
   상속·증여 관련 뉴스 동향(참고용, AI 관련도 판단). 종목별 기업분석/공시/리포트 조회는
   전사위젯 > 내 위젯의 개별 위젯에서 제공한다(이 탭에서는 제공하지 않음). */
(function () {
  "use strict";

  function get(url) {
    return fetch(url).then(function (r) {
      return r.text().then(function (t) {
        var j = null;
        if (t) { try { j = JSON.parse(t); } catch (e) { j = null; } }
        if (j === null) {
          throw new Error(
            r.status >= 500 || r.status === 0
              ? "서버가 응답하지 못했습니다 (" + (r.status || "네트워크") + "). 잠시 후 다시 시도해주세요."
              : "서버 응답을 해석하지 못했습니다 (" + r.status + ")."
          );
        }
        if (!r.ok) throw new Error(j.error || ("요청 실패 (" + r.status + ")"));
        return j;
      });
    });
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  /* ── 메인 화면: 담보대출·우리사주 금융 수요 리드 레이더 ── */
  var leadsState = { data: null, sub: "all" };

  function leadKpiHTML(items) {
    return items.map(function (k) {
      return '<div class="kpi"><div class="k-label">' + k[0] + "</div>" +
        '<div class="k-value">' + k[1] + "</div>" +
        (k[2] ? '<div class="k-sub">' + k[2] + "</div>" : "") + "</div>";
    }).join("");
  }

  function countSince(items, days) {
    var cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - days);
    var cutStr = cutoff.toISOString().slice(0, 10);
    return items.filter(function (it) { return it.date >= cutStr; }).length;
  }

  function renderLeadKpis(d) {
    var all = (d.collateral || []).concat(d.esop || []);
    var todayStr = new Date().toISOString().slice(0, 10);
    document.getElementById("leads-kpis").innerHTML = leadKpiHTML([
      ["오늘 신규 리드", all.filter(function (x) { return x.date === todayStr; }).length + "건",
        "이번 주 " + countSince(all, 7) + "건"],
      ["상속·증여 공시", (d.collateral || []).length + "건", "DART 자동 감지"],
    ]);
  }

  function monthLabel(ym) {
    var parts = ym.split("-");
    return parts[0] + "년 " + Number(parts[1]) + "월";
  }

  function renderEsopKpisAndMonthly(d) {
    var monthly = d.esop_monthly || [];
    var thisMonth = new Date().toISOString().slice(0, 7);
    document.getElementById("leads-esop-month").textContent =
      "— " + monthLabel(thisMonth) + " 기준";

    var cur = monthly.filter(function (m) { return m.month === thisMonth; })[0] || { rights: 0, ipo: 0 };
    document.getElementById("leads-esop-kpis").innerHTML = leadKpiHTML([
      ["유상증자 공시(이번 달)", cur.rights + "건", "이미 상장된 회사"],
      ["IPO 공시(이번 달)", cur.ipo + "건", "상장 전 공모"],
    ]);

    var monthlyBox = document.getElementById("leads-esop-monthly");
    if (!monthly.length) {
      monthlyBox.innerHTML = "";
    } else {
      monthlyBox.innerHTML = '<div class="esop-monthly">' + monthly.map(function (m) {
        return '<div class="esop-month-row"><span class="esop-month-label">' + monthLabel(m.month) + "</span>" +
          '<span class="esop-month-count">유상증자 ' + m.rights + "건 · IPO " + m.ipo + "건</span></div>";
      }).join("") + "</div>";
    }
  }

  function collateralRowHTML(it) {
    return (
      '<a class="lead-row" href="' + esc(it.url) + '" target="_blank" rel="noopener">' +
        '<div class="lead-row-head">' +
          '<span class="pg-badge">LEAD</span>' +
          '<span class="lead-title">' + esc(it.name) + " — " + esc(it.reporter || it.reason) + "</span>" +
          '<span class="lead-date">' + esc(it.date) + "</span>" +
        "</div>" +
        '<div class="lead-note">💡 해설: ' + esc(it.note) + "</div>" +
      "</a>"
    );
  }

  function esopRowHTML(it) {
    var tag = it.category === "ipo" ? "IPO" : "유상증자";
    return (
      '<a class="lead-row" href="' + esc(it.url) + '" target="_blank" rel="noopener">' +
        '<div class="lead-row-head">' +
          '<span class="pg-badge">' + tag + "</span>" +
          '<span class="lead-title">' + esc(it.name) + " — " + esc(it.title) + "</span>" +
          '<span class="lead-date">' + esc(it.date) + "</span>" +
        "</div>" +
        '<div class="lead-note">💡 해설: ' + esc(it.note) + "</div>" +
      "</a>"
    );
  }

  function renderLeadLists() {
    var d = leadsState.data;
    if (!d) return;
    var sub = leadsState.sub;
    var collateral = (d.collateral || []).filter(function () { return sub === "all" || sub === "inherit"; });
    var showEsop = sub === "all" || sub === "esop";
    document.getElementById("leads-esop-block").hidden = !showEsop;
    document.getElementById("leads-news-block").hidden = sub === "esop";

    var colList = document.getElementById("leads-collateral-list");
    if (sub === "esop") {
      colList.innerHTML = "";
    } else if (!collateral.length) {
      colList.innerHTML = '<div class="page-note">최근 60일 내 해당 공시가 없습니다.</div>';
    } else {
      colList.innerHTML = collateral.map(collateralRowHTML).join("");
    }

    if (showEsop) {
      var esop = d.esop || [];
      document.getElementById("leads-esop-list").innerHTML = esop.length
        ? esop.map(esopRowHTML).join("")
        : '<div class="page-note">최근 60일 내 유상증자·IPO 공시가 없습니다.</div>';
    }
  }

  var leadsLoaded = false;
  function loadLeads() {
    if (leadsLoaded) return;
    leadsLoaded = true;
    get("/api/credit/leads").then(function (d) {
      leadsState.data = d;
      if (d.pending) {
        document.getElementById("leads-kpis").innerHTML = "";
        document.getElementById("leads-collateral-list").innerHTML =
          '<div class="page-note">코스피 전 종목 데이터를 처음 수집하는 중입니다. 잠시 후 새로고침해주세요.</div>';
        document.getElementById("leads-esop-list").innerHTML = "";
        document.getElementById("leads-scope-note").textContent = "";
        leadsLoaded = false;             // pending 이면 나중에 다시 불러올 수 있게
        return;
      }
      renderLeadKpis(d);
      renderEsopKpisAndMonthly(d);
      renderLeadLists();
      document.getElementById("leads-scope-note").textContent =
        "대상 범위: 상속·증여 리드는 코스피 전체 상장종목(" + (d.universe || 0) + "종목) · " +
        "우리사주 리드는 전 시장(유상증자) + 상장 전 IPO 공모 공시 포함 · DART 전자공시 실데이터 기준, 매일 1회 갱신" +
        (d.stale ? " · 최신 수집이 진행 중이라 이전 결과를 보여주고 있습니다" : "");
    }).catch(function (e) {
      leadsLoaded = false;
      document.getElementById("leads-collateral-list").innerHTML =
        '<div class="chart-error">' + (e.message || "리드 데이터를 불러오지 못했습니다") + "</div>";
      document.getElementById("leads-esop-list").innerHTML = "";
    });
  }

  /* ── 상속·증여 관련 뉴스 동향(참고용, AI 관련도 판단) ── */
  function newsRowHTML(it) {
    return (
      '<a class="lead-row" href="' + esc(it.url || "#") + '" target="_blank" rel="noopener">' +
        '<div class="lead-row-head">' +
          '<span class="pg-badge">뉴스</span>' +
          '<span class="lead-title">' + esc(it.title) + "</span>" +
          '<span class="lead-date">' + esc(it.published || "") + "</span>" +
        "</div>" +
        '<div class="lead-note">🤖 AI 판단: ' + esc(it.ai_note) + "</div>" +
      "</a>"
    );
  }

  function loadInheritNews() {
    get("/api/credit/inherit-news").then(function (d) {
      var items = d.items || [];
      document.getElementById("leads-news-list").innerHTML = items.length
        ? items.map(newsRowHTML).join("")
        : '<div class="page-note">최근 관련 있다고 판단된 뉴스가 없습니다.</div>';
    }).catch(function () {
      document.getElementById("leads-news-list").innerHTML =
        '<div class="page-note">뉴스 동향을 불러오지 못했습니다.</div>';
    });
  }

  function creditTabVisible() {
    var p = document.querySelector('.tab-panel[data-panel="credit"]');
    return p && !p.hidden;
  }
  var newsLoaded = false;
  function maybeLoadLeads() {
    if (!creditTabVisible()) return;
    loadLeads();
    if (!newsLoaded) { newsLoaded = true; loadInheritNews(); }
  }

  function initLeadsSubtabs() {
    var bar = document.getElementById("leads-subtabs");
    if (!bar) return;
    bar.addEventListener("click", function (e) {
      var btn = e.target.closest(".subtab-btn");
      if (!btn) return;
      bar.querySelectorAll(".subtab-btn").forEach(function (b) { b.classList.toggle("active", b === btn); });
      leadsState.sub = btn.dataset.sub;
      renderLeadLists();
    });
  }

  function boot() {
    var root = document.getElementById("credit-root");
    if (!root) return;
    initLeadsSubtabs();
    maybeLoadLeads();
    var mainTabs = document.getElementById("main-tabs");
    if (mainTabs) mainTabs.addEventListener("click", function () { setTimeout(maybeLoadLeads, 0); });
    var workTabs = document.getElementById("work-subtabs");
    if (workTabs) workTabs.addEventListener("click", function () { setTimeout(maybeLoadLeads, 0); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
