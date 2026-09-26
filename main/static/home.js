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
    { id: "credit-equity-glance", tab: "credit", title: "한눈에 보는 기업분석 정보", emoji: "🔎",
      creditBadge: "투자금융부 박OO 과장 제작",
      desc: "예시로 삼성전자 정보를 바로 보여드려요 — 종목을 검색하면 다른 기업 정보도 바로 확인할 수 있습니다.",
      status: "live" },
    { id: "sector-map", externalUrl: "/sector",
      title: "국내 업종별 시가총액 순위 및 밸류체인", emoji: "📊", creditBadge: "투자금융부 이OO 과장 제작",
      desc: "국내 업종별 시가총액 순위 및 대표산업(4가지) 밸류체인", status: "live" },
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
  var STATUS_LABEL = { live: "전사 등재", dept: "부서 검증중", soon: "준비중" };
  var STATUS_CLASS = { live: "st-live", dept: "st-dept", soon: "st-soon" };

  // 나의 대시보드에 기본으로 미리 담아두는 위젯 2개 — 처음 열었을 때부터 실데이터로
  // 바로 보여주기 위함(빈 화면 대신). 이 순서 그대로 노출한다(위젯 추가 목록도
  // WIDGET_CATALOG 순서상 이미 같은 순서로 나온다).
  var DEFAULT_WIDGET_IDS = ["credit-equity-glance", "sector-map"];

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
  // "내 위젯"이 DEFAULT_WIDGET_IDS 2개만 담긴 상태로 시작하도록(=그 외엔 재접속 시
  // 지속되지 않음) 변경. 위젯 추가 목록에서도 이 2개는 처음부터 "추가됨"으로 보인다.
  var myWidgetIds = DEFAULT_WIDGET_IDS.slice();
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
  // 재무요약 표: 무조건 조 단위로 맞추면 조 미만 규모 기업은 "0.0조"처럼 실제 크기가
  // 사라져 버린다 — 1조 이상이면 조(0.1조 단위), 미만이면 억(1억 단위)으로 자동 전환한다.
  function finWon(v) {
    if (v == null) return "-";
    var abs = Math.abs(v);
    if (abs >= 1e12) return jo(v / 1e12);
    return Math.round(v / 1e8).toLocaleString("ko-KR") + "억";
  }
  // 실적분석 차트의 축 단위 — 표와 같은 이유로, 여러 계열 중 최댓값 기준으로 조/억 중 고른다.
  function finChartUnit(seriesList) {
    var max = 0;
    seriesList.forEach(function (arr) {
      (arr || []).forEach(function (v) { if (v != null) max = Math.max(max, Math.abs(v)); });
    });
    return max >= 1e12 ? { div: 1e12, label: "조원" } : { div: 1e8, label: "억원" };
  }
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
        var cc = d.category_counts || {};
        // 세부 분류(괄호 안)는 총 건수만큼 강조할 필요가 없어 더 작고 가는 글씨로 따로 감싼다
        // (miniRow는 값 전체를 esc()로 감싸 HTML을 못 끼워 넣으므로 이 줄만 직접 그린다).
        var catTxt = Object.keys(cc).sort(function (a, b) { return cc[b] - cc[a]; })
          .map(function (k) { return esc(k) + " " + cc[k]; }).join(" · ");
        var totalTxt = (d.total || 0) + (d.total_capped ? "+" : "") + "건";
        var totalRow = '<div class="gal-mini-row"><div class="gal-mini-item">' +
          '<span class="gmi-label">리포트 총 건수</span>' +
          '<span class="gmi-value">' + esc(totalTxt) +
          (catTxt ? ' <span class="gmi-value-sub">(' + catTxt + ")</span>" : "") +
          "</span></div></div>";
        var html = asOfLine(d.as_of) + totalRow +
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
  // (여신 화면과는 독립적 — 기업분석 위젯의 검색창이 유일한 입력 지점)
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
          { label: "매출액", values: a.revenue, fmt: finWon },
          { label: "영업이익", values: a.operating_income, fmt: finWon },
          { label: "순이익", values: a.net_income, fmt: finWon },
          { label: "부채비율", values: a.debt_ratio, fmt: pctFmt },
          { label: "ROE", values: a.roe, fmt: pctFmt }
        ]);
        var caChartUnit1 = finChartUnit([a.revenue, a.operating_income]);
        html += miniSubtitle("실적분석") +
          '<div class="gm-ca-charts">' +
            '<div class="gm-ca-chart-box"><div class="gm-ca-chart-label">매출액·영업이익(' + caChartUnit1.label + ')</div>' +
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
              { name: "매출액", values: (fin.annual.revenue || []).map(function (v) { return v == null ? null : v / caChartUnit1.div; }), varName: "--c1" },
              { name: "영업이익", values: (fin.annual.operating_income || []).map(function (v) { return v == null ? null : v / caChartUnit1.div; }), varName: "--c2" }
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
            '<input type="text" class="gm-ca-input" placeholder="종목명 또는 코드 검색" value="삼성전자 (005930)">' +
            '<div class="eq-suggest gm-ca-suggest" hidden></div>' +
          "</div>" +
        "</div>" +
        '<div class="gal-mini" id="mini-' + w.id + '"><div class="gm-ca-result" id="mini-' + w.id + '-result">' +
          '<span class="page-note">불러오는 중…</span></div></div>' +
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
          { label: "매출액", values: a.revenue, fmt: finWon },
          { label: "영업이익", values: a.operating_income, fmt: finWon },
          { label: "순이익", values: a.net_income, fmt: finWon },
          { label: "자산총계", values: a.assets, fmt: finWon },
          { label: "부채총계", values: a.liabilities, fmt: finWon },
          { label: "자본총계", values: a.equity, fmt: finWon }
        ]);
        var glanceChartUnit1 = finChartUnit([a.revenue, a.operating_income, a.net_income]);
        var glanceChartUnit2 = finChartUnit([a.liabilities, a.equity]);
        html += miniSubtitle("실적분석") +
          '<div class="gm-ca-charts">' +
            '<div class="gm-ca-chart-box"><div class="gm-ca-chart-label">매출액·영업이익·순이익(' + glanceChartUnit1.label + ')</div>' +
              '<div class="gal-mini-chart" id="' + resultEl.id + '-chart1"></div></div>' +
            '<div class="gm-ca-chart-box"><div class="gm-ca-chart-label">자산·부채·자본(' + glanceChartUnit2.label + ')</div>' +
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
              { name: "매출액", values: (fin.annual.revenue || []).map(function (v) { return v == null ? null : v / glanceChartUnit1.div; }), varName: "--c1" },
              { name: "영업이익", values: (fin.annual.operating_income || []).map(function (v) { return v == null ? null : v / glanceChartUnit1.div; }), varName: "--c2" },
              { name: "순이익", values: (fin.annual.net_income || []).map(function (v) { return v == null ? null : v / glanceChartUnit1.div; }), varName: "--c5" }
            ]
          });
        }
        var c2 = document.getElementById(resultEl.id + "-chart2");
        if (c2) {
          window.Charts.stackBar(c2, {
            labels: L,
            series: [
              { name: "부채", values: (fin.annual.liabilities || []).map(function (v) { return v == null ? null : v / glanceChartUnit2.div; }), varName: "--c2" },
              { name: "자본", values: (fin.annual.equity || []).map(function (v) { return v == null ? null : v / glanceChartUnit2.div; }), varName: "--c3" }
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

    // 처음 담았을 때 빈 화면 대신 예시(삼성전자)를 바로 보여준다 — 입력창의 기본값과
    // 짝을 맞춘 코드/이름. 사용자가 검색하면 renderGlancePreview가 그대로 덮어쓴다.
    renderGlancePreview(resultEl, "005930", "삼성전자");
  }

  // "국내 업종별 시가총액 순위 및 밸류체인"(내 위젯 전용) — 별도 페이지로 이동하지 않고
  // 카드 안에서 업종 순위(기본 5개, 더보기로 전체) + 밸류체인(버튼 선택)을 모두 보여준다.
  // 렌더 함수 자체는 sector/static/sector.js 가 window.SectorWidget 으로 공개한 것을 그대로 쓴다
  // (독립 페이지 /sector 와 중복 구현하지 않기 위함). 시가총액 트리맵 맵은 모바일에서
  // 레이아웃이 깨져 기능을 제거했다.
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
          '<div class="gal-mini-subtitle">1. 업종 순위</div>' +
          '<p class="page-note sector-note" id="' + id + '-map-note"></p>' +
          '<div class="table-wrap" id="' + id + '-rank"><span class="page-note">불러오는 중…</span></div>' +
          '<div class="gal-mini-subtitle">2. 업종별 밸류체인</div>' +
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
    var rankEl = document.getElementById(id + "-rank");
    var mapNoteEl = document.getElementById(id + "-map-note");
    var btnBox = document.getElementById(id + "-vc-buttons");
    var detailEl = document.getElementById(id + "-vc-detail");
    if (!rankEl) return;

    window.SectorWidget.fetchMap().then(function (d) {
      window.SectorWidget.renderRankTable(rankEl, d.sectors || [], d.total_market_cap);
      if (mapNoteEl) mapNoteEl.textContent = d.as_of ? d.as_of + " 기준" : "";
    }).catch(function (e) {
      rankEl.innerHTML = '<div class="chart-error">' + esc(e.message) + "</div>";
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

  function galItemsForCatalog() {
    return WIDGET_CATALOG.filter(function (w) {
      return w.status !== "soon" && HIDDEN_FROM_GALLERY.indexOf(w.id) < 0;
    });
  }

  function renderGallery() {
    var box = document.getElementById("gallery-grid");
    if (!box) return;
    box.innerHTML = galItemsForCatalog().map(function (w) { return galCardHTML(w); }).join("");
    bindGalleryCardEvents(box);
  }

  function personalAnchorId(w) { return "personal-w-" + w.id; }

  // 위젯을 여러 개 담으면 한 화면에 다 쌓여 복잡해지니, 제목 칩을 탭처럼 써서
  // 한 번에 하나씩만 보여준다(선택 상태는 탭이 열려 있는 동안만 메모리로 유지).
  var personalActiveId = null;

  function renderPersonalJumpNav(items) {
    var nav = document.getElementById("personal-jump-nav");
    if (!nav) return;
    if (items.length < 2) { nav.innerHTML = ""; return; }
    nav.innerHTML = items.map(function (w) {
      return '<button type="button" class="pd-jump-chip' + (w.id === personalActiveId ? " active" : "") +
        '" data-id="' + esc(w.id) + '">' + w.emoji + " " + esc(w.title) + "</button>";
    }).join("");
    nav.querySelectorAll(".pd-jump-chip").forEach(function (chip) {
      chip.addEventListener("click", function () {
        personalActiveId = chip.dataset.id;
        showPersonalWidget(personalActiveId);
        nav.querySelectorAll(".pd-jump-chip").forEach(function (c) {
          c.classList.toggle("active", c === chip);
        });
      });
    });
  }

  function showPersonalWidget(id) {
    document.querySelectorAll(".pd-widget-anchor").forEach(function (el) {
      el.hidden = el.id !== personalAnchorId({ id: id });
    });
  }

  function renderPersonal() {
    var box = document.getElementById("personal-grid");
    if (!box) return;
    var ids = getMyWidgetIds();
    var items = WIDGET_CATALOG.filter(function (w) { return ids.indexOf(w.id) >= 0; });
    if (!items.length) {
      personalActiveId = null;
      document.getElementById("personal-jump-nav").innerHTML = "";
      // 상단 헤더에 이미 "+ 위젯 추가" 버튼이 있어, 여기서는 문구만 안내하고
      // 별도 버튼(예전엔 "위젯 추가하러 가기 →")은 중복이라 없앴다.
      // 위 block-head 소개 문구("+ 위젯 추가"를 눌러...)와 중복이라 별도 안내 없이 빈 채로 둔다.
      box.innerHTML = "";
      return;
    }
    // 이전에 선택했던 위젯이 아직 있으면 유지, 없으면(처음이거나 방금 제거됐으면) 첫 위젯으로.
    if (!items.some(function (w) { return w.id === personalActiveId; })) {
      personalActiveId = items[0].id;
    }
    renderPersonalJumpNav(items);
    box.innerHTML = items.map(function (w) {
      return '<div class="pd-widget-anchor" id="' + personalAnchorId(w) + '"' +
        (w.id === personalActiveId ? "" : " hidden") + ">" + galCardHTML(w, { mini: true }) + "</div>";
    }).join("");
    bindGalleryCardEvents(box);
    loadMiniPreviews(items);
    if (items.some(function (w) { return w.id === "credit-analysis"; })) initCreditAnalysisSearch();
    if (items.some(function (w) { return w.id === "credit-equity-glance"; })) initCreditGlanceSearch();
    if (items.some(function (w) { return w.id === "sector-map"; })) initSectorMapWidget();
  }

  // ── 위젯 추가 모달 ── "전사 위젯/부서 위젯" 같은 내부 용어 대신, 실제 있는 구분(담당자가
  // 직접 만든 위젯 vs 자본시장 정보)만 자연어로 묶어 보여준다(없는 "인기순위"는 지어내지 않음).
  function waGroupHTML(title, items) {
    if (!items.length) return "";
    return (
      '<div class="wa-group"><div class="wa-group-title">' + esc(title) + "</div>" +
      items.map(function (w) { return galCardHTML(w); }).join("") +
      "</div>"
    );
  }
  function renderWidgetAddModal(query) {
    var body = document.getElementById("wa-body");
    if (!body) return;
    var all = galItemsForCatalog();
    var q = (query || "").trim().toLowerCase();
    var filtered = q ? all.filter(function (w) {
      return (w.title + " " + w.desc).toLowerCase().indexOf(q) >= 0;
    }) : all;
    var madeByStaff = filtered.filter(function (w) { return !!w.creditBadge; });
    var capitalInfo = filtered.filter(function (w) { return w.tab === "capital"; });
    var rest = filtered.filter(function (w) {
      return madeByStaff.indexOf(w) < 0 && capitalInfo.indexOf(w) < 0;
    });
    var html =
      waGroupHTML("✍️ 담당자가 직접 만든 위젯", madeByStaff) +
      waGroupHTML("📈 자본시장 정보", capitalInfo) +
      waGroupHTML("그 밖의 위젯", rest);
    body.innerHTML = html || '<div class="page-note">검색 결과가 없습니다.</div>';
    bindGalleryCardEvents(body);
  }
  function openWidgetAddModal() {
    var modal = document.getElementById("widget-add-modal");
    if (!modal) return;
    var search = document.getElementById("wa-search");
    if (search) search.value = "";
    renderWidgetAddModal("");
    modal.hidden = false;
    document.body.style.overflow = "hidden";
  }
  function closeWidgetAddModal() {
    var modal = document.getElementById("widget-add-modal");
    if (modal) modal.hidden = true;
    document.body.style.overflow = "";
    renderPersonal(); // 모달에서 추가/제거한 결과를 나의 대시보드에 바로 반영
  }

  // ── AI가 추천하기(mock) ── 실제 개인화 백엔드가 없어, 선택한 업무·키워드를 위젯
  // 카탈로그의 제목·설명과 단순 매칭해 추천한다(프런트 mock 플로우 — 실제 AI 판단 아님).
  var AI_ROLE_OPTIONS = ["투자금융", "리스크", "여신", "자금", "영업", "기타"];
  var AI_ROLE_MATCH = {
    "투자금융": ["sector-map", "capital-issuance", "market-reports"],
    "리스크": ["capital-liquidity", "credit-equity-glance"],
    "여신": ["credit-equity-glance", "capital-liquidity"],
    "자금": ["capital-liquidity", "capital-cma"],
    "영업": ["market-reports", "sector-map"],
    "기타": ["it-news", "sector-map"]
  };
  function aiRecommendFormHTML() {
    return (
      '<p class="page-note">주로 어떤 업무를 하시나요?</p>' +
      '<div class="ai-role-options">' +
        AI_ROLE_OPTIONS.map(function (r) {
          return '<label class="ai-role-opt"><input type="radio" name="ai-role" value="' + esc(r) + '">' + esc(r) + "</label>";
        }).join("") +
      "</div>" +
      '<p class="page-note" style="margin-top:14px">최근 관심 있는 주제나 기업이 있나요?</p>' +
      '<input type="text" class="wa-search" id="ai-keyword" placeholder="예: 2차전지, CFD, 삼성전자">' +
      '<button type="button" class="dart-btn" id="ai-run-btn" style="margin-top:14px">AI가 추천하기</button>'
    );
  }
  // 위젯별로 하나씩 "+ 추가"/"✓ 추가됨"을 토글한다(예전엔 "모두 추가" 하나뿐이라
  // 원치 않는 항목까지 한 번에 담기게 됐음). 목록 자체는 role·keyword가 바뀔 때만
  // 다시 그리고, 토글은 버튼 하나만 갱신해 리스트가 다시 그려지며 깜빡이지 않게 한다.
  function aiResultItemHTML(w) {
    var mine = getMyWidgetIds().indexOf(w.id) >= 0;
    return (
      '<li class="ai-result-item" data-id="' + esc(w.id) + '">' +
        '<span class="ai-result-name">' + esc(w.emoji) + " " + esc(w.title) + "</span>" +
        '<button type="button" class="gal-toggle ai-result-add' + (mine ? " active" : "") + '" data-id="' + esc(w.id) + '">' +
          (mine ? "✓ 추가됨" : "+ 추가") +
        "</button>" +
      "</li>"
    );
  }
  function aiRecommendResultHTML(role, keyword) {
    var all = galItemsForCatalog();
    var picked = {};
    (AI_ROLE_MATCH[role] || []).forEach(function (id) { picked[id] = true; });
    var kw = (keyword || "").trim().toLowerCase();
    if (kw) {
      all.forEach(function (w) {
        if ((w.title + " " + w.desc).toLowerCase().indexOf(kw) >= 0) picked[w.id] = true;
      });
    }
    var items = all.filter(function (w) { return picked[w.id]; });
    if (!items.length) items = all.slice(0, 3);
    return (
      '<p class="page-note">' + esc(role) + ' 업무에 맞는 위젯을 추천해드릴게요 — 원하는 위젯만 골라 추가하세요</p>' +
      '<ul class="ai-result-list">' +
        items.map(aiResultItemHTML).join("") +
      "</ul>"
    );
  }
  function bindAiRecommendForm() {
    var runBtn = document.getElementById("ai-run-btn");
    if (!runBtn) return;
    runBtn.addEventListener("click", function () {
      var checked = document.querySelector('input[name="ai-role"]:checked');
      var role = checked ? checked.value : "기타";
      var keywordEl = document.getElementById("ai-keyword");
      var body = document.getElementById("ai-body");
      body.innerHTML = aiRecommendResultHTML(role, keywordEl ? keywordEl.value : "");
    });
    var body = document.getElementById("ai-body");
    if (body && !body.dataset.bound) {
      body.dataset.bound = "1";
      body.addEventListener("click", function (e) {
        var btn = e.target.closest(".ai-result-add");
        if (!btn) return;
        var ids = toggleMyWidget(btn.dataset.id);
        var mine = ids.indexOf(btn.dataset.id) >= 0;
        btn.classList.toggle("active", mine);
        btn.textContent = mine ? "✓ 추가됨" : "+ 추가";
      });
    }
  }
  function openAiRecommendModal() {
    var modal = document.getElementById("ai-recommend-modal");
    if (!modal) return;
    var body = document.getElementById("ai-body");
    if (body) body.innerHTML = aiRecommendFormHTML();
    bindAiRecommendForm();
    modal.hidden = false;
    document.body.style.overflow = "hidden";
  }
  function closeAiRecommendModal() {
    var modal = document.getElementById("ai-recommend-modal");
    if (modal) modal.hidden = true;
    document.body.style.overflow = "";
    renderPersonal();
  }

  // ── 홈 대시보드: 통합 브리핑 + 알림 ──
  function bulletsFromBriefing(b) {
    if (!b) return [];
    var arr = Array.isArray(b) ? b.slice() : String(b).split("\n");
    return arr.map(function (l) { return l.replace(/^\s*[-•*]\s*/, "").trim(); })
      .filter(Boolean).slice(0, 3);
  }

  // 날짜 "20260921" → "2026-09-21" (data.go.kr 등 원천이 하이픈 없는 basDt 형식을 줄 때).
  function fmtDate(s) {
    s = String(s || "");
    return /^\d{8}$/.test(s) ? s.slice(0, 4) + "-" + s.slice(4, 6) + "-" + s.slice(6, 8) : s;
  }

  // ── 오늘의 브리핑: 오늘의 핵심 ── AI가 먼저 골라낸 최대 3건만 보여준다(이상징후
  // 알림 → 정책 발표 → AI 선별 리서치 기사 순으로 채워짐, main/home.py get_home_summary
  // 참고). 뉴스 feed처럼 보이지 않도록 01번은 크게(+"왜 중요한가?"), 02/03은 컴팩트하게
  // 렌더한다. research.curate 가 이미 만들어둔 태그·이유(reason)를 그대로 재사용,
  // 새 Gemini 호출 없음.
  function alertLineTitle(a) {
    var m = a.detail ? /(\d{4}-\d{2}-\d{2})/.exec(a.detail) : null;
    return esc(a.title) + (m ? " (" + m[1] + " 기준)" : "");
  }
  function todayKeyCardHTML(h, rank) {
    var cat, badge, reason, dateText;
    if (h.kind === "alert") {
      cat = "알림";
      badge = h.level === "warn" ? '<span class="hl-badge">HOT</span>' : "";
      reason = h.detail || "";
      dateText = "";
    } else if (h.kind === "policy") {
      cat = h.org || "정책·규제";
      badge = '<span class="hl-badge">HOT</span>';
      reason = "금융당국 발표 — 관련 업무 영향 확인이 필요합니다.";
      dateText = fmtDate(h.date);
    } else if (h.kind === "market") {
      cat = "시장 브리핑";
      badge = "";
      reason = h.detail || "";
      dateText = "";
    } else {
      cat = h.tag || "일반";
      badge = "";
      reason = h.reason || "";
      dateText = fmtDate(h.date);
    }
    var primary = rank === 1;
    var reasonHTML = "";
    if (reason && primary) {
      reasonHTML = '<div class="hl-reason"><span class="hl-reason-label">왜 중요한가?</span>' + esc(reason) + "</div>";
    } else if (reason) {
      reasonHTML = '<div class="hl-reason-sm">' + esc(reason) + "</div>";
    }
    var inner =
      '<div class="hl-no">' + String(rank).padStart(2, "0") + "</div>" +
      '<div class="hl-body">' +
        '<div class="hl-top"><span class="hl-cat">' + esc(cat) + "</span>" + badge +
          (dateText ? '<span class="hl-date">' + esc(dateText) + "</span>" : "") + "</div>" +
        '<div class="hl-title">' +
          (h.kind === "alert" ? alertLineTitle(h) : esc(h.title || "")) +
        "</div>" + reasonHTML +
      "</div>";
    var cls = "hl-card" + (primary ? " hl-card-primary" : " hl-card-compact");
    if (h.kind === "alert") {
      return '<div class="' + cls + ' hl-card-btn" data-work="' + esc(h.tab || "") + '"' +
        (h.sub ? ' data-sub="' + esc(h.sub) + '"' : "") + ">" + inner + "</div>";
    }
    if (h.kind === "market") {
      // 다른 탭으로 이동하는 대신, 같은 화면 아래 "오늘의 시장 브리핑" 섹션으로 스크롤한다.
      return '<div class="' + cls + ' hl-card-btn" data-scroll="brief-briefing-block">' + inner + "</div>";
    }
    return '<a class="' + cls + '" href="' + esc(h.url || "#") + '" target="_blank" rel="noopener">' + inner + "</a>";
  }

  function renderHighlights(d) {
    var box = document.getElementById("brief-highlights");
    if (!box) return;
    var items = d.today_key || [];
    box.innerHTML = items.length
      ? items.map(function (h, i) { return todayKeyCardHTML(h, i + 1); }).join("")
      : '<div class="page-note">오늘은 꼭 확인할 만큼 중요한 항목이 없습니다.</div>';
    bindGoWorkButtons(box);
    box.querySelectorAll("[data-scroll]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var el = document.getElementById(btn.dataset.scroll);
        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  }

  // ── 오늘의 브리핑: 시장 한눈에 ── 국내(코스피·코스닥, data.go.kr)와 해외(다우·나스닥·
  // S&P500, Yahoo Finance 비공식 API)를 탭 전환 없이 한 화면에 같이 보여주고, 환율은
  // 그 아래 별도 줄로 붙인다(지수와 단위가 달라 같은 그리드에 섞지는 않음).
  // sparkValues가 있으면 카드 안에 빈 자리(id 부여)를 만들어두고, box.innerHTML 대입
  // 이후에 window.Charts.sparkline로 채운다(SVG를 문자열로 직접 만들지 않기 위함).
  var mktSparkQueue = [];
  function mktIdxHTML(label, close, chg, sparkValues, unit) {
    var cls = chg > 0 ? "st-c-up" : chg < 0 ? "st-c-down" : "";
    var arrow = chg > 0 ? "▲" : chg < 0 ? "▼" : "";
    var chgText = chg == null ? "-" : arrow + Math.abs(chg).toFixed(2) + "%";
    var sparkHTML = "";
    if (sparkValues && sparkValues.length > 1) {
      var id = "mkt-spark-" + mktSparkQueue.length;
      mktSparkQueue.push({ id: id, values: sparkValues });
      sparkHTML = '<div class="mkt-idx-spark" id="' + id + '"></div>';
    }
    return (
      '<div class="mkt-idx"><div class="mkt-idx-name">' + esc(label) + "</div>" +
        '<div class="mkt-idx-value">' + Number(close).toLocaleString("ko-KR") + (unit || "") + "</div>" +
        '<div class="mkt-idx-chg ' + cls + '">' + chgText + "</div>" +
        sparkHTML +
      "</div>"
    );
  }
  function renderMarket(d) {
    var box = document.getElementById("brief-market");
    if (!box) return;
    var m = d.market, gm = d.global_market;
    var mh = d.market_history, gh = d.global_market_history;
    var mhLive = mh && mh.source === "live";
    var ghLive = gh && gh.source === "live";
    mktSparkQueue = [];
    var html = "";

    var idxCards = "";
    if (m && m.source === "live") {
      idxCards += mktIdxHTML("KOSPI", m.kospi.close, m.kospi.change_pct, mhLive && mh.kospi.values) +
        mktIdxHTML("KOSDAQ", m.kosdaq.close, m.kosdaq.change_pct, mhLive && mh.kosdaq.values);
    }
    if (gm && gm.source === "live") {
      idxCards += gm.us_indices.map(function (idx) {
        var hist = ghLive && gh[idx.name];
        return mktIdxHTML(idx.name, idx.close, idx.change_pct, hist && hist.values);
      }).join("");
    }
    if (idxCards) {
      html += '<div class="mkt-grid mkt-grid-3">' + idxCards + "</div>";
    } else {
      html += '<div class="page-note">시장 지수를 일시적으로 불러오지 못했습니다.</div>';
    }

    if (gm && gm.source === "live") {
      html += '<div class="mkt-sub-label">환율</div>' +
        '<div class="mkt-grid mkt-grid-3">' +
          gm.fx.map(function (f) { return mktIdxHTML(f.name, f.value, f.change_pct); }).join("") +
        "</div>";
    }

    // 국고채 3년물은 아직 안정적인 데이터 소스를 못 구해 표시하지 않는다(있는 척 지어내지
    // 않음). 미국채10년은 Yahoo Finance(^TNX)로 붙였다.
    if (gm && gm.source === "live" && gm.bond_us10y) {
      var bondHist = ghLive && gh.bond_us10y;
      html += '<div class="mkt-sub-label">금리</div>' +
        '<div class="mkt-grid mkt-grid-3">' +
          mktIdxHTML(gm.bond_us10y.name, gm.bond_us10y.value, gm.bond_us10y.change_pct,
            bondHist && bondHist.values, "%") +
        "</div>";
    }

    var asofBits = [];
    if (m && m.source === "live") asofBits.push(esc(fmtDate(m.as_of)) + " 기준 코스피·코스닥(공공데이터포털)");
    if (gm && gm.source === "live") asofBits.push("실시간 해외·환율·금리(Yahoo Finance, 참고용)");
    if (asofBits.length) {
      html += '<div class="page-note mkt-asof"><span class="mkt-asof-inline">' + asofBits.join(" · ") +
        '<button type="button" class="asof-info" data-msg="코스피·코스닥은 공공데이터 특성상 통계가 집계되어 제공되기까지 시간이 걸려, 화면에 표시되는 기준일이 오늘보다 며칠 늦을 수 있습니다. 해외 지수·환율·금리는 Yahoo Finance 실시간 시세로, 공식 통계가 아닌 참고용입니다. 그래프는 최근 1년 일별 종가 추이입니다." ' +
          'aria-label="기준일 안내">!</button></span></div>';
    }

    box.innerHTML = html;
    bindAsofInfo(box);
    mktSparkQueue.forEach(function (s) {
      var el = document.getElementById(s.id);
      if (el && window.Charts) window.Charts.sparkline(el, { values: s.values });
    });
  }

  // "!" 기준일 안내 아이콘 — 자본시장 탭(capital.js)과 같은 UX(클릭 시 작은 팝업)를
  // 쓰지만, 이 박스는 페이지 로드 후 fetch로 늦게 채워지므로 그때마다 새로 바인딩한다.
  var asofInfoDocBound = false;
  function closeAsofPopups() {
    document.querySelectorAll(".asof-popup").forEach(function (p) { p.remove(); });
  }
  function bindAsofInfo(scope) {
    scope.querySelectorAll(".asof-info").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        var already = btn.parentElement.querySelector(".asof-popup");
        closeAsofPopups();
        if (already) return; // 같은 버튼 다시 누르면 닫기만
        var pop = document.createElement("div");
        pop.className = "asof-popup";
        pop.textContent = btn.dataset.msg || "";
        btn.parentElement.appendChild(pop);
      });
    });
    if (!asofInfoDocBound) {
      asofInfoDocBound = true;
      document.addEventListener("click", closeAsofPopups);
    }
  }

  // ── 오늘의 브리핑: 주요뉴스(AI 선별 상위 6건, 전체는 리서치·뉴스 탭에서) ──
  function briefNewsRowHTML(a) {
    // 태그·제목·날짜를 한 줄에 나란히 두면 제목 칸이 좁아져 줄바꿈이 잦았다.
    // 태그+날짜는 위 메타줄로 따로 빼고, 제목은 카드 전체 너비를 쓰게 해 줄바꿈을 최소화한다.
    return (
      '<a class="brief-news-item" href="' + esc(a.url) + '" target="_blank" rel="noopener">' +
        '<span class="bni-top">' +
          '<span class="bni-tag">' + esc(a.tag || "일반") + "</span>" +
          '<span class="bni-date">' + esc(a.published || "") + "</span>" +
        "</span>" +
        '<span class="bni-title">' + esc(a.title) + "</span>" +
      "</a>"
    );
  }
  // ── 오늘의 브리핑: 오늘의 시장 브리핑(AI, 주식/채권/환율/장전 4개 카테고리, 하루 1회) ──
  var BRIEFING_CATS = [
    { key: "주식", icon: "📊" },
    { key: "채권", icon: "💵" },
    { key: "환율", icon: "💱" },
    { key: "장전", icon: "🌙" }
  ];
  function renderMarketBriefing(d) {
    var box = document.getElementById("brief-briefing");
    if (!box) return;
    var mb = d.market_briefing;
    var sections = mb && mb.sections;
    var cats = sections ? BRIEFING_CATS.filter(function (c) { return sections[c.key]; }) : [];
    if (!cats.length) {
      box.innerHTML = '<div class="page-note">' + esc((mb && mb.note) || "오늘 시장 브리핑을 아직 준비하지 못했습니다.") + "</div>";
      return;
    }
    box.innerHTML = '<div class="mb-grid">' + cats.map(function (c) {
      return '<div class="mb-item">' +
        '<div class="mb-item-head"><span class="mb-item-icon">' + c.icon + '</span>' +
          '<span class="mb-item-label">' + esc(c.key) + '</span></div>' +
        '<div class="mb-item-text">' + esc(sections[c.key]) + '</div>' +
      '</div>';
    }).join('') + '</div>';
  }

  function renderBriefNews(d) {
    var box = document.getElementById("brief-news");
    if (!box) return;
    var arts = d.today_news || [];
    box.innerHTML = arts.length
      ? arts.map(briefNewsRowHTML).join("")
      : '<div class="page-note">' + esc((d.research && d.research.briefing_note) || "오늘 선별된 뉴스가 없습니다.") + "</div>";
  }

  function bindGoWorkButtons(scope) {
    scope.querySelectorAll("[data-work]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        // "gallery"는 업무 화면이 아니라 위젯 추가 모달을 여는 자리다.
        if (btn.dataset.work === "gallery") { openWidgetAddModal(); }
        else goWork(btn.dataset.work, btn.dataset.sub);
      });
    });
  }

  // 정적 버튼(모달 열기/닫기/검색)은 페이지 로드 시 한 번만 바인딩한다.
  var waAddBtn = document.getElementById("personal-add-widget-btn");
  if (waAddBtn) waAddBtn.addEventListener("click", openWidgetAddModal);
  var waCloseBtn = document.getElementById("wa-close-btn");
  if (waCloseBtn) waCloseBtn.addEventListener("click", closeWidgetAddModal);
  var waBackdrop = document.getElementById("wa-backdrop");
  if (waBackdrop) waBackdrop.addEventListener("click", closeWidgetAddModal);
  var waSearchInput = document.getElementById("wa-search");
  if (waSearchInput) waSearchInput.addEventListener("input", function () { renderWidgetAddModal(waSearchInput.value); });
  var aiRecommendBtn = document.getElementById("personal-ai-recommend-btn");
  if (aiRecommendBtn) aiRecommendBtn.addEventListener("click", openAiRecommendModal);
  var aiCloseBtn = document.getElementById("ai-close-btn");
  if (aiCloseBtn) aiCloseBtn.addEventListener("click", closeAiRecommendModal);
  var aiBackdrop = document.getElementById("ai-backdrop");
  if (aiBackdrop) aiBackdrop.addEventListener("click", closeAiRecommendModal);
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    var wa = document.getElementById("widget-add-modal");
    var ai = document.getElementById("ai-recommend-modal");
    if (wa && !wa.hidden) closeWidgetAddModal();
    if (ai && !ai.hidden) closeAiRecommendModal();
  });

  // home.html의 정적 버튼(오늘의 주요뉴스 "더보기 →")은 매번 다시 그려지지 않으니
  // 페이지 로드 시 한 번만 바인딩한다(ensureBriefing은 재시도 시 다시 불릴 수 있어
  // 거기서 바인딩하면 리스너가 중복 등록된다).
  var briefNewsMoreBtn = document.querySelector('#brief-news-block [data-work]');
  if (briefNewsMoreBtn) bindGoWorkButtons(briefNewsMoreBtn.parentElement);

  function renderGreetTime() {
    var now = new Date();
    var hh = String(now.getHours()).padStart(2, "0");
    var mm = String(now.getMinutes()).padStart(2, "0");
    var yyyy = now.getFullYear();
    var mo = String(now.getMonth() + 1).padStart(2, "0");
    var dd = String(now.getDate()).padStart(2, "0");
    var wd = ["일", "월", "화", "수", "목", "금", "토"][now.getDay()];
    var timeEl = document.getElementById("brief-greet-time");
    if (timeEl) {
      timeEl.textContent = yyyy + "." + mo + "." + dd + "(" + wd + ") 마지막 업데이트 " + hh + ":" + mm;
    }
    var titleEl = document.getElementById("brief-greet-title");
    if (titleEl) titleEl.textContent = "좋은 하루입니다.";
  }

  var briefingLoaded = false;
  function ensureBriefing() {
    if (briefingLoaded) return;
    briefingLoaded = true;
    renderGreetTime();
    get("/api/home/summary").then(function (d) {
      renderHighlights(d);
      renderMarket(d);
      renderMarketBriefing(d);
      renderBriefNews(d);
      obStart(); // 브리핑 데이터가 실제 렌더된 뒤에 시작해야 스포트라이트 박스가
                 // "불러오는 중" 자리(짧음)가 아니라 실제 콘텐츠 크기에 맞는다.
    }).catch(function (e) {
      ["brief-highlights", "brief-market", "brief-briefing", "brief-news"].forEach(function (id) {
        var box = document.getElementById(id);
        if (box) box.innerHTML = '<div class="chart-error">' + esc(e.message) + "</div>";
      });
      briefingLoaded = false; // 재방문 시 재시도
      obStart(); // 브리핑 로딩이 실패해도 온보딩 자체는 계속 보여준다.
    });
  }

  window.HomeDashboard = {
    enterHome: function () { ensureBriefing(); },
    enterGallery: function () { renderGallery(); },
    enterPersonal: function () { renderPersonal(); },
    // 온보딩은 보통 홈 화면의 브리핑 로딩 완료 시점에 시작되지만(obStart 참고), 첫 진입
    // 화면이 홈이 아닌 경우(예: 북마크한 #capital 링크로 접속)를 위한 안전장치로 노출한다.
    obStart: obStart
  };

  // ── 온보딩 투어 — 오늘의 브리핑의 "오늘의 핵심/시장 한눈에/오늘의 주요뉴스" 3개
  // 영역을 소개한 뒤, 사이드바 버튼만 가리키는 대신 실제로 나의 대시보드·자본시장
  // 화면으로 이동해(step.nav) 위젯 추가·부서 화면을 직접 보여주며 설명한다(환영 화면
  // + 완료 화면 포함 총 7스텝). 세션 여부와 무관하게 웹페이지를 열 때마다 매번
  // 보여준다(로그인이 없는 PoC라 "이 사람이 처음 왔는지"를 판단할 방법이 없어, 저장해뒀다
  // 건너뛰는 대신 매번 짧게 보여주는 쪽을 택함). 사이드바는 데스크톱에선 세로, 모바일에선
  // 상단 가로 바로 바뀌므로, 스포트라이트·말풍선 위치는 매번 실제 렌더된 좌표
  // (getBoundingClientRect)를 기준으로 계산하고, 화면 밖에 있을 수 있는 대상은
  // 먼저 scrollIntoView로 보이게 한다. ──
  var OB_STEPS = [
    { type: "welcome" },
    { type: "spot", sel: "#brief-key-block",
      title: "오늘의 핵심",
      body: "오늘 가장 먼저 확인할 곳입니다. AI가 여러 정보 중 업무에 중요한 변화를 먼저 선별해 보여드립니다." },
    { type: "spot", sel: "#brief-market-block",
      title: "시장 한눈에",
      body: "국내외 주요 지수와 환율을 한눈에 확인하세요." },
    { type: "spot", sel: "#brief-news-block",
      title: "오늘의 주요뉴스",
      body: "더 많은 뉴스가 필요하면 여기서 확인하고, \"더보기\"로 리서치·뉴스 탭에서 더 깊이 살펴볼 수 있습니다." },
    { type: "spot", nav: "personal", sel: "#personal-add-widget-btn",
      title: "나의 대시보드 — 위젯 추가",
      body: "지금처럼 기본 위젯 2개를 미리 담아드렸어요. \"+ 위젯 추가\"를 누르면 내가 자주 보는 정보만 골라 더 담아 나만의 화면을 만들 수 있습니다." },
    // 실제로 자본시장 화면까지 들어갔다 나오면(모바일에서는 사이드바가 2행이라 화면이
    // 아래로 길어져) 스포트라이트 위치가 어색해진다는 피드백에 따라, 페이지 이동 없이
    // 사이드바의 부서 메뉴 자체를 가리키는 방식으로 되돌린다.
    { type: "spot", selRange: ['.side-btn[data-cat="capital"]', '.side-btn[data-cat="research"]'],
      title: "업무별 메뉴(부서 위젯)",
      body: "자본시장·여신·정책·규제·리서치·뉴스처럼 부서별 상세 화면은 여기서 바로 이동해 확인할 수 있습니다." },
    { type: "done" }
  ];
  var obIndex = 0;

  function obUnionRect(el1, el2) {
    var a = el1.getBoundingClientRect(), b = el2.getBoundingClientRect();
    var top = Math.min(a.top, b.top), left = Math.min(a.left, b.left);
    var right = Math.max(a.right, b.right), bottom = Math.max(a.bottom, b.bottom);
    return { top: top, left: left, right: right, bottom: bottom, width: right - left, height: bottom - top };
  }

  function obWelcomeHTML() {
    return (
      "<h3>안녕하세요! 👋</h3>" +
      "<p>증금 인텔리전스에 오신 것을 환영합니다.<br>AI가 시장·정책·뉴스를 분석해 매일 아침 업무에 필요한 핵심만 먼저 알려드립니다.</p>" +
      '<div class="ob-tooltip-actions">' +
        '<button type="button" class="dart-btn" id="ob-next">1분 투어 시작하기 →</button>' +
        '<button type="button" class="ob-skip" id="ob-skip">건너뛰기</button>' +
      "</div>"
    );
  }
  function obDoneHTML() {
    return (
      "<h3>준비가 완료되었습니다 🎉</h3>" +
      "<p>이제 오늘의 브리핑, 나의 대시보드, 업무별 메뉴를 자유롭게 둘러보세요.</p>" +
      '<div class="ob-tooltip-actions">' +
        '<button type="button" class="dart-btn" id="ob-done-btn">오늘의 브리핑 보기 →</button>' +
      "</div>"
    );
  }
  function obSpotHTML(step) {
    var spotSteps = OB_STEPS.filter(function (s) { return s.type === "spot"; });
    var n = spotSteps.indexOf(step) + 1;
    return (
      '<div class="ob-tooltip-step">' + n + "/" + spotSteps.length + "</div>" +
      "<h3>" + esc(step.title) + "</h3>" +
      "<p>" + esc(step.body) + "</p>" +
      '<div class="ob-tooltip-actions">' +
        '<button type="button" class="ob-skip" id="ob-skip">건너뛰기</button>' +
        '<button type="button" class="dart-btn" id="ob-next">다음 →</button>' +
      "</div>"
    );
  }
  // 말풍선이 항상 뷰포트 안에 완전히 보이도록 가로·세로 모두 clamp한다. 데스크톱
  // 폭에서도 스포트라이트 대상이 화면 오른쪽 끝 가까이 있으면(예: 폭 넓은 "오늘의
  // 주요뉴스" 블록) 오른쪽에 붙일 공간이 없어 잘려 보이던 문제를 막기 위해, 오른쪽에
  // 공간이 없으면 왼쪽에, 그것도 부족하면 화면 안쪽으로 강제로 당긴다.
  function obPosition(rect) {
    var spot = document.getElementById("ob-spot");
    var tip = document.getElementById("ob-tooltip");
    var pad = 6;
    var boxLeft = rect.left - pad;
    var boxTop = rect.top - pad;
    var boxWidth = rect.width + pad * 2;
    var boxHeight = rect.height + pad * 2;
    // 사이드바 버튼처럼 대상이 컨테이너 경계에 딱 붙어 있으면, 패딩만큼 그 경계를 넘어
    // 튀어나와(진한 남색 사이드바 밖 흰 배경까지 파란 테두리가 걸쳐) 보인다 — 대상이
    // 사이드바 안에 있을 때는 그 오른쪽 경계를 넘지 않게 잘라준다.
    var sidebar = document.getElementById("main-tabs");
    if (sidebar) {
      var sbRect = sidebar.getBoundingClientRect();
      if (rect.left >= sbRect.left - 1 && rect.right <= sbRect.right + 1) {
        var maxRight = sbRect.right - 2;
        if (boxLeft + boxWidth > maxRight) boxWidth = Math.max(0, maxRight - boxLeft);
      }
    }
    // 그 밖에도 화면 가장자리에 바짝 붙은 대상은(예: 모바일 헤더 버튼) 패딩만큼 화면
    // 밖으로 밀려나 잘려 보일 수 있어, 뷰포트 경계도 넘지 않게 한 번 더 잘라준다.
    if (boxLeft < 2) { boxWidth -= (2 - boxLeft); boxLeft = 2; }
    if (boxTop < 2) { boxHeight -= (2 - boxTop); boxTop = 2; }
    if (boxLeft + boxWidth > window.innerWidth - 2) boxWidth = Math.max(0, window.innerWidth - 2 - boxLeft);
    if (boxTop + boxHeight > window.innerHeight - 2) boxHeight = Math.max(0, window.innerHeight - 2 - boxTop);
    spot.style.top = boxTop + "px";
    spot.style.left = boxLeft + "px";
    spot.style.width = boxWidth + "px";
    spot.style.height = boxHeight + "px";

    var margin = 12;
    var tipW = Math.min(300, window.innerWidth - margin * 2);
    var mobile = window.innerWidth <= 880;
    var top, left;
    if (mobile) {
      top = rect.bottom + 14;
      left = Math.min(Math.max(margin, rect.left), window.innerWidth - tipW - margin);
    } else {
      var spaceRight = window.innerWidth - rect.right - 18;
      var spaceLeft = rect.left - 18;
      if (spaceRight >= tipW) {
        left = rect.right + 18;
      } else if (spaceLeft >= tipW + margin) {
        left = rect.left - 18 - tipW;
      } else {
        left = Math.max(margin, Math.min(rect.left, window.innerWidth - tipW - margin));
      }
      top = Math.max(margin, rect.top);
    }
    tip.style.width = tipW + "px";
    tip.style.left = left + "px";
    tip.style.top = top + "px";
    // 내용을 이미 채운 뒤에 호출되므로 실제 렌더된 높이로 세로 clamp가 가능하다
    // (화면 아래로 넘쳐 하단 버튼이 안 보이는 것을 막음).
    var tipH = tip.offsetHeight || 0;
    if (tipH) {
      tip.style.top = Math.max(margin, Math.min(top, window.innerHeight - tipH - margin)) + "px";
    }
  }
  function obBindStepButtons() {
    var next = document.getElementById("ob-next");
    if (next) next.addEventListener("click", obNext);
    var skip = document.getElementById("ob-skip");
    if (skip) skip.addEventListener("click", obEnd);
    var doneBtn = document.getElementById("ob-done-btn");
    if (doneBtn) doneBtn.addEventListener("click", obEnd);
  }
  // 스텝 전환마다 증가 — 이동 대기 중(obWaitNavReady) 사용자가 "다음/건너뛰기"로 다른
  // 스텝으로 넘어가면, 늦게 도착하는 이전 폴링 콜백이 더 이상 화면을 덮어쓰지 않게 막는다.
  var obRenderToken = 0;

  // 대상이 실제로 화면에 잡힐 때까지 스포트라이트·말풍선을 그리고 위치를 맞춘다
  // (nav 스텝이든 아니든 공통 — 대상 엘리먼트가 "지금" 존재한다고 가정).
  function obShowSpot(step) {
    var backdrop = document.getElementById("ob-backdrop");
    var spot = document.getElementById("ob-spot");
    var tip = document.getElementById("ob-tooltip");
    if (!backdrop || !spot || !tip) return;
    var rect;
    if (step.selRange) {
      var a = document.querySelector(step.selRange[0]), b = document.querySelector(step.selRange[1]);
      if (!a || !b) { obNext(); return; }
      a.scrollIntoView({ block: "center", behavior: "auto" });
      rect = obUnionRect(a, b);
    } else {
      var el = document.querySelector(step.sel);
      if (!el) { obNext(); return; }
      el.scrollIntoView({ block: "center", behavior: "auto" });
      rect = el.getBoundingClientRect();
    }
    backdrop.hidden = true;
    spot.hidden = false;
    tip.hidden = false;
    tip.className = "ob-tooltip";
    tip.innerHTML = obSpotHTML(step);
    obPosition(rect);
    obBindStepButtons();
  }

  // step.navReady가 있으면(예: 자본시장의 유동성 요약) 그게 true가 될 때까지 짧게
  // 폴링한다 — 원천 장애 등으로 끝내 안 채워져도 3초 뒤엔 그냥 지금 상태로 보여준다.
  function obWaitNavReady(step, token, cb) {
    if (!step.navReady) { cb(); return; }
    var start = Date.now();
    (function poll() {
      if (token !== obRenderToken) return; // 그 사이 다른 스텝으로 넘어감
      if (step.navReady() || Date.now() - start > 3000) { cb(); return; }
      setTimeout(poll, 80);
    })();
  }

  function obRenderStep() {
    var step = OB_STEPS[obIndex];
    if (!step) { obEnd(); return; }
    var backdrop = document.getElementById("ob-backdrop");
    var spot = document.getElementById("ob-spot");
    var tip = document.getElementById("ob-tooltip");
    if (!backdrop || !spot || !tip) return;
    var token = ++obRenderToken;

    if (step.type === "spot") {
      if (step.nav) {
        // 이 스텝은 다른 업무 화면으로 실제 이동해서 설명한다(나의 대시보드/업무별 메뉴).
        // 이동 도중 이전 스텝의 스포트라이트가 잘못된 위치에 잠깐 보였다 다시 그려지는
        // "깜빡임"을 막기 위해, 화면이 준비될 때까지는 아무것도 안 보여준다.
        backdrop.hidden = true; spot.hidden = true; tip.hidden = true;
        goWork(step.nav);
        obWaitNavReady(step, token, function () {
          if (token !== obRenderToken) return;
          obShowSpot(step);
        });
        return;
      }
      obShowSpot(step);
    } else {
      spot.hidden = true;
      backdrop.hidden = false;
      tip.hidden = false;
      tip.className = "ob-tooltip ob-centered";
      // 이전 스텝이 spot이었다면 obPosition()이 top/left/width를 인라인 스타일로
      // 박아뒀다 — 인라인 스타일은 .ob-centered의 top:50%/left:50%보다 우선순위가
      // 높아서 안 지우면 welcome·done 모달이 마지막 스포트라이트 위치에 걸려
      // 화면 밖으로 잘려 보인다(실제로 모바일에서 이렇게 잘려 보인다는 제보 확인).
      tip.style.top = ""; tip.style.left = ""; tip.style.width = "";
      tip.innerHTML = step.type === "welcome" ? obWelcomeHTML() : obDoneHTML();
      obBindStepButtons();
    }
  }
  function obNext() { obIndex++; obRenderStep(); }
  function obEnd() {
    obRenderToken++; // 진행 중이던 nav 대기가 있으면 이제 와서 화면을 덮어쓰지 않게
    ["ob-backdrop", "ob-spot", "ob-tooltip"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.hidden = true;
    });
    if (window.AppNav) window.AppNav.go("home");
  }
  // 창 크기 변경 시에는 위치만 다시 잰다 — 내용을 다시 그리면(말풍선 재생성·버튼 재바인딩)
  // 크기 변화가 없어도 매번 다시 깜빡여 보인다.
  function obResize() {
    var step = OB_STEPS[obIndex];
    if (!step || step.type !== "spot" || document.getElementById("ob-spot").hidden) return;
    var rect;
    if (step.selRange) {
      var a = document.querySelector(step.selRange[0]), b = document.querySelector(step.selRange[1]);
      if (!a || !b) return;
      rect = obUnionRect(a, b);
    } else {
      var el = document.querySelector(step.sel);
      if (!el) return;
      rect = el.getBoundingClientRect();
    }
    obPosition(rect);
  }
  window.addEventListener("resize", obResize);

  var obStarted = false;
  function obStart() {
    if (obStarted) return;
    obStarted = true;
    // 브리핑 데이터 로딩이 끝난(성공/실패 모두) 시점에 호출된다. 사이드바 레이아웃이
    // 자리잡은 뒤 좌표를 재야 스포트라이트 위치가 어긋나지 않으므로 약간의 지연을 둔다.
    setTimeout(function () { obIndex = 0; obRenderStep(); }, 400);
  }
})();
