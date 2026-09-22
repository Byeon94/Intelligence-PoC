/* 홈 대시보드 · 전사 위젯 · 내 위젯
 * 위젯 "선택"은 로그인 없이, 이 탭이 열려 있는 동안(메모리)만 유지한다 — 새로고침·재접속하면
 * 초기화된다(PoC 범위, 영속 저장 없음). */
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
    { id: "sector-map", externalUrl: "/sector",
      title: "국내 업종별 시가총액 및 밸류체인", emoji: "🗺️", creditBadge: "투자금융부 이OO 과장 제작",
      desc: "국내 업종별 시가총액 및 대표산업(4가지) 밸류체인", status: "live" },
    { id: "credit-equity-glance", tab: "credit", title: "한눈에 보는 기업분석 정보", emoji: "🔎",
      creditBadge: "투자금융부 박OO 과장 제작",
      desc: "종목명을 입력하면 기업 분석정보 및 공시정보 한눈에 확인", status: "live" },
    { id: "market-reports", externalUrl: "https://consensus.hankyung.com/analysis/list",
      title: "오늘의 증권사 리포트", emoji: "📑", creditBadge: "기획부 유OO 과장 제작",
      desc: "조회 기준일(전영업일) 시장 전체 리포트 건수 + AI 브리핑", status: "live" },
    { id: "it-news", externalUrl: "https://search.naver.com/search.naver?where=news&query=" +
        encodeURIComponent("금융IT 정보보호 생성형AI"),
      title: "오늘의 IT·정보보호 뉴스", emoji: "🖥️", creditBadge: "IT부 변OO 과장 제작",
      desc: "IT·정보보호 관련 참고하기 좋은 뉴스 및 AI 브리핑", status: "live" },
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
  // 홈 "오늘의 알림"에 항상 함께 보여주는 위젯 추천 카드(실데이터 알림이 아닌 고정 안내).
  var WIDGET_RECOMMENDATION = {
    level: "info", icon: "💡",
    title: "[오늘의 위젯 추천] 국내 업종별 시가총액 및 밸류체인 (투자금융부 이OO 과장 제작)",
    tab: "gallery"
  };

  var STATUS_LABEL = { live: "전사 등재", dept: "부서 검증중", soon: "준비중" };
  var STATUS_CLASS = { live: "st-live", dept: "st-dept", soon: "st-soon" };

  // "부서 위젯" 배지 — 업무별 화면에 실제로 구현된(=live) 위젯에는 "전사 등재" 옆에
  // 함께 표시해, 원래 부서 업무 화면에서 만들어졌다는 출처를 나타낸다.
  // creditBadge 가 있는 위젯(예: 특정 부서 담당자가 직접 만든 위젯)은 "부서 위젯" 대신
  // 그 제작 출처를 파란색 배지로 보여준다.
  function statusBadgesHTML(w) {
    var deptBadge = w.creditBadge
      ? '<span class="gal-status st-credit">' + esc(w.creditBadge) + "</span>"
      : (w.status === "live" ? '<span class="gal-status st-deptw">부서 위젯</span>' : "");
    return deptBadge + '<span class="gal-status ' + STATUS_CLASS[w.status] + '">' + STATUS_LABEL[w.status] + "</span>";
  }

  // ── 내가 고른 위젯: 이 탭이 열려 있는 동안만(메모리) 유지 ──
  // 예전엔 localStorage에 저장해 재접속해도 남아 있었으나, 링크로 새로 열 때마다
  // "내 위젯"이 항상 빈 상태로 시작하도록(=재접속 시 지속되지 않도록) 요청에 따라 변경.
  var myWidgetIds = [];
  function getMyWidgetIds() {
    return myWidgetIds.slice();
  }
  function toggleMyWidget(id) {
    var i = myWidgetIds.indexOf(id);
    if (i >= 0) myWidgetIds.splice(i, 1); else myWidgetIds.push(id);
    return myWidgetIds.slice();
  }

  function goWork(tab, sub) {
    if (window.AppNav) window.AppNav.go(tab);
    if (sub && tab === "capital" && window.CapitalNav) window.CapitalNav.goSub(sub);
    // 각 업무 모듈(정책·규제/리서치·뉴스 등)은 #main-tabs 클릭을 감지해 처음 한 번
    // 데이터를 지연 로딩한다. 홈/나의 대시보드에서 곧장 이동할 때도 그 로딩이 걸리도록
    // 같은 이벤트를 한 번 흉내 낸다.
    var bar = document.getElementById("main-tabs");
    if (bar) bar.dispatchEvent(new Event("click", { bubbles: true }));
  }

  // ── 미니 값 표시(내 위젯 전용) — 위젯마다 가벼운 실데이터를 카드 안에 바로 보여준다 ──
  function jo(v) { return v == null ? "-" : (Math.round(v * 10) / 10) + "조"; }
  function asOfLine(asOf) {
    return asOf ? '<div class="gal-mini-asof">' + esc(asOf) + ' 기준</div>' : "";
  }
  function miniSubtitle(t) {
    return '<div class="gal-mini-subtitle">' + esc(t) + "</div>";
  }
  function miniRow(pairs) {
    return '<div class="gal-mini-row">' + pairs.map(function (p) {
      var cls = p[2] ? " " + p[2] : "";
      return '<div class="gal-mini-item"><span class="gmi-label">' + esc(p[0]) + '</span>' +
        '<span class="gmi-value' + cls + '">' + esc(String(p[1])) + '</span></div>';
    }).join("") + "</div>";
  }
  function miniRateTable(rows) {
    if (!rows.length) return '<div class="gal-mini-note">금리 정보가 없습니다.</div>';
    return '<table class="gal-mini-table"><thead><tr><th>증권사</th><th>RP형</th><th>발행어음형</th></tr></thead><tbody>' +
      rows.map(function (r) {
        return "<tr><td>" + esc(r.company) + "</td><td>" +
          (r.rp_rate != null ? r.rp_rate.toFixed(2) + "%" : "-") + "</td><td>" +
          (r.note_rate != null ? r.note_rate.toFixed(2) + "%" : "-") + "</td></tr>";
      }).join("") + "</tbody></table>";
  }
  function thisWeekRange() {
    var now = new Date();
    now.setHours(0, 0, 0, 0);
    var start = new Date(now); start.setDate(now.getDate() - now.getDay());
    var end = new Date(start); end.setDate(start.getDate() + 6);
    return [start, end];
  }
  function thisWeekEvents(events) {
    var range = thisWeekRange();
    return (events || []).filter(function (e) {
      if (!e.date) return false;
      var d = new Date(e.date + "T00:00:00");
      return d >= range[0] && d <= range[1];
    }).sort(function (a, b) { return a.date < b.date ? -1 : (a.date > b.date ? 1 : 0); });
  }
  function miniWeekList(events) {
    if (!events.length) return '<div class="gal-mini-note">이번 주 예정된 일정이 없습니다.</div>';
    return '<ul class="gal-mini-week">' + events.slice(0, 6).map(function (e) {
      return "<li><span class=\"gmw-date\">" + esc((e.date || "").slice(5)) + "</span>" +
        '<span class="gmw-type">' + esc(e.type || "") + "</span>" +
        '<span class="gmw-company">' + esc(e.company || "") + "</span></li>";
    }).join("") + "</ul>";
  }
  function miniStockHead(name, code) {
    return '<div class="gal-mini-stock">' + esc(name) + ' <span class="mono">(' + esc(code) + ')</span></div>';
  }
  function miniBullets(bullets, note) {
    var body = (!bullets || !bullets.length)
      ? '<div class="gal-mini-note">' + esc(note || "표시할 내용이 없습니다.") + "</div>"
      : '<ul class="gal-mini-bullets">' + bullets.slice(0, 2).map(function (b) {
          return "<li>" + esc(b) + "</li>";
        }).join("") + "</ul>";
    return '<div class="gal-mini-ai"><div class="gal-mini-ai-label">🤖 AI 브리핑</div>' + body + "</div>";
  }

  // 각 로더는 자신의 미리보기 영역(el)을 직접 채운다(el) => Promise.
  var MINI_LOADERS = {
    "capital-liquidity": function (el) {
      return get("/api/capital/liquidity/summary").then(function (d) {
        var it = d.items || {};
        el.innerHTML = asOfLine(d.as_of) + miniRow([
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
      return Promise.all([get("/api/capital/cma/summary"), get("/api/capital/cma/mix"), get("/api/capital/cma/rates")]).then(function (res) {
        var summary = res[0], mix = res[1], rates = res[2];
        var it = summary.items || {};
        var top = (mix.mix || []).slice().sort(function (a, b) { return b.share - a.share; })[0] || {};
        var top5 = (rates.companies || []).slice()
          .sort(function (a, b) { return (b.rp_rate || 0) - (a.rp_rate || 0); }).slice(0, 5);
        el.innerHTML =
          miniSubtitle("CMA 잔고 현황") + asOfLine(summary.as_of) +
          miniRow([
            ["CMA 총잔고", jo(it.total && it.total.value)],
            ["RP형 잔고", jo(it.rp && it.rp.value)],
            ["발행어음형 잔고", jo(it.note && it.note.value)],
            ["RP형 최고금리", (it.rp_top_rate && it.rp_top_rate.value != null) ? it.rp_top_rate.value.toFixed(2) + "%" : "-"]
          ]) +
          miniSubtitle("CMA 유형별 비중") + asOfLine(mix.as_of) +
          '<div class="gal-mini-chart gal-mini-donut" id="' + el.id + '-donut"></div>' +
          miniSubtitle("증권사별 금리 비교") + asOfLine(rates.as_of) + miniRateTable(top5);
        var chartEl = document.getElementById(el.id + "-donut");
        if (chartEl && window.Charts) {
          window.Charts.donut(chartEl, {
            items: mix.mix,
            centerLabel: "최다 " + (top.type || ""),
            centerValue: top.share != null ? Math.round(top.share * 10) / 10 + "%" : ""
          });
        }
      });
    },
    "capital-issuance": function (el) {
      return get("/api/issuance/digest").then(function (d) {
        var c = d.counts || {};
        el.innerHTML =
          miniSubtitle((d.month_label || "이번 달") + " IPO·유상증자 캘린더 요약") + asOfLine(d.date) +
          miniRow([
            ["수요예측", c["수요예측"] || 0],
            ["청약", c["청약"] || 0],
            ["상장", c["상장"] || 0],
            ["유상증자", c["유상증자"] || 0]
          ]) +
          miniBullets(bulletsFromBriefing(d.briefing), d.briefing_note) +
          miniSubtitle("이번 주 일정") + miniWeekList(thisWeekEvents(d.events));
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
    },
    // 기업분석 위젯 검색창에서 고른 종목을 그대로 따라간다(공용 personalStockPick).
    "credit-filing": function (el) { return renderFilingsMini(el); },
    "credit-report": function (el) { return renderReportsMini(el); },
    "market-reports": function (el) {
      return get("/api/credit/market-reports").then(function (d) {
        var totalTxt = (d.total || 0) + (d.total_capped ? "+" : "") + "건";
        var html = asOfLine(d.as_of) + miniRow([["리포트 총 건수", totalTxt]]) +
          miniBullets(d.briefing, d.briefing_note);
        var top = (d.items || []).slice(0, 5);
        if (top.length) {
          html += miniSubtitle("최근 리포트") + '<ul class="gal-mini-reports">' + top.map(function (r, i) {
            return '<li><a href="' + esc(r.url || d.list_url) + '" target="_blank" rel="noopener">' +
              '<span class="gmr-no">' + (i + 1) + "</span>" +
              '<span class="gmr-broker">' + esc(r.broker || "") + "</span>" +
              '<span class="gmr-title">' + esc(r.title || "") + "</span></a></li>";
          }).join("") + "</ul>";
        }
        el.innerHTML = html;
      });
    },
    "it-news": function (el) {
      return get("/api/it-news/digest").then(function (d) {
        var html = asOfLine(d.date) + miniBullets(d.briefing, d.briefing_note);
        var top = (d.articles || []).slice(0, 5);
        if (top.length) {
          html += miniSubtitle("오늘의 기사(AI 추천)") + '<ul class="gal-mini-reports">' + top.map(function (a, i) {
            return '<li><a href="' + esc(a.url || "#") + '" target="_blank" rel="noopener">' +
              '<span class="gmr-no">' + (i + 1) + "</span>" +
              '<span class="gmr-broker">' + esc(a.keyword || "") + "</span>" +
              '<span class="gmr-title">' + esc(a.title || "") + "</span></a></li>";
          }).join("") + "</ul>";
        }
        el.innerHTML = html;
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

  // ── 기업분석/공시/리포트: 내 위젯 안에서 검색한 종목을 셋이 함께 따라간다 ──
  // (여신·심사 화면과는 독립적 — 기업분석 위젯의 검색창이 유일한 입력 지점)
  var STOCK_PICK_KEY = "personalStockPick";
  function getStockPick() {
    var pick;
    try { pick = JSON.parse(localStorage.getItem(STOCK_PICK_KEY) || "null"); } catch (e) { pick = null; }
    // 형식이 깨져 있으면(과거 버전 흔적 등) 무시하고 정리 — 검색해보라는 안내로 자연스럽게 복귀.
    if (!pick || typeof pick.code !== "string" || !/^\d{6}$/.test(pick.code)) {
      try { localStorage.removeItem(STOCK_PICK_KEY); } catch (e) {}
      return null;
    }
    return pick;
  }
  function setStockPick(code, name) {
    try { localStorage.setItem(STOCK_PICK_KEY, JSON.stringify({ code: code, name: name })); } catch (e) {}
  }
  function mktNameShort(m) {
    return m === "KOSDAQ" ? "코스닥" : m === "KOSPI" ? "코스피" : (m || "");
  }
  function fmtWon(v) { return v == null ? "-" : Number(v).toLocaleString("ko-KR"); }
  function pctFmt(v) { return v == null ? "-" : Number(v).toFixed(1) + "%"; }
  function joWon(v) { return v == null ? "-" : jo(v / 1e12); }
  function finTableHTML(labels, rows) {
    return '<table class="gal-mini-table gm-ca-fin"><thead><tr><th>구분</th>' +
      labels.map(function (y) { return "<th>" + esc(y) + "</th>"; }).join("") + "</tr></thead><tbody>" +
      rows.map(function (r) {
        return "<tr><td>" + esc(r.label) + "</td>" + (r.values || []).map(function (v) {
          return "<td>" + r.fmt(v) + "</td>";
        }).join("") + "</tr>";
      }).join("") + "</tbody></table>";
  }
  function rangeBarHTML(w52) {
    if (!w52) return "";
    var pct = Math.max(0, Math.min(100, w52.pos_pct || 0));
    return (
      '<div class="gm-ca-range">' +
        '<div class="gm-ca-range-labels"><span>' + fmtWon(w52.low) + "원</span>" +
          '<span class="gm-ca-range-mid">52주 범위</span><span>' + fmtWon(w52.high) + "원</span></div>" +
        '<div class="gm-ca-range-bar"><div class="gm-ca-range-fill" style="width:' + pct + '%"></div>' +
          '<div class="gm-ca-range-dot" style="left:' + pct + '%"></div></div>' +
      "</div>"
    );
  }

  function creditAnalysisMiniHTML(elId) {
    return '<div class="gm-ca-result" id="' + elId + '-result"><div class="gal-mini-note">종목을 검색해보세요.</div></div>';
  }
  function renderStockPreview(resultEl, code, name) {
    resultEl.innerHTML = '<span class="page-note">불러오는 중…</span>';
    Promise.all([
      get("/api/credit/equity/basics?code=" + code),
      get("/api/credit/equity/financials?code=" + code).catch(function () { return null; })
    ]).then(function (res) {
      var d = res[0], fin = res[1];
      var chg = d.change_pct;
      var chgUp = chg != null && chg > 0, chgDn = chg != null && chg < 0;
      var chgTxt = chg == null ? "-" : (chgUp ? "▲" : chgDn ? "▼" : "") + Math.abs(chg).toFixed(2) + "%";

      var html = '<div class="gm-ca-stockhead">' + esc(d.name || name) +
        ' <span class="mono">(' + esc(d.code || code) + ')</span>' +
        (d.market ? '<span class="eq-mkt">' + esc(mktNameShort(d.market)) + "</span>" : "") + "</div>";

      html += miniSubtitle("기초정보") + miniRow([
        ["종가" + (d.as_of ? "(" + d.as_of + " 기준)" : ""), d.close != null ? Number(d.close).toLocaleString("ko-KR") + "원" : "-"],
        ["등락", chgTxt, chgUp ? "k-up" : chgDn ? "k-dn" : ""],
        ["시가총액", d.market_cap != null ? jo(d.market_cap / 1e12) : "-"]
      ]) + miniRow([
        ["PER", d.valuation && d.valuation.per != null ? Number(d.valuation.per).toFixed(1) : "-"],
        ["PBR", d.valuation && d.valuation.pbr != null ? Number(d.valuation.pbr).toFixed(1) : "-"],
        ["PSR", d.valuation && d.valuation.psr != null ? Number(d.valuation.psr).toFixed(1) : "-"]
      ]) + rangeBarHTML(d.ranges && d.ranges.w52);

      if (fin && fin.annual && fin.annual.labels && fin.annual.labels.length) {
        var a = fin.annual;
        html += miniSubtitle("재무요약 (연간)") + finTableHTML(a.labels, [
          { label: "매출액", values: a.revenue, fmt: joWon },
          { label: "영업이익", values: a.operating_income, fmt: joWon },
          { label: "순이익", values: a.net_income, fmt: joWon },
          { label: "부채비율", values: a.debt_ratio, fmt: pctFmt },
          { label: "ROE", values: a.roe, fmt: pctFmt }
        ]);
        html += miniSubtitle("실적분석") +
          '<div class="gm-ca-charts">' +
            '<div class="gm-ca-chart-box"><div class="gm-ca-chart-label">매출액·영업이익(조원)</div>' +
              '<div class="gal-mini-chart" id="' + resultEl.id + '-chart1"></div></div>' +
            '<div class="gm-ca-chart-box"><div class="gm-ca-chart-label">부채비율(%)</div>' +
              '<div class="gal-mini-chart" id="' + resultEl.id + '-chart2"></div></div>' +
          "</div>";
      }

      resultEl.innerHTML = html;

      if (fin && fin.annual && window.Charts) {
        var c1 = document.getElementById(resultEl.id + "-chart1");
        if (c1) {
          window.Charts.line(c1, {
            labels: fin.annual.labels,
            series: [
              { name: "매출액", values: (fin.annual.revenue || []).map(function (v) { return v / 1e12; }), varName: "--c1" },
              { name: "영업이익", values: (fin.annual.operating_income || []).map(function (v) { return v / 1e12; }), varName: "--c2" }
            ]
          });
        }
        var c2 = document.getElementById(resultEl.id + "-chart2");
        if (c2) {
          window.Charts.line(c2, {
            labels: fin.annual.labels,
            series: [{ name: "부채비율", values: fin.annual.debt_ratio || [], varName: "--c3" }]
          });
        }
      }
    }).catch(function () {
      resultEl.innerHTML = '<div class="gal-mini-note">불러오지 못했습니다.</div>';
    });
  }

  function miniStockPickHint() {
    return '<div class="gal-mini-note">기업분석 위젯에서 종목을 검색하면 여기에도 표시됩니다.</div>';
  }

  // 공시 미리보기: 기업분석에서 고른 종목 기준 최신 5건
  function renderFilingsMini(el) {
    var pick = getStockPick();
    if (!pick) { el.innerHTML = miniStockPickHint(); return Promise.resolve(); }
    return get("/api/credit/equity/filings?code=" + pick.code).then(function (d) {
      var items = (d.items || []).slice(0, 5);
      var head = miniStockHead(d.corp_name || pick.name, pick.code);
      if (!items.length) { el.innerHTML = head + '<div class="gal-mini-note">최근 공시가 없습니다.</div>'; return; }
      el.innerHTML = head + '<ul class="gal-mini-filings">' + items.map(function (it) {
        return '<li><a href="' + esc(it.url) + '" target="_blank" rel="noopener">' +
          '<span class="gmf-date">' + esc(it.date || "") + "</span>" +
          '<span class="gmf-title">' + esc(it.title || "") + "</span></a></li>";
      }).join("") + "</ul>";
    });
  }

  // 리포트 미리보기: 목표주가 컨센서스 + 최신 리포트 5건
  function renderReportsMini(el) {
    var pick = getStockPick();
    if (!pick) { el.innerHTML = miniStockPickHint(); return Promise.resolve(); }
    return get("/api/credit/equity/reports?code=" + pick.code).then(function (d) {
      var head = miniStockHead(pick.name, pick.code);
      var c = d.consensus;
      var html = head;
      if (c) {
        html += miniSubtitle("목표주가 컨센서스") + miniRow([
          ["평균", Number(c.avg).toLocaleString("ko-KR") + "원"],
          ["최저-최고", Number(c.low).toLocaleString("ko-KR") + " ~ " + Number(c.high).toLocaleString("ko-KR")],
          ["증권사/리포트", c.n_brokers + "곳 · " + c.n_reports + "건"]
        ]);
      } else {
        html += '<div class="gal-mini-note">' + esc(d.note || "리포트 컨센서스가 없습니다.") + "</div>";
      }
      var reports = (d.reports || []).slice(0, 5);
      if (reports.length) {
        html += miniSubtitle("증권사 리포트") + '<ul class="gal-mini-reports">' + reports.map(function (r) {
          var chgIcon = r.change === "up" ? "▲" : r.change === "down" ? "▼" : r.change === "new" ? "N" : "-";
          var chgClass = r.change === "up" ? "up" : r.change === "down" ? "down" : r.change === "new" ? "new" : "flat";
          return '<li><a href="' + esc(r.url || "#") + '" target="_blank" rel="noopener">' +
            '<span class="gmr-date">' + esc(r.date || "") + "</span>" +
            '<span class="gmr-broker">' + esc(r.broker || "") + "</span>" +
            '<span class="gmr-title">' + esc(r.title || "") + "</span>" +
            (r.target ? '<span class="gmr-target">' + Number(r.target).toLocaleString("ko-KR") + "</span>" : "") +
            '<span class="gmr-chg ' + chgClass + '">' + chgIcon + "</span></a></li>";
        }).join("") + "</ul>";
      }
      el.innerHTML = html;
    });
  }

  function refreshDependentCreditWidgets() {
    var filEl = document.getElementById("mini-credit-filing");
    if (filEl) renderFilingsMini(filEl).catch(function () {
      filEl.innerHTML = '<div class="gal-mini-note">불러오지 못했습니다.</div>';
    });
    var rptEl = document.getElementById("mini-credit-report");
    if (rptEl) renderReportsMini(rptEl).catch(function () {
      rptEl.innerHTML = '<div class="gal-mini-note">불러오지 못했습니다.</div>';
    });
  }

  // 서제스트 바깥 클릭 시 닫기 — 매번 새로 렌더되는 카드에 중복 바인딩되지 않도록 문서에 한 번만 건다.
  document.addEventListener("click", function (e) {
    if (e.target.closest(".gm-ca-search")) return;
    document.querySelectorAll(".gm-ca-suggest").forEach(function (s) { s.hidden = true; });
  });
  function initCreditAnalysisSearch() {
    var card = document.querySelector(".gal-card-ca");
    if (!card) return;
    var input = card.querySelector(".gm-ca-input");
    var sugBox = card.querySelector(".gm-ca-suggest");
    var resultEl = document.getElementById("mini-credit-analysis-result");
    var timer = null;

    function search() {
      var q = input.value.trim();
      if (q.length < 2) { sugBox.hidden = true; return; }
      get("/api/credit/equity/search?q=" + encodeURIComponent(q)).then(function (d) {
        if (!d.items || !d.items.length) { sugBox.hidden = true; return; }
        sugBox.innerHTML = d.items.map(function (it) {
          return '<button type="button" class="eq-sug" data-code="' + esc(it.code) +
            '" data-name="' + esc(it.name) + '"><b>' + esc(it.name) + "</b> " +
            '<span class="mono">' + esc(it.code) + "</span>" +
            '<span class="eq-sug-mkt">' + esc(mktNameShort(it.market)) + "</span></button>";
        }).join("");
        sugBox.hidden = false;
      }).catch(function () { sugBox.hidden = true; });
    }
    input.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(search, 250);
    });
    sugBox.addEventListener("click", function (e) {
      var btn = e.target.closest(".eq-sug");
      if (!btn) return;
      var code = btn.dataset.code, name = btn.dataset.name;
      input.value = name + " (" + code + ")";
      sugBox.hidden = true;
      setStockPick(code, name);
      renderStockPreview(resultEl, code, name);
      refreshDependentCreditWidgets();
    });

    var pick = getStockPick();
    if (pick && pick.code) {
      input.value = pick.name + " (" + pick.code + ")";
      renderStockPreview(resultEl, pick.code, pick.name);
    }
  }

  // ── 카드(전사 위젯 / 내 위젯 공용) ──
  // opts.mini: 내 위젯 전용 — 있으면 실데이터 미리보기 영역을 넣고 "내 위젯에 추가" 토글 대신
  // "그만보기"(제거) 버튼을 보여준다. 제거해도 전사 위젯에서는 다시 "+ 내 위젯에 추가"로 보인다.
  function galCardHTML(w, opts) {
    opts = opts || {};
    if (opts.mini && w.id === "credit-analysis") return creditAnalysisCardHTML(w);
    if (opts.mini && w.id === "credit-equity-glance") return creditGlanceCardHTML(w);
    if (opts.mini && w.id === "sector-map") return sectorMapCardHTML(w);
    var mine = getMyWidgetIds().indexOf(w.id) >= 0;
    var miniHTML = (opts.mini && MINI_LOADERS[w.id])
      ? '<div class="gal-mini" id="mini-' + w.id + '"><span class="page-note">불러오는 중…</span></div>'
      : "";
    var toggleHTML = opts.mini
      ? '<button type="button" class="gal-remove" data-id="' + w.id + '">✕ 그만보기</button>'
      : '<button type="button" class="gal-toggle' + (mine ? " active" : "") + '" data-id="' + w.id + '">' +
        (mine ? "✓ 나의 대시보드에 추가됨" : "+ 나의 대시보드에 추가") +
      "</button>";
    // 아래 위젯들은 "자세히 보기"가 가리키는 곳이 위젯 내용과 안 맞거나(외부 검색
    // 결과로 이동 등) 카드 안에 이미 내용이 다 보여 detail 이동 자체가 불필요해
    // 갤러리·내 위젯 모두에서 버튼을 없앤다.
    var NO_DETAIL_IDS = ["market-reports", "it-news", "credit-equity-glance", "sector-map"];
    var showActionBtn = NO_DETAIL_IDS.indexOf(w.id) < 0;
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
          (showActionBtn ? actionButtonHTML(w) : "") +
          toggleHTML +
        "</div>" +
      "</div>"
    );
  }

  // 내부 업무 화면이 있으면 SPA 내 이동, 없으면(externalUrl) 새 탭으로 외부 원문 링크.
  function actionButtonHTML(w) {
    if (w.externalUrl) {
      return '<a class="dart-btn gal-open" href="' + esc(w.externalUrl) + '" target="_blank" rel="noopener">자세히 보기 →</a>';
    }
    return '<button type="button" class="dart-btn gal-open" data-work="' + w.tab + '"' +
      (w.sub ? ' data-sub="' + w.sub + '"' : "") + '>자세히 보기 →</button>';
  }

  // 기업분석 위젯(내 위젯 전용)은 상단에 종목 검색창을 둔 전용 레이아웃을 쓴다.
  function creditAnalysisCardHTML(w) {
    return (
      '<div class="gal-card gal-card-ca">' +
        '<div class="gm-ca-topsearch">' +
          '<div class="gm-ca-topsearch-label">🔍 종목 입력</div>' +
          '<div class="eq-search gm-ca-search">' +
            '<input type="text" class="gm-ca-input" placeholder="종목명 또는 코드 검색">' +
            '<div class="eq-suggest gm-ca-suggest" hidden></div>' +
          "</div>" +
        "</div>" +
        '<div class="gal-top">' +
          '<span class="gal-emoji">' + w.emoji + "</span>" +
          '<span class="gal-badges">' + statusBadgesHTML(w) + "</span>" +
        "</div>" +
        '<div class="gal-title">' + esc(w.title) + "</div>" +
        '<div class="gal-desc">' + esc(w.desc) + "</div>" +
        '<div class="gal-mini" id="mini-' + w.id + '">' + creditAnalysisMiniHTML("mini-" + w.id) + "</div>" +
        '<div class="gal-actions">' +
          '<button type="button" class="dart-btn gal-open" data-work="' + w.tab + '">자세히 보기 →</button>' +
          '<button type="button" class="gal-remove" data-id="' + w.id + '">✕ 그만보기</button>' +
        "</div>" +
      "</div>"
    );
  }

  // "한눈에 보는 기업분석 정보"(내 위젯 전용) — 종목 검색 1번으로 기초정보 + 최근 공시를
  // 한 카드 안에서 같이 보여준다(기업분석/공시 위젯을 따로 추가할 필요 없음).
  function creditGlanceCardHTML(w) {
    return (
      '<div class="gal-card gal-card-glance">' +
        '<div class="gal-top">' +
          '<span class="gal-emoji">' + w.emoji + "</span>" +
          '<span class="gal-badges">' + statusBadgesHTML(w) + "</span>" +
        "</div>" +
        '<div class="gal-title">' + esc(w.title) + "</div>" +
        '<div class="gal-desc">' + esc(w.desc) + "</div>" +
        '<div class="gm-ca-topsearch">' +
          '<div class="gm-ca-topsearch-label">🔍 종목 입력</div>' +
          '<div class="eq-search gm-ca-search">' +
            '<input type="text" class="gm-ca-input" placeholder="종목명 또는 코드 검색">' +
            '<div class="eq-suggest gm-ca-suggest" hidden></div>' +
          "</div>" +
        "</div>" +
        '<div class="gal-mini" id="mini-' + w.id + '"><div class="gm-ca-result" id="mini-' + w.id + '-result">' +
          '<div class="gal-mini-note">종목을 검색해보세요.</div></div></div>' +
        '<div class="gal-actions">' +
          '<button type="button" class="dart-btn gal-open" data-work="' + w.tab + '">자세히 보기 →</button>' +
          '<button type="button" class="gal-remove" data-id="' + w.id + '">✕ 그만보기</button>' +
        "</div>" +
      "</div>"
    );
  }

  function renderGlancePreview(resultEl, code, name) {
    resultEl.innerHTML = '<span class="page-note">불러오는 중…</span>';
    Promise.all([
      get("/api/credit/equity/basics?code=" + code),
      get("/api/credit/equity/financials?code=" + code).catch(function () { return null; }),
      get("/api/credit/equity/filings?code=" + code).catch(function () { return null; })
    ]).then(function (res) {
      var d = res[0], fin = res[1], fil = res[2];
      var chg = d.change_pct;
      var chgUp = chg != null && chg > 0, chgDn = chg != null && chg < 0;
      var chgTxt = chg == null ? "-" : (chgUp ? "▲" : chgDn ? "▼" : "") + Math.abs(chg).toFixed(2) + "%";

      var html = '<div class="gm-ca-stockhead">' + esc(d.name || name) +
        ' <span class="mono">(' + esc(d.code || code) + ')</span>' +
        (d.market ? '<span class="eq-mkt">' + esc(mktNameShort(d.market)) + "</span>" : "") + "</div>";

      html += miniSubtitle("기초정보") + miniRow([
        ["종가" + (d.as_of ? "(" + d.as_of + " 기준)" : ""), d.close != null ? Number(d.close).toLocaleString("ko-KR") + "원" : "-"],
        ["등락", chgTxt, chgUp ? "k-up" : chgDn ? "k-dn" : ""],
        ["시가총액", d.market_cap != null ? jo(d.market_cap / 1e12) : "-"]
      ]) + miniRow([
        ["거래대금", d.trade_value != null ? jo(d.trade_value / 1e12) : "-"],
        ["거래량", d.volume != null ? Number(d.volume).toLocaleString("ko-KR") + "주" : "-"],
        ["상장주식수", d.shares != null ? Number(d.shares).toLocaleString("ko-KR") + "주" : "-"]
      ]);

      var ps = d.price_series;
      if (ps && ps.values && ps.values.length > 1) {
        // 실적분석 차트 박스와 같은 크기로 보이도록 동일한 gm-ca-charts/gm-ca-chart-box 래퍼를 재사용
        html += miniSubtitle("주가흐름") +
          '<div class="gm-ca-charts"><div class="gm-ca-chart-box">' +
            '<div class="gm-ca-chart-label">종가(최근 120거래일, 원)</div>' +
            '<div class="gal-mini-chart" id="' + resultEl.id + '-pricechart"></div>' +
          "</div></div>";
      }

      if (fin && fin.annual && fin.annual.labels && fin.annual.labels.length) {
        var a = fin.annual;
        html += miniSubtitle("재무요약 (연간)") + finTableHTML(a.labels, [
          { label: "매출액", values: a.revenue, fmt: joWon },
          { label: "영업이익", values: a.operating_income, fmt: joWon },
          { label: "순이익", values: a.net_income, fmt: joWon },
          { label: "자산총계", values: a.assets, fmt: joWon },
          { label: "부채총계", values: a.liabilities, fmt: joWon },
          { label: "자본총계", values: a.equity, fmt: joWon }
        ]);
        html += miniSubtitle("실적분석") +
          '<div class="gm-ca-charts">' +
            '<div class="gm-ca-chart-box"><div class="gm-ca-chart-label">매출액·영업이익·순이익(조원)</div>' +
              '<div class="gal-mini-chart" id="' + resultEl.id + '-chart1"></div></div>' +
            '<div class="gm-ca-chart-box"><div class="gm-ca-chart-label">자산·부채·자본(조원)</div>' +
              '<div class="gal-mini-chart" id="' + resultEl.id + '-chart2"></div></div>' +
          "</div>";
      }

      var filings = (fil && fil.items || []).slice(0, 5);
      html += miniSubtitle("최근 공시(DART)");
      if (!filings.length) {
        html += '<div class="gal-mini-note">' + esc((fil && fil.note) || "최근 공시가 없습니다.") + "</div>";
      } else {
        html += '<ul class="gal-mini-reports">' + filings.map(function (it, i) {
          return '<li><a href="' + esc(it.url) + '" target="_blank" rel="noopener">' +
            '<span class="gmr-no">' + (i + 1) + "</span>" +
            '<span class="gmr-broker">' + esc(it.date || "") + "</span>" +
            '<span class="gmr-title">' + esc(it.title || "") + "</span></a></li>";
        }).join("") + "</ul>";
      }
      resultEl.innerHTML = html;

      if (ps && ps.values && ps.values.length > 1 && window.Charts) {
        var pc = document.getElementById(resultEl.id + "-pricechart");
        if (pc) {
          window.Charts.line(pc, {
            labels: ps.labels,
            series: [{ name: "종가", values: ps.values, varName: "--c1" }]
          });
        }
      }

      if (fin && fin.annual && window.Charts) {
        var L = fin.annual.labels;
        var c1 = document.getElementById(resultEl.id + "-chart1");
        if (c1) {
          window.Charts.line(c1, {
            labels: L,
            series: [
              { name: "매출액", values: (fin.annual.revenue || []).map(function (v) { return v == null ? null : v / 1e12; }), varName: "--c1" },
              { name: "영업이익", values: (fin.annual.operating_income || []).map(function (v) { return v == null ? null : v / 1e12; }), varName: "--c2" },
              { name: "순이익", values: (fin.annual.net_income || []).map(function (v) { return v == null ? null : v / 1e12; }), varName: "--c5" }
            ]
          });
        }
        var c2 = document.getElementById(resultEl.id + "-chart2");
        if (c2) {
          window.Charts.stackBar(c2, {
            labels: L,
            series: [
              { name: "부채", values: (fin.annual.liabilities || []).map(function (v) { return v == null ? null : v / 1e12; }), varName: "--c2" },
              { name: "자본", values: (fin.annual.equity || []).map(function (v) { return v == null ? null : v / 1e12; }), varName: "--c3" }
            ]
          });
        }
      }
    }).catch(function () {
      resultEl.innerHTML = '<div class="gal-mini-note">불러오지 못했습니다.</div>';
    });
  }

  function initCreditGlanceSearch() {
    var card = document.querySelector(".gal-card-glance");
    if (!card) return;
    var input = card.querySelector(".gm-ca-input");
    var sugBox = card.querySelector(".gm-ca-suggest");
    var resultEl = card.querySelector(".gm-ca-result");
    var timer = null;

    function search() {
      var q = input.value.trim();
      if (q.length < 2) { sugBox.hidden = true; return; }
      get("/api/credit/equity/search?q=" + encodeURIComponent(q)).then(function (d) {
        if (!d.items || !d.items.length) { sugBox.hidden = true; return; }
        sugBox.innerHTML = d.items.map(function (it) {
          return '<button type="button" class="eq-sug" data-code="' + esc(it.code) +
            '" data-name="' + esc(it.name) + '"><b>' + esc(it.name) + "</b> " +
            '<span class="mono">' + esc(it.code) + "</span>" +
            '<span class="eq-sug-mkt">' + esc(mktNameShort(it.market)) + "</span></button>";
        }).join("");
        sugBox.hidden = false;
      }).catch(function () { sugBox.hidden = true; });
    }
    input.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(search, 250);
    });
    sugBox.addEventListener("click", function (e) {
      var btn = e.target.closest(".eq-sug");
      if (!btn) return;
      var code = btn.dataset.code, name = btn.dataset.name;
      input.value = name + " (" + code + ")";
      sugBox.hidden = true;
      renderGlancePreview(resultEl, code, name);
    });
  }

  // "국내 업종별 시가총액 및 밸류체인"(내 위젯 전용) — 별도 페이지로 이동하지 않고
  // 카드 안에서 트리맵 + 업종 순위(기본 5개, 더보기로 전체) + 밸류체인(버튼 선택)을 모두 보여준다.
  // 렌더 함수 자체는 sector/static/sector.js 가 window.SectorWidget 으로 공개한 것을 그대로 쓴다
  // (독립 페이지 /sector 와 중복 구현하지 않기 위함).
  function sectorMapCardHTML(w) {
    var id = "mini-" + w.id;
    return (
      '<div class="gal-card gal-card-sector">' +
        '<div class="gal-top">' +
          '<span class="gal-emoji">' + w.emoji + "</span>" +
          '<span class="gal-badges">' + statusBadgesHTML(w) + "</span>" +
        "</div>" +
        '<div class="gal-title">' + esc(w.title) + "</div>" +
        '<div class="gal-desc">' + esc(w.desc) + "</div>" +
        '<div class="gal-mini" id="' + id + '">' +
          '<div class="gal-mini-subtitle">1. 업종별 시가총액 맵</div>' +
          '<div class="sector-treemap" id="' + id + '-treemap"><span class="page-note">불러오는 중…</span></div>' +
          '<p class="page-note sector-note" id="' + id + '-map-note"></p>' +
          '<div class="gal-mini-subtitle">2. 업종 순위</div>' +
          '<div class="table-wrap" id="' + id + '-rank"><span class="page-note">불러오는 중…</span></div>' +
          '<div class="gal-mini-subtitle">3. 업종별 밸류체인</div>' +
          '<div class="sector-vc-buttons" id="' + id + '-vc-buttons"></div>' +
          '<div id="' + id + '-vc-detail"><span class="page-note">불러오는 중…</span></div>' +
        "</div>" +
        '<div class="gal-actions">' +
          '<button type="button" class="gal-remove" data-id="' + w.id + '">✕ 그만보기</button>' +
        "</div>" +
      "</div>"
    );
  }

  function initSectorMapWidget() {
    if (!window.SectorWidget) return;
    var id = "mini-sector-map";
    var treemapEl = document.getElementById(id + "-treemap");
    var rankEl = document.getElementById(id + "-rank");
    var mapNoteEl = document.getElementById(id + "-map-note");
    var btnBox = document.getElementById(id + "-vc-buttons");
    var detailEl = document.getElementById(id + "-vc-detail");
    if (!treemapEl) return;

    window.SectorWidget.fetchMap().then(function (d) {
      window.SectorWidget.renderTreemap(treemapEl, d.sectors || []);
      window.SectorWidget.renderRankTable(rankEl, d.sectors || [], d.total_market_cap);
      if (mapNoteEl) mapNoteEl.textContent = d.as_of ? d.as_of + " 기준" : "";
    }).catch(function (e) {
      treemapEl.innerHTML = '<div class="chart-error">' + esc(e.message) + "</div>";
    });

    window.SectorWidget.fetchChains().then(function (d) {
      var chains = d.chains || [];
      if (!chains.length) { detailEl.innerHTML = '<div class="gal-mini-note">표시할 데이터가 없습니다.</div>'; return; }
      window.SectorWidget.renderChainButtons(btnBox, chains, function (key) {
        window.SectorWidget.renderValueChain(detailEl, window.SectorWidget.findChain(chains, key), d.as_of);
      });
      window.SectorWidget.renderValueChain(detailEl, chains[0], d.as_of);
    }).catch(function (e) {
      detailEl.innerHTML = '<div class="chart-error">' + esc(e.message) + "</div>";
    });
  }

  function bindGalleryCardEvents(scope) {
    // data-work 가 있는(=내부 화면으로 이동하는) 버튼만 SPA 네비게이션을 건다.
    // externalUrl 카드는 <a href target=_blank> 자체로 동작하므로 별도 바인딩 불필요.
    scope.querySelectorAll(".gal-open[data-work]").forEach(function (btn) {
      btn.addEventListener("click", function () { goWork(btn.dataset.work, btn.dataset.sub); });
    });
    scope.querySelectorAll(".gal-toggle").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var ids = toggleMyWidget(btn.dataset.id);
        var mine = ids.indexOf(btn.dataset.id) >= 0;
        btn.classList.toggle("active", mine);
        btn.textContent = mine ? "✓ 나의 대시보드에 추가됨" : "+ 나의 대시보드에 추가";
      });
    });
    // "그만보기"(내 위젯 전용) — 제거 후 목록을 다시 그려 카드가 즉시 사라지게 한다.
    // 전사 위젯 쪽 "+ 내 위젯에 추가" 버튼은 getMyWidgetIds() 기준으로 다시 그려지므로
    // 자동으로 원상복구된다(별도 처리 불필요).
    scope.querySelectorAll(".gal-remove").forEach(function (btn) {
      btn.addEventListener("click", function () {
        toggleMyWidget(btn.dataset.id);
        renderPersonal();
      });
    });
  }

  // 전사 위젯에는 종목 무관 "시장 전체" 성격의 위젯만 노출한다.
  // - policy-briefing/research-briefing: 홈 대시보드에서 이미 통합 브리핑으로 제공
  // - credit-analysis/credit-filing/credit-report: 특정 종목 기준이라 "내 위젯"의
  //   기업분석 검색창을 통해서만 채워진다(전사 위젯에서 훑어볼 성격의 위젯이 아님)
  // 이미 내 위젯에 추가돼 있던 경우는 그대로 유지된다.
  var HIDDEN_FROM_GALLERY = [
    "policy-briefing", "research-briefing",
    "credit-analysis", "credit-filing", "credit-report"
  ];

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
        '<div class="page-note home-empty-widgets">"+ 위젯 추가"를 눌러 전사에 등재된 위젯을 담아보세요.<br>' +
        '<button type="button" class="dart-btn" id="personal-go-gallery">위젯 추가하러 가기 →</button></div>';
      var gbtn = document.getElementById("personal-go-gallery");
      if (gbtn) gbtn.addEventListener("click", function () { if (window.AppNav) window.AppNav.go("gallery"); });
      return;
    }
    box.innerHTML = items.map(function (w) { return galCardHTML(w, { mini: true }); }).join("");
    bindGalleryCardEvents(box);
    loadMiniPreviews(items);
    if (items.some(function (w) { return w.id === "credit-analysis"; })) initCreditAnalysisSearch();
    if (items.some(function (w) { return w.id === "credit-equity-glance"; })) initCreditGlanceSearch();
    if (items.some(function (w) { return w.id === "sector-map"; })) initSectorMapWidget();
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

  // 알림 상세문구(detail)에서 날짜만 뽑아 "제목 (YYYY-MM-DD 기준)" 한 줄로 압축한다
  // (부연설명 줄은 없앰 — 요청에 따라). 끝에 붙는 "(...)" 부분은 본문보다 작고
  // 덜 굵게 보이도록 별도 span으로 감싼다.
  function alertLineTitle(a) {
    var m = a.detail ? /(\d{4}-\d{2}-\d{2})/.exec(a.detail) : null;
    var full = esc(a.title) + (m ? " (" + m[1] + " 기준)" : "");
    var pm = /^(.*?)(\s*\([^()]*\))$/.exec(full);
    return pm ? pm[1] + '<span class="al-title-sub">' + pm[2] + "</span>" : full;
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
          '<div class="al-body">' +
            '<div class="al-title">' + (a.icon || "⚠️") + " " + alertLineTitle(a) + "</div>" +
          "</div>" +
          '<button type="button" class="al-go" data-work="' + a.tab + '"' +
            (a.sub ? ' data-sub="' + a.sub + '"' : "") + '>확인 →</button>' +
        "</div>"
      );
    }).join("");
    bindGoWorkButtons(box);
  }

  function bindGoWorkButtons(scope) {
    scope.querySelectorAll("[data-work]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        // "gallery"는 업무 화면이 아니라 전사 위젯 탭이라 goWork 대신 곧장 이동시킨다.
        if (btn.dataset.work === "gallery") { if (window.AppNav) window.AppNav.go("gallery"); }
        else goWork(btn.dataset.work, btn.dataset.sub);
      });
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
      renderAlerts([WIDGET_RECOMMENDATION].concat(d.alerts || []));
    }).catch(function (e) {
      briefBox.innerHTML = '<div class="chart-error">' + esc(e.message) + "</div>";
      renderAlerts([WIDGET_RECOMMENDATION]);
      briefingLoaded = false; // 재방문 시 재시도
    });
  }

  window.HomeDashboard = {
    enterHome: function () { ensureBriefing(); },
    enterGallery: function () { renderGallery(); },
    enterPersonal: function () { renderPersonal(); }
  };
})();
