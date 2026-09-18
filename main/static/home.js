/* 홈 대시보드 · 전사 위젯 · 개인 위젯
 * 위젯 "선택"은 로그인 없이 이 브라우저(localStorage)에만 저장한다(PoC 범위). */
(function () {
  "use strict";

  var CIRCLED = ["①", "②", "③", "④", "⑤", "⑥"];

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
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

  // ── 전사 갤러리 카탈로그(= 업무별 화면의 주요 섹션 단위) ──
  var WIDGET_CATALOG = [
    { id: "capital-liquidity", tab: "capital", title: "증시자금·유동성", emoji: "📈",
      desc: "투자자예탁금·신용공여·CMA 잔고 및 추이", status: "live" },
    { id: "capital-cma", tab: "capital", title: "CMA·단기수신", emoji: "💰",
      desc: "CMA 유형별 비중, 증권사별 금리 비교", status: "live" },
    { id: "capital-issuance", tab: "capital", title: "발행시장", emoji: "🏗️",
      desc: "IPO·유상증자 캘린더 + AI 브리핑", status: "live" },
    { id: "policy-briefing", tab: "policy", title: "정책·규제 브리핑", emoji: "📜",
      desc: "금융당국·유관기관 보도자료 + AI 3줄 요약", status: "live" },
    { id: "research-briefing", tab: "research", title: "리서치·뉴스 브리핑", emoji: "📰",
      desc: "업무 관련 기사 AI 선별·태깅 + 요약", status: "live" },
    { id: "credit-analysis", tab: "credit", title: "기업분석", emoji: "🏦",
      desc: "종목 기초정보·가격범위·재무요약·실적분석", status: "live" },
    { id: "credit-filing", tab: "credit", title: "공시", emoji: "🗂️",
      desc: "종목별 DART 공시 목록", status: "live" },
    { id: "credit-report", tab: "credit", title: "증권사 리포트", emoji: "📊",
      desc: "당해 연도 리포트 + 목표주가 컨센서스", status: "live" },
    { id: "ib-deals", tab: "ib", title: "투자금융", emoji: "💼",
      desc: "IB·인수·발행시장 동향", status: "soon" },
    { id: "custody-status", tab: "custody", title: "수탁", emoji: "🔐",
      desc: "신탁·수탁고 및 자산관리 지표", status: "soon" },
    { id: "funding-fx", tab: "funding", title: "자금·외화", emoji: "💱",
      desc: "조달·운용·외화 유동성", status: "soon" },
    { id: "lending-stock", tab: "lending", title: "증권대차", emoji: "🔄",
      desc: "대차잔고·공매도·이용률", status: "soon" }
  ];
  var STATUS_LABEL = { live: "전사 등재", dept: "부서 검증중", soon: "준비중" };
  var STATUS_CLASS = { live: "st-live", dept: "st-dept", soon: "st-soon" };

  // "부서 위젯" 배지 — 업무별 화면에 실제로 구현된(=live) 위젯에는 "전사 등재" 옆에
  // 함께 표시해, 원래 부서 업무 화면에서 만들어졌다는 출처를 나타낸다.
  function statusBadgesHTML(w) {
    var deptBadge = w.status === "live" ? '<span class="gal-status st-deptw">부서 위젯</span>' : "";
    return deptBadge + '<span class="gal-status ' + STATUS_CLASS[w.status] + '">' + STATUS_LABEL[w.status] + "</span>";
  }

  // ── localStorage: 내가 고른 위젯(기기별) ──
  var LS_KEY = "myWidgets";
  function getMyWidgetIds() {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || "[]"); } catch (e) { return []; }
  }
  function toggleMyWidget(id) {
    var ids = getMyWidgetIds();
    var i = ids.indexOf(id);
    if (i >= 0) ids.splice(i, 1); else ids.push(id);
    try { localStorage.setItem(LS_KEY, JSON.stringify(ids)); } catch (e) {}
    return ids;
  }

  function goWork(tab) {
    if (window.AppNav) window.AppNav.go("work", tab);
  }

  // ── 갤러리 카드 ──
  function galCardHTML(w) {
    var mine = getMyWidgetIds().indexOf(w.id) >= 0;
    return (
      '<div class="gal-card">' +
        '<div class="gal-top">' +
          '<span class="gal-emoji">' + w.emoji + "</span>" +
          '<span class="gal-badges">' + statusBadgesHTML(w) + "</span>" +
        "</div>" +
        '<div class="gal-title">' + esc(w.title) + "</div>" +
        '<div class="gal-desc">' + esc(w.desc) + "</div>" +
        '<div class="gal-actions">' +
          '<button type="button" class="dart-btn gal-open" data-work="' + w.tab + '">화면 열기 →</button>' +
          '<button type="button" class="gal-toggle' + (mine ? " active" : "") + '" data-id="' + w.id + '">' +
            (mine ? "✓ 내 위젯에 추가됨" : "+ 내 위젯에 추가") +
          "</button>" +
        "</div>" +
      "</div>"
    );
  }

  function bindGalleryCardEvents(scope) {
    scope.querySelectorAll(".gal-open").forEach(function (btn) {
      btn.addEventListener("click", function () { goWork(btn.dataset.work); });
    });
    scope.querySelectorAll(".gal-toggle").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var ids = toggleMyWidget(btn.dataset.id);
        var mine = ids.indexOf(btn.dataset.id) >= 0;
        btn.classList.toggle("active", mine);
        btn.textContent = mine ? "✓ 내 위젯에 추가됨" : "+ 내 위젯에 추가";
      });
    });
  }

  function renderGallery() {
    var box = document.getElementById("gallery-grid");
    if (!box) return;
    var items = WIDGET_CATALOG.filter(function (w) { return w.status !== "soon"; });
    box.innerHTML = items.map(galCardHTML).join("");
    bindGalleryCardEvents(box);
  }

  function renderPersonal() {
    var box = document.getElementById("personal-grid");
    if (!box) return;
    var ids = getMyWidgetIds();
    var items = WIDGET_CATALOG.filter(function (w) { return ids.indexOf(w.id) >= 0; });
    if (!items.length) {
      box.innerHTML =
        '<div class="page-note home-empty-widgets">전사 위젯에서 추가하면 여기에 표시됩니다.<br>' +
        '<button type="button" class="dart-btn" id="personal-go-gallery">전사 위젯 가기 →</button></div>';
      var gbtn = document.getElementById("personal-go-gallery");
      if (gbtn) gbtn.addEventListener("click", function () { if (window.AppNav) window.AppNav.go("gallery"); });
      return;
    }
    box.innerHTML = items.map(galCardHTML).join("");
    bindGalleryCardEvents(box);
  }

  // ── 홈 대시보드: 통합 브리핑 + 알림 ──
  function bulletsFromBriefing(b) {
    if (!b) return [];
    var arr = Array.isArray(b) ? b.slice() : String(b).split("\n");
    return arr.map(function (l) { return l.replace(/^\s*[-•*]\s*/, "").trim(); })
      .filter(Boolean).slice(0, 3);
  }

  function briefCardHTML(opts) {
    var head =
      '<div class="brief-head"><span class="brief-label">' + opts.label + "</span>" +
      '<span class="brief-when">' + esc(opts.when || "") + "</span></div>";
    var body;
    if (opts.bullets && opts.bullets.length) {
      body = '<ol class="brief-list">' +
        opts.bullets.map(function (b, i) {
          return '<li><span class="bl-no">' + (CIRCLED[i] || (i + 1)) + '</span><span class="bl-tx">' +
            esc(b) + "</span></li>";
        }).join("") + "</ol>";
    } else {
      body = '<div class="brief-note">' + esc(opts.note || "표시할 브리핑이 없습니다.") + "</div>";
    }
    return (
      '<div class="brief-card home-brief">' + head + body +
        '<button type="button" class="dart-btn home-brief-more" data-work="' + opts.tab + '">자세히 보기 →</button>' +
      "</div>"
    );
  }

  function renderAlerts(alerts) {
    var box = document.getElementById("home-alerts");
    if (!box) return;
    if (!alerts || !alerts.length) {
      box.innerHTML = '<div class="page-note">현재 등록된 이상징후 알림이 없습니다.</div>';
      return;
    }
    box.innerHTML = alerts.map(function (a) {
      return (
        '<div class="home-alert ' + (a.level === "warn" ? "al-warn" : "al-info") + '">' +
          '<div class="al-title">⚠️ ' + esc(a.title) + "</div>" +
          '<div class="al-detail">' + esc(a.detail) + "</div>" +
          '<button type="button" class="dart-btn home-brief-more" data-work="' + a.tab + '">확인하러 가기 →</button>' +
        "</div>"
      );
    }).join("");
    bindGoWorkButtons(box);
  }

  function bindGoWorkButtons(scope) {
    scope.querySelectorAll("[data-work]").forEach(function (btn) {
      btn.addEventListener("click", function () { goWork(btn.dataset.work); });
    });
  }

  var briefingLoaded = false;
  function ensureBriefing() {
    if (briefingLoaded) return;
    briefingLoaded = true;
    var briefBox = document.getElementById("home-briefs");
    get("/api/home/summary").then(function (d) {
      var cards = "";
      if (d.policy) {
        cards += briefCardHTML({
          label: "📜 정책·규제", when: (d.policy.as_of || "") + " 기준",
          bullets: bulletsFromBriefing(d.policy.briefing), note: d.policy.briefing_note, tab: "policy"
        });
      }
      if (d.research) {
        cards += briefCardHTML({
          label: "📰 리서치·뉴스", when: (d.research.date || "") + " · " + (d.research.count || 0) + "건 선별",
          bullets: bulletsFromBriefing(d.research.briefing), note: d.research.briefing_note, tab: "research"
        });
      }
      briefBox.innerHTML = cards || '<div class="page-note">브리핑을 불러오지 못했습니다.</div>';
      bindGoWorkButtons(briefBox);
      renderAlerts(d.alerts);
    }).catch(function (e) {
      briefBox.innerHTML = '<div class="chart-error">' + esc(e.message) + "</div>";
      renderAlerts([]);
      briefingLoaded = false; // 재방문 시 재시도
    });
  }

  window.HomeDashboard = {
    enterHome: function () { ensureBriefing(); },
    enterGallery: function () { renderGallery(); },
    enterPersonal: function () { renderPersonal(); }
  };
})();
