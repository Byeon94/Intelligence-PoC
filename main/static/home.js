/* 홈 대시보드 · 전사 위젯 · 내 위젯
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
  // sub: 자본시장처럼 내부에 세부탭이 있는 화면일 때, 그 세부탭까지 바로 이동시키기 위한 힌트.
  var WIDGET_CATALOG = [
    { id: "capital-liquidity", tab: "capital", sub: "liquidity", title: "증시자금·유동성", emoji: "📈",
      desc: "투자자예탁금·신용공여·CMA 잔고 및 추이", status: "live" },
    { id: "capital-cma", tab: "capital", sub: "cma", title: "CMA·단기수신", emoji: "💰",
      desc: "CMA 유형별 비중, 증권사별 금리 비교", status: "live" },
    { id: "capital-issuance", tab: "capital", sub: "issuance", title: "발행시장", emoji: "🏗️",
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

  function goWork(tab, sub) {
    if (window.AppNav) window.AppNav.go("work", tab);
    if (sub && tab === "capital" && window.CapitalNav) window.CapitalNav.goSub(sub);
    // 각 업무 모듈(정책·규제/리서치·뉴스 등)은 #work-subtabs 클릭을 감지해 처음 한 번
    // 데이터를 지연 로딩한다. 홈/전사 위젯에서 곧장 이동할 때도 그 로딩이 걸리도록
    // 같은 이벤트를 한 번 흉내 낸다.
    var bar = document.getElementById("work-subtabs");
    if (bar) bar.dispatchEvent(new Event("click", { bubbles: true }));
  }

  // ── 미니 값 표시(내 위젯 전용) — 위젯마다 가벼운 실데이터를 카드 안에 바로 보여준다 ──
  function jo(v) { return v == null ? "-" : (Math.round(v * 10) / 10) + "조"; }
  function miniRow(pairs) {
    return '<div class="gal-mini-row">' + pairs.map(function (p) {
      return '<div class="gal-mini-item"><span class="gmi-label">' + esc(p[0]) + '</span>' +
        '<span class="gmi-value">' + esc(String(p[1])) + '</span></div>';
    }).join("") + "</div>";
  }
  function miniBullets(bullets, note) {
    if (!bullets || !bullets.length) {
      return '<div class="gal-mini-note">' + esc(note || "표시할 내용이 없습니다.") + "</div>";
    }
    return '<ul class="gal-mini-bullets">' + bullets.slice(0, 2).map(function (b) {
      return "<li>" + esc(b) + "</li>";
    }).join("") + "</ul>";
  }

  // 각 로더는 자신의 미리보기 영역(el)을 직접 채운다(el) => Promise.
  var MINI_LOADERS = {
    "capital-liquidity": function (el) {
      return get("/api/capital/liquidity/summary").then(function (d) {
        var it = d.items || {};
        el.innerHTML = miniRow([
          ["예탁금", jo(it.investor_deposits && it.investor_deposits.value)],
          ["신용공여", jo(it.credit_balance && it.credit_balance.value)],
          ["CMA", jo(it.cma_balance && it.cma_balance.value)]
        ]) + '<div class="gal-mini-chart" id="' + el.id + '-chart"></div>';
        return get("/api/capital/liquidity/trend").then(function (t) {
          var chartEl = document.getElementById(el.id + "-chart");
          if (!chartEl || !window.Charts) return;
          var n = 12; // 최근 1년만 (카드 공간이 작아 전체 24개월은 과함)
          window.Charts.line(chartEl, {
            labels: (t.labels || []).slice(-n),
            series: [
              { name: "예탁금", values: (t.series.investor_deposits || []).slice(-n), varName: "--c1" },
              { name: "신용공여", values: (t.series.credit_balance || []).slice(-n), varName: "--c2" },
              { name: "CMA", values: (t.series.cma_balance || []).slice(-n), varName: "--c3" }
            ]
          });
        });
      });
    },
    "capital-cma": function (el) {
      return get("/api/capital/cma/summary").then(function (d) {
        var it = d.items || {};
        el.innerHTML = miniRow([
          ["총잔고", jo(it.total && it.total.value)],
          ["RP형", jo(it.rp && it.rp.value)],
          ["발행어음형", jo(it.note && it.note.value)]
        ]);
      });
    },
    "capital-issuance": function (el) {
      return get("/api/issuance/digest").then(function (d) {
        var c = d.counts || {};
        el.innerHTML = miniRow([
          ["수요예측", c["수요예측"] || 0],
          ["청약", c["청약"] || 0],
          ["상장", c["상장"] || 0],
          ["유상증자", c["유상증자"] || 0]
        ]) + miniBullets(bulletsFromBriefing(d.briefing), d.briefing_note);
      });
    },
    "policy-briefing": function (el) {
      return get("/api/policy/digest").then(function (d) {
        el.innerHTML = miniBullets(bulletsFromBriefing(d.briefing), d.briefing_note);
      });
    },
    "research-briefing": function (el) {
      return get("/api/research/digest").then(function (d) {
        el.innerHTML = miniBullets(bulletsFromBriefing(d.briefing), d.briefing_note);
      });
    }
  };

  function loadMiniPreviews(items) {
    items.forEach(function (w) {
      var loader = MINI_LOADERS[w.id];
      var el = document.getElementById("mini-" + w.id);
      if (!loader || !el) return;
      loader(el).catch(function () {
        el.innerHTML = '<div class="gal-mini-note">불러오지 못했습니다.</div>';
      });
    });
  }

  // ── 카드(전사 위젯 / 내 위젯 공용) ──
  // opts.mini: 내 위젯 전용 — 있으면 실데이터 미리보기 영역을 넣고 "내 위젯에 추가" 토글은 뺀다.
  function galCardHTML(w, opts) {
    opts = opts || {};
    var mine = getMyWidgetIds().indexOf(w.id) >= 0;
    var miniHTML = (opts.mini && MINI_LOADERS[w.id])
      ? '<div class="gal-mini" id="mini-' + w.id + '"><span class="page-note">불러오는 중…</span></div>'
      : "";
    var toggleHTML = opts.mini ? "" :
      '<button type="button" class="gal-toggle' + (mine ? " active" : "") + '" data-id="' + w.id + '">' +
        (mine ? "✓ 내 위젯에 추가됨" : "+ 내 위젯에 추가") +
      "</button>";
    return (
      '<div class="gal-card">' +
        '<div class="gal-top">' +
          '<span class="gal-emoji">' + w.emoji + "</span>" +
          '<span class="gal-badges">' + statusBadgesHTML(w) + "</span>" +
        "</div>" +
        '<div class="gal-title">' + esc(w.title) + "</div>" +
        '<div class="gal-desc">' + esc(w.desc) + "</div>" +
        miniHTML +
        '<div class="gal-actions">' +
          '<button type="button" class="dart-btn gal-open" data-work="' + w.tab + '"' +
            (w.sub ? ' data-sub="' + w.sub + '"' : "") + '>화면 열기 →</button>' +
          toggleHTML +
        "</div>" +
      "</div>"
    );
  }

  function bindGalleryCardEvents(scope) {
    scope.querySelectorAll(".gal-open").forEach(function (btn) {
      btn.addEventListener("click", function () { goWork(btn.dataset.work, btn.dataset.sub); });
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

  // 홈 대시보드에서 이미 통합 브리핑으로 제공하는 위젯은 전사 위젯 목록에서는 뺀다
  // (이미 내 위젯에 추가돼 있는 경우는 그대로 유지됨).
  var HIDDEN_FROM_GALLERY = ["policy-briefing", "research-briefing"];

  function renderGallery() {
    var box = document.getElementById("gallery-grid");
    if (!box) return;
    var items = WIDGET_CATALOG.filter(function (w) {
      return w.status !== "soon" && HIDDEN_FROM_GALLERY.indexOf(w.id) < 0;
    });
    box.innerHTML = items.map(function (w) { return galCardHTML(w); }).join("");
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
    box.innerHTML = items.map(function (w) { return galCardHTML(w, { mini: true }); }).join("");
    bindGalleryCardEvents(box);
    loadMiniPreviews(items);
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
          '<button type="button" class="dart-btn home-brief-more" data-work="' + a.tab + '"' +
            (a.sub ? ' data-sub="' + a.sub + '"' : "") + '>확인하러 가기 →</button>' +
        "</div>"
      );
    }).join("");
    bindGoWorkButtons(box);
  }

  function bindGoWorkButtons(scope) {
    scope.querySelectorAll("[data-work]").forEach(function (btn) {
      btn.addEventListener("click", function () { goWork(btn.dataset.work, btn.dataset.sub); });
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
