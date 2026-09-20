/* 여신·심사 탭 메인 화면: 증권담보대출·우리사주 금융 수요 리드 레이더(DART 실데이터) +
   상속·증여/우리사주 관련 뉴스 동향(참고용, AI 관련도 판단) + AI 브리핑. 종목별 기업분석/공시/
   리포트 조회는 전사위젯 > 내 위젯의 개별 위젯에서 제공한다(이 탭에서는 제공하지 않음).

   탭 구성:
     전체     — 요약 KPI 4개 + AI 브리핑 2개(증권담보대출 수요 레이더 / 우리사주 금융 수요),
                브리핑 카드는 홈 대시보드의 "오늘의 AI 통합 브리핑"과 같은 디자인/버튼 사용
     증권담보대출 — DART 공시(상속·증여)와 관련 뉴스를 각각 최대 5개씩 보여주고, 더보기로 전체 펼침 + 월별 집계
     우리사주    — 유상증자·IPO DART 공시와 관련 뉴스를 각각 최대 5개씩 보여주고, 더보기로 전체 펼침 + 월별 집계 */
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
  var esopNewsState = { items: null };
  var briefState = { data: null };
  var CIRCLED = ["①", "②", "③", "④", "⑤", "⑥"];
  var LIST_LIMIT = 5;

  /* ── 목록(더보기) 공통 렌더러: 기본 5개만 보여주고, 더보기를 누르면 전체를 펼친다 ── */
  var expandState = {};
  var rerenderers = {};
  function renderExpandableList(boxId, items, rowFn, emptyMsg, rerender) {
    rerenderers[boxId] = rerender;
    var box = document.getElementById(boxId);
    if (!box) return;
    if (!items.length) { box.innerHTML = '<div class="page-note">' + emptyMsg + "</div>"; return; }
    var expanded = !!expandState[boxId];
    var shown = expanded ? items : items.slice(0, LIST_LIMIT);
    var html = shown.map(rowFn).join("");
    if (items.length > LIST_LIMIT) {
      html += '<button type="button" class="lead-more-btn" data-box="' + boxId + '">' +
        (expanded ? "접기 ▲" : "더보기 (전체 " + items.length + "건) ▼") + "</button>";
    }
    box.innerHTML = html;
  }
  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".lead-more-btn");
    if (!btn) return;
    var boxId = btn.dataset.box;
    expandState[boxId] = !expandState[boxId];
    if (rerenderers[boxId]) rerenderers[boxId]();
  });

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
      .concat((esopNewsState.items || []).map(function (n) { return n.published; }))
      .filter(Boolean);
    if (!dates.length) return null;
    var refDate = dates.reduce(function (a, b) { return b > a ? b : a; });
    return { refDate: refDate, refMonth: refDate.slice(0, 7) };
  }

  /* ── 전체: 요약 KPI 4개 ── */
  function renderTopKpis() {
    var d = leadsState.data;
    if (!d || d.pending || newsState.items === null || esopNewsState.items === null) return;   // 모든 소스가 응답한 뒤에 계산
    var ref = refDateInfo();
    var refDate = ref ? ref.refDate : new Date().toISOString().slice(0, 10);
    var refMonth = ref ? ref.refMonth : new Date().toISOString().slice(0, 7);

    document.getElementById("leads-asof").textContent =
      refDate + " 기준 (DART·뉴스에 실제로 올라온 최신 날짜 — 비영업일이면 자동으로 전 영업일)";

    var newsItems = newsState.items || [];
    var allDated = (d.collateral || []).concat(d.esop || [])
      .concat(newsItems.map(function (n) { return { date: n.published }; }))
      .concat((esopNewsState.items || []).map(function (n) { return { date: n.published }; }));
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
      ["증권담보대출 수요 - 상속증여 공시뉴스(" + monthLabel(refMonth) + ")", inheritMonthly + "건", "DART + AI 뉴스 분석"],
      ["우리사주 수요 - 유상증자(" + monthLabel(refMonth) + ")", monthly.rights + "건", "이미 상장된 회사"],
      ["우리사주 수요 - IPO(" + monthLabel(refMonth) + ")", monthly.ipo + "건", "상장 전 공모"],
    ]);

    renderEsopKpisAndMonthly(d, refMonth);
  }

  /* ── AI 브리핑(증권담보대출 수요 레이더 / 우리사주 금융 수요) — 홈 대시보드의
     "오늘의 AI 통합 브리핑" 카드와 같은 디자인(원형 번호 불릿 + 자세히 보기 버튼) ── */
  function briefCardHTML(opts) {
    var head = '<div class="brief-head"><span class="brief-label">' + opts.label + "</span>" +
      '<span class="brief-when">' + esc(opts.when || "") + "</span></div>";
    var body;
    if (opts.bullets && opts.bullets.length) {
      body = '<ol class="brief-list">' + opts.bullets.map(function (b, i) {
        return '<li><span class="bl-no">' + (CIRCLED[i] || (i + 1)) + '</span><span class="bl-tx">' +
          esc(b) + "</span></li>";
      }).join("") + "</ol>";
    } else {
      body = '<div class="brief-note">브리핑을 아직 생성하지 못했습니다.</div>';
    }
    return (
      '<div class="brief-card">' + head + body +
        '<button type="button" class="dart-btn home-brief-more" data-sub="' + opts.sub + '">자세히 보기 →</button>' +
      "</div>"
    );
  }

  function bindBriefButtons(scope) {
    scope.querySelectorAll(".home-brief-more[data-sub]").forEach(function (btn) {
      btn.addEventListener("click", function () { selectSub(btn.dataset.sub); });
    });
  }

  function loadBriefings() {
    get("/api/credit/lead-briefings").then(function (d) {
      briefState.data = d;
      var colBox = document.getElementById("leads-collateral-brief");
      var esopBox = document.getElementById("leads-esop-brief");
      colBox.innerHTML = briefCardHTML({
        label: "💰 증권담보대출 수요 레이더", when: "AI 브리핑",
        bullets: d.collateral_briefing, sub: "inherit",
      });
      esopBox.innerHTML = briefCardHTML({
        label: "🧑‍🤝‍🧑 우리사주 금융 수요", when: "AI 브리핑",
        bullets: d.esop_briefing, sub: "esop",
      });
      bindBriefButtons(colBox);
      bindBriefButtons(esopBox);
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

  function byDateDesc(a, b) { return (a.date || "") < (b.date || "") ? 1 : ((a.date || "") > (b.date || "") ? -1 : 0); }

  function renderInheritDisclosures() {
    var d = leadsState.data;
    if (!d) return;
    var items = (d.collateral || []).slice().sort(byDateDesc);
    renderExpandableList("leads-inherit-disclosures", items, collateralRowHTML,
      "최근 60일 내 상속·증여 관련 DART 공시가 없습니다.", renderInheritDisclosures);
  }

  function renderInheritNewsList() {
    if (newsState.items === null) return;
    var items = (newsState.items || []).slice()
      .sort(function (a, b) { return (a.published || "") < (b.published || "") ? 1 : -1; });
    renderExpandableList("leads-inherit-news-list", items, newsRowHTML,
      "최근 60일 내 관련 뉴스가 없습니다.", renderInheritNewsList);
  }

  function renderInheritList() {
    var d = leadsState.data;
    if (!d || newsState.items === null) return;
    renderInheritDisclosures();
    renderInheritNewsList();
    renderInheritMonthly();
  }

  // 우리사주(esop_monthly)와 짝을 맞춰, 증권담보대출도 월별로 DART 공시·뉴스 건수를 보여준다.
  function renderInheritMonthly() {
    var d = leadsState.data;
    var box = document.getElementById("leads-inherit-monthly");
    if (!d || newsState.items === null || !box) return;
    var counts = {};
    (d.collateral_monthly || []).forEach(function (m) {
      counts[m.month] = { dart: m.count, news: 0 };
    });
    (newsState.items || []).forEach(function (n) {
      var m = (n.published || "").slice(0, 7);
      if (!m) return;
      counts[m] = counts[m] || { dart: 0, news: 0 };
      counts[m].news++;
    });
    var months = Object.keys(counts).sort().reverse();
    box.innerHTML = !months.length ? "" : '<div class="esop-monthly">' + months.map(function (m) {
      return '<div class="esop-month-row"><span class="esop-month-label">' + monthLabel(m) + "</span>" +
        '<span class="esop-month-count">DART 공시 ' + counts[m].dart + "건 · 관련 뉴스 " + counts[m].news + "건</span></div>";
    }).join("") + "</div>";
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

  function renderEsopDisclosures() {
    var d = leadsState.data;
    if (!d) return;
    var items = (d.esop || []).slice().sort(byDateDesc);
    renderExpandableList("leads-esop-disclosures", items, esopRowHTML,
      "최근 60일 내 유상증자·IPO 공시가 없습니다.", renderEsopDisclosures);
  }

  function renderEsopNewsList() {
    if (esopNewsState.items === null) return;
    var items = (esopNewsState.items || []).slice()
      .sort(function (a, b) { return (a.published || "") < (b.published || "") ? 1 : -1; });
    renderExpandableList("leads-esop-news-list", items, newsRowHTML,
      "최근 60일 내 관련 뉴스가 없습니다.", renderEsopNewsList);
  }

  function renderEsopList() {
    renderEsopDisclosures();
    renderEsopNewsList();
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
        document.getElementById("leads-inherit-disclosures").innerHTML =
          '<div class="page-note">코스피·코스닥 전 종목 데이터를 처음 수집하는 중입니다. 잠시 후 새로고침해주세요.</div>';
        document.getElementById("leads-inherit-news-list").innerHTML = "";
        document.getElementById("leads-esop-disclosures").innerHTML = "";
        document.getElementById("leads-esop-news-list").innerHTML = "";
        document.getElementById("leads-scope-note").textContent = "";
        leadsLoaded = false;             // pending 이면 나중에 다시 불러올 수 있게
        return;
      }
      renderTopKpis();
      renderInheritList();
      renderEsopList();
      document.getElementById("leads-scope-note").textContent =
        "대상 범위: 증권담보대출(상속·증여) 리드는 코스피·코스닥 전체 상장종목(" + (d.universe || 0) + "종목) · " +
        "우리사주 리드는 전 시장(유상증자) + 상장 전 IPO 공모 공시 포함 · DART 전자공시 실데이터 기준, 매일 1회 갱신" +
        (d.stale ? " · 최신 수집이 진행 중이라 이전 결과를 보여주고 있습니다" : "");
    }).catch(function (e) {
      leadsLoaded = false;
      document.getElementById("leads-inherit-disclosures").innerHTML =
        '<div class="chart-error">' + (e.message || "리드 데이터를 불러오지 못했습니다") + "</div>";
      document.getElementById("leads-inherit-news-list").innerHTML = "";
      document.getElementById("leads-esop-disclosures").innerHTML = "";
      document.getElementById("leads-esop-news-list").innerHTML = "";
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

  function loadEsopNews() {
    get("/api/credit/esop-news").then(function (d) {
      esopNewsState.items = d.items || [];
      renderTopKpis();
      renderEsopNewsList();
    }).catch(function () {
      esopNewsState.items = [];          // 실패해도 KPI·리스트 계산은 진행되게
      renderTopKpis();
      renderEsopNewsList();
    });
  }

  function creditTabVisible() {
    var p = document.querySelector('.tab-panel[data-panel="credit"]');
    return p && !p.hidden;
  }
  var newsLoaded = false, esopNewsLoaded = false, briefLoaded = false;
  function maybeLoadLeads() {
    if (!creditTabVisible()) return;
    loadLeads();
    if (!newsLoaded) { newsLoaded = true; loadInheritNews(); }
    if (!esopNewsLoaded) { esopNewsLoaded = true; loadEsopNews(); }
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
