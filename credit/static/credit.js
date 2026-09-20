/* 여신·심사 탭 메인 화면: 담보대출·우리사주 금융 수요 리드 레이더(DART 실데이터) +
   상속·증여 관련 뉴스 동향(참고용, AI 관련도 판단) + AI 브리핑. 종목별 기업분석/공시/
   리포트 조회는 전사위젯 > 내 위젯의 개별 위젯에서 제공한다(이 탭에서는 제공하지 않음).

   탭 구성:
     전체     — 요약 KPI 4개 + AI 브리핑 2개(담보대출 수요 레이더 / 우리사주 금융 수요)
     상속·증여 — DART 리드 + 관련 뉴스를 날짜순으로 합친 상세 목록
     우리사주  — 유상증자·IPO 상세 목록 + 월별 집계 */
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

  var leadsState = { data: null };
  var newsState = { items: null };
  var briefState = { data: null };

  function leadKpiHTML(items) {
    return items.map(function (k) {
      return '<div class="kpi"><div class="k-label">' + k[0] + "</div>" +
        '<div class="k-value">' + k[1] + "</div>" +
        (k[2] ? '<div class="k-sub">' + k[2] + "</div>" : "") + "</div>";
    }).join("");
  }

  function monthLabel(ym) {
    var parts = ym.split("-");
    return parts[0] + "년 " + Number(parts[1]) + "월";
  }

  function refDateInfo() {
    var d = leadsState.data;
    if (!d) return null;
    var dates = (d.collateral || []).map(function (x) { return x.date; })
      .concat((d.esop || []).map(function (x) { return x.date; }))
      .concat((newsState.items || []).map(function (n) { return n.published; }))
      .filter(Boolean);
    if (!dates.length) return null;
    var refDate = dates.reduce(function (a, b) { return b > a ? b : a; });
    return { refDate: refDate, refMonth: refDate.slice(0, 7) };
  }

  /* ── 전체: 요약 KPI 4개 ── */
  function renderTopKpis() {
    var d = leadsState.data;
    if (!d || d.pending || newsState.items === null) return;   // 리드·뉴스 둘 다 응답한 뒤에 계산
    var ref = refDateInfo();
    var refDate = ref ? ref.refDate : new Date().toISOString().slice(0, 10);
    var refMonth = ref ? ref.refMonth : new Date().toISOString().slice(0, 7);

    document.getElementById("leads-asof").textContent =
      refDate + " 기준 (DART·뉴스에 실제로 올라온 최신 날짜 — 비영업일이면 자동으로 전 영업일)";

    var newsItems = newsState.items || [];
    var allDated = (d.collateral || []).concat(d.esop || [])
      .concat(newsItems.map(function (n) { return { date: n.published }; }));
    var weekCutoff = new Date(refDate + "T00:00:00");
    weekCutoff.setDate(weekCutoff.getDate() - 6);
    var weekCutStr = weekCutoff.toISOString().slice(0, 10);

    var todayCount = allDated.filter(function (x) { return x.date === refDate; }).length;
    var weekCount = allDated.filter(function (x) { return x.date >= weekCutStr && x.date <= refDate; }).length;

    var inMonth = function (x) { return (x.date || "").slice(0, 7) === refMonth; };
    var inheritMonthly = (d.collateral || []).filter(inMonth).length + newsItems.filter(inMonth).length;
    var monthly = (d.esop_monthly || []).filter(function (m) { return m.month === refMonth; })[0] || { rights: 0, ipo: 0 };

    document.getElementById("leads-kpis").innerHTML = leadKpiHTML([
      ["오늘 신규 리드", todayCount + "건", "최근 7일 " + weekCount + "건 · DART+뉴스"],
      ["상속·증여 공시·뉴스(" + monthLabel(refMonth) + ")", inheritMonthly + "건", "DART + AI 뉴스 분석"],
      ["우리사주 금융 수요(" + monthLabel(refMonth) + ")", monthly.rights + "건", "유상증자 · 이미 상장된 회사"],
      ["우리사주 금융 IPO(" + monthLabel(refMonth) + ")", monthly.ipo + "건", "상장 전 공모"],
    ]);

    renderEsopKpisAndMonthly(d, refMonth);
  }

  /* ── AI 브리핑(담보대출 수요 레이더 / 우리사주 금융 수요) ── */
  function bulletsHTML(bullets) {
    if (!bullets || !bullets.length) {
      return '<div class="page-note">브리핑을 아직 생성하지 못했습니다.</div>';
    }
    return '<ul class="gal-mini-bullets">' + bullets.map(function (b) {
      return "<li>" + esc(b) + "</li>";
    }).join("") + "</ul>";
  }

  function loadBriefings() {
    get("/api/credit/lead-briefings").then(function (d) {
      briefState.data = d;
      document.getElementById("leads-collateral-brief").innerHTML = bulletsHTML(d.collateral_briefing);
      document.getElementById("leads-esop-brief").innerHTML = bulletsHTML(d.esop_briefing);
    }).catch(function () {
      document.getElementById("leads-collateral-brief").innerHTML =
        '<div class="page-note">브리핑을 불러오지 못했습니다.</div>';
      document.getElementById("leads-esop-brief").innerHTML =
        '<div class="page-note">브리핑을 불러오지 못했습니다.</div>';
    });
  }

  /* ── 상속·증여 상세: DART 리드 + 뉴스를 날짜순으로 합침 ── */
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

  function renderInheritList() {
    var d = leadsState.data;
    if (!d || newsState.items === null) return;
    var collateral = (d.collateral || []).map(function (it) { return { date: it.date, html: collateralRowHTML(it) }; });
    var news = (newsState.items || []).map(function (n) { return { date: n.published, html: newsRowHTML(n) }; });
    var rows = collateral.concat(news).sort(function (a, b) { return a.date < b.date ? 1 : (a.date > b.date ? -1 : 0); });
    document.getElementById("leads-inherit-list").innerHTML = rows.length
      ? rows.map(function (r) { return r.html; }).join("")
      : '<div class="page-note">최근 60일 내 해당 공시·뉴스가 없습니다.</div>';
  }

  /* ── 우리사주 상세: 유상증자·IPO ── */
  function renderEsopKpisAndMonthly(d, refMonth) {
    var monthly = d.esop_monthly || [];
    document.getElementById("leads-esop-month").textContent = "— " + monthLabel(refMonth) + " 기준";

    var cur = monthly.filter(function (m) { return m.month === refMonth; })[0] || { rights: 0, ipo: 0 };
    document.getElementById("leads-esop-kpis").innerHTML = leadKpiHTML([
      ["유상증자 공시(" + monthLabel(refMonth) + ")", cur.rights + "건", "이미 상장된 회사"],
      ["IPO 공시(" + monthLabel(refMonth) + ")", cur.ipo + "건", "상장 전 공모"],
    ]);

    var monthlyBox = document.getElementById("leads-esop-monthly");
    monthlyBox.innerHTML = !monthly.length ? "" : '<div class="esop-monthly">' + monthly.map(function (m) {
      return '<div class="esop-month-row"><span class="esop-month-label">' + monthLabel(m.month) + "</span>" +
        '<span class="esop-month-count">유상증자 ' + m.rights + "건 · IPO " + m.ipo + "건</span></div>";
    }).join("") + "</div>";
  }

  function esopRowHTML(it) {
    var isIpo = it.category === "ipo";
    return (
      '<a class="lead-row" href="' + esc(it.url) + '" target="_blank" rel="noopener">' +
        '<div class="lead-row-head">' +
          '<span class="pg-badge' + (isIpo ? " badge-ipo" : "") + '">' + (isIpo ? "IPO" : "유상증자") + "</span>" +
          '<span class="lead-title">' + esc(it.name) + " — " + esc(it.title) + "</span>" +
          '<span class="lead-date">' + esc(it.date) + "</span>" +
        "</div>" +
        '<div class="lead-note">💡 해설: ' + esc(it.note) + "</div>" +
      "</a>"
    );
  }

  function renderEsopList() {
    var d = leadsState.data;
    if (!d) return;
    var esop = d.esop || [];
    document.getElementById("leads-esop-list").innerHTML = esop.length
      ? esop.map(esopRowHTML).join("")
      : '<div class="page-note">최근 60일 내 유상증자·IPO 공시가 없습니다.</div>';
  }

  var leadsLoaded = false;
  function loadLeads() {
    if (leadsLoaded) return;
    leadsLoaded = true;
    get("/api/credit/leads").then(function (d) {
      leadsState.data = d;
      if (d.pending) {
        document.getElementById("leads-kpis").innerHTML = "";
        document.getElementById("leads-asof").textContent = "";
        document.getElementById("leads-inherit-list").innerHTML =
          '<div class="page-note">코스피·코스닥 전 종목 데이터를 처음 수집하는 중입니다. 잠시 후 새로고침해주세요.</div>';
        document.getElementById("leads-esop-list").innerHTML = "";
        document.getElementById("leads-scope-note").textContent = "";
        leadsLoaded = false;             // pending 이면 나중에 다시 불러올 수 있게
        return;
      }
      renderTopKpis();
      renderInheritList();
      renderEsopList();
      document.getElementById("leads-scope-note").textContent =
        "대상 범위: 상속·증여 리드는 코스피·코스닥 전체 상장종목(" + (d.universe || 0) + "종목) · " +
        "우리사주 리드는 전 시장(유상증자) + 상장 전 IPO 공모 공시 포함 · DART 전자공시 실데이터 기준, 매일 1회 갱신" +
        (d.stale ? " · 최신 수집이 진행 중이라 이전 결과를 보여주고 있습니다" : "");
    }).catch(function (e) {
      leadsLoaded = false;
      document.getElementById("leads-inherit-list").innerHTML =
        '<div class="chart-error">' + (e.message || "리드 데이터를 불러오지 못했습니다") + "</div>";
      document.getElementById("leads-esop-list").innerHTML = "";
    });
  }

  function loadInheritNews() {
    get("/api/credit/inherit-news").then(function (d) {
      newsState.items = d.items || [];
      renderTopKpis();
      renderInheritList();
    }).catch(function () {
      newsState.items = [];              // 실패해도 KPI·리스트 계산은 진행되게
      renderTopKpis();
      renderInheritList();
    });
  }

  function creditTabVisible() {
    var p = document.querySelector('.tab-panel[data-panel="credit"]');
    return p && !p.hidden;
  }
  var newsLoaded = false, briefLoaded = false;
  function maybeLoadLeads() {
    if (!creditTabVisible()) return;
    loadLeads();
    if (!newsLoaded) { newsLoaded = true; loadInheritNews(); }
    if (!briefLoaded) { briefLoaded = true; loadBriefings(); }
  }

  function selectSub(sub) {
    var bar = document.getElementById("leads-subtabs");
    if (bar) {
      bar.querySelectorAll(".subtab-btn").forEach(function (b) {
        b.classList.toggle("active", b.dataset.sub === sub);
      });
    }
    document.querySelectorAll(".leads-panel").forEach(function (p) {
      p.hidden = p.dataset.panel !== sub;
    });
  }

  function initLeadsSubtabs() {
    var bar = document.getElementById("leads-subtabs");
    if (!bar) return;
    bar.addEventListener("click", function (e) {
      var btn = e.target.closest(".subtab-btn");
      if (btn) selectSub(btn.dataset.sub);
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
