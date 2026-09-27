/* 자본시장 탭: 하위 탭 전환 + 지표/차트 렌더 */
(function () {
  "use strict";

  var esc = window.KSFC.esc, get = window.KSFC.get;

  function num(n, d) {
    if (n == null || isNaN(n)) return "-";
    return Number(n).toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  function srcBadge(source) {
    if (source === "live") return '<span class="src-badge live">● 연결</span>';
    if (source === "curated") return '<span class="src-badge sample">● 큐레이션</span>';
    if (source === "ai_search") return '<span class="src-badge sample">● AI 검색</span>';
    if (source === "official") return '<span class="src-badge live">● 공식</span>';
    return '<span class="src-badge sample">● 샘플</span>';
  }
  // basis: 서버가 알려주는 비교 기준("day" → 전일 대비, 그 외·미지정 → 전월 대비)
  function deltaHTML(change, unit, basis) {
    var label = basis === "day" ? "전일 대비" : "전월 대비";
    if (change == null || isNaN(change) || change === 0)
      return '<div class="k-delta flat">' + label + ' —</div>';
    var up = change > 0;
    return '<div class="k-delta ' + (up ? "up" : "down") + '">' +
      (up ? "▲ +" : "▼ ") + num(change, Math.abs(change) < 10 ? 2 : 1) + (unit || "") +
      ' <span style="color:var(--muted);font-weight:600">' + label + '</span></div>';
  }
  // o.info: 제목 옆 "!" 안내 문구(클릭 시 카드 폭 팝업 — initAsofInfo 가 위임 처리)
  function kpi(o) {
    return '<div class="kpi' + (o.info ? " kpi-has-info" : "") + '">' +
      '<div class="k-label">' + o.label +
        (o.info ? '<button type="button" class="asof-info k-info" data-msg="' + esc(o.info) + '" aria-label="' + esc(o.label) + ' 안내">!</button>' : "") +
        (o.source ? srcBadge(o.source) : "") + '</div>' +
      '<div class="k-value">' + o.value + (o.unit ? '<span class="k-unit">' + o.unit + '</span>' : "") + '</div>' +
      (o.sub ? '<div class="k-sub">' + esc(o.sub) + '</div>' : "") +
      (o.delta || "") +
      '</div>';
  }
  function loading(id) { var e = document.getElementById(id); if (e) e.innerHTML = '<div class="chart-loading">불러오는 중…</div>'; }
  function fail(id, msg) { var e = document.getElementById(id); if (e) e.innerHTML = '<div class="chart-error">' + esc(msg || "데이터를 불러오지 못했습니다") + '</div>'; }

  /* ── 증시자금 · 유동성 ── */
  function loadLiquiditySummary() {
    loading("liq-kpis");
    get("/api/capital/liquidity/summary").then(function (d) {
      var it = d.items, u = "조원", basis = d.change_basis;
      document.getElementById("liq-asof-date").textContent = (d.as_of || "") + " 기준";
      document.getElementById("liq-kpis").innerHTML = [
        kpi({ label: "투자자예탁금", value: num(it.investor_deposits.value, 1), unit: u,
              delta: deltaHTML(it.investor_deposits.change, "", basis), source: d.source }),
        kpi({ label: "CMA 잔고", value: num(it.cma_balance.value, 1), unit: u,
              delta: deltaHTML(it.cma_balance.change, "", basis), source: d.source }),
        kpi({ label: "신용융자", value: num((it.credit_loan || {}).value, 1), unit: u,
              delta: deltaHTML((it.credit_loan || {}).change, "", basis), source: d.source }),
        kpi({ label: "예탁증권담보융자", value: num((it.securities_loan || {}).value, 1), unit: u,
              delta: deltaHTML((it.securities_loan || {}).change, "", basis), source: d.source })
      ].join("");
    }).catch(function (e) { fail("liq-kpis", e.message); });
  }

  function loadLiquidityTrend() {
    loading("liq-trend");
    get("/api/capital/liquidity/trend").then(function (d) {
      window.Charts.line(document.getElementById("liq-trend"), {
        labels: d.labels,
        series: [
          // 빨강·파랑·초록·보라(주황 제외) — 선명한 색은 capital.css 의 --liq-* 변수
          { name: "투자자예탁금", values: d.series.investor_deposits, varName: "--liq-red" },
          { name: "CMA", values: d.series.cma_balance, varName: "--liq-blue" },
          { name: "신용융자", values: d.series.credit_loan || [], varName: "--liq-green" },
          { name: "예탁증권담보융자", values: d.series.securities_loan || [], varName: "--liq-purple" }
        ]
      });
    }).catch(function (e) { fail("liq-trend", e.message); });
  }

  function loadTurnoverSummary() {
    loading("turnover-kpis");
    get("/api/capital/turnover/summary").then(function (d) {
      var it = d.items, u = "조원";
      document.getElementById("turnover-asof-date").textContent =
        (d.month || "") + " · 거래일 " + (d.trading_days || "-") + "일";
      document.getElementById("turnover-kpis").innerHTML = [
        kpi({ label: "코스피 월 거래대금", value: num(it.kospi_month_total.value, 1), unit: u,
              delta: deltaHTML(it.kospi_month_total.change, ""), source: d.source }),
        kpi({ label: "코스닥 월 거래대금", value: num(it.kosdaq_month_total.value, 1), unit: u,
              delta: deltaHTML(it.kosdaq_month_total.change, ""), source: d.source }),
        kpi({ label: "합계 월 거래대금", value: num(it.total_month.value, 1), unit: u,
              delta: deltaHTML(it.total_month.change, ""), source: d.source }),
        kpi({ label: "일평균 거래대금", value: num(it.daily_avg.value, 2), unit: u,
              sub: "합계 ÷ 거래일수", source: d.source })
      ].join("");
    }).catch(function (e) { fail("turnover-kpis", e.message); });
  }

  function loadTurnoverTrend() {
    loading("turnover-trend");
    get("/api/capital/turnover/trend").then(function (d) {
      window.Charts.stackBar(document.getElementById("turnover-trend"), {
        labels: d.labels,
        series: [
          { name: "코스피", values: d.series.kospi, varName: "--c1" },
          { name: "코스닥", values: d.series.kosdaq, varName: "--c2" }
        ]
      });
    }).catch(function (e) { fail("turnover-trend", e.message); });
  }

  /* ── CMA · 단기수신 ── */
  function loadCmaSummary() {
    loading("cma-kpis");
    get("/api/capital/cma/summary").then(function (d) {
      var it = d.items;
      document.getElementById("cma-asof-date").textContent = (d.as_of || "") + " 기준";
      document.getElementById("cma-kpis").innerHTML = [
        kpi({ label: "CMA 총잔고", value: num(it.total.value, 1), unit: "조원", source: d.source }),
        kpi({ label: "RP형 잔고", value: num(it.rp.value, 1), unit: "조원",
              sub: "점유율 " + num(it.rp.share, 1) + "%", source: d.source }),
        kpi({ label: "발행어음형 잔고", value: num(it.note.value, 1), unit: "조원",
              sub: "점유율 " + num(it.note.share, 1) + "%", source: d.source })
      ].join("");
    }).catch(function (e) { fail("cma-kpis", e.message); });
  }

  function loadCmaMix() {
    loading("cma-mix");
    get("/api/capital/cma/mix").then(function (d) {
      var top = d.mix.slice().sort(function (a, b) { return b.share - a.share; })[0] || {};
      window.Charts.donut(document.getElementById("cma-mix"), {
        items: d.mix,
        centerLabel: "최다 " + (top.type || ""),
        centerValue: top.share != null ? num(top.share, 1) + "%" : ""
      });
    }).catch(function (e) { fail("cma-mix", e.message); });
  }

  function loadCmaRates() {
    loading("cma-rates");
    get("/api/capital/cma/rates").then(function (d) {
      // 증권사 공식 홈페이지를 매일 새벽 확인(capital/cma_rates.py) — 기준일은 증권사가 페이지에 적은 날짜
      var checked = String(d.checked_at || d.as_of || "");
      document.getElementById("cma-rate-asof").textContent =
        (checked ? checked.slice(5, 10).replace("-", ".") + " " + checked.slice(11) + " 확인 · " : "") +
        "증권사 공식 홈페이지" + (d.stale ? " · 이전값" : "");
      document.getElementById("cma-rate-note").textContent = d.note || "";
      var dash = '<span class="dash">–</span>';
      // RP형·발행어음형 칸마다 최고 금리에 "최고" 배지(공동 1위는 모두)
      function maxOf(k) {
        return d.companies.reduce(function (m, c) { return c[k] != null && (m == null || c[k] > m) ? c[k] : m; }, null);
      }
      var topRp = maxOf("rp_rate"), topNote = maxOf("note_rate");
      function pctCell(v, top) {
        if (v == null) return '<td>' + dash + '</td>';
        return v === top
          ? '<td class="cma-top">' + num(v, 2) + '%<span class="cma-top-badge">최고</span></td>'
          : '<td>' + num(v, 2) + '%</td>';
      }
      var rows = d.companies.map(function (c) {
        var link = c.url ? '<a class="cma-src" href="' + esc(window.KSFC.safeUrl(c.url)) + '" target="_blank" rel="noopener">' : "";
        var when = c.as_of ? c.as_of.slice(2).replace(/-/g, ".") : "미표기";
        var basis = c.unavailable ? "확인 불가" : when + (c.stale ? " · 이전값" : "");
        return '<tr>' +
          '<td>' + esc(c.company) + (c.product ? '<span class="cma-product">' + esc(c.product) + '</span>' : "") + '</td>' +
          pctCell(c.rp_rate, topRp) +
          pctCell(c.note_rate, topNote) +
          '<td class="cma-basis">' + (link ? link + esc(basis) + " ↗</a>" : esc(basis)) + '</td>' +
          '</tr>';
      }).join("");
      document.getElementById("cma-rates").innerHTML =
        '<table class="rate-table"><thead><tr>' +
        '<th>증권사</th><th>RP형<span class="cma-th2"> CMA</span></th><th>발행어음형<span class="cma-th2"> CMA</span></th><th class="cma-basis">기준일<span class="cma-th2">(출처)</span></th>' +
        '</tr></thead><tbody>' + rows + '</tbody></table>';
    }).catch(function (e) { fail("cma-rates", e.message); });
  }

  /* ── 로딩 오케스트레이션 ── */
  var loaded = {};
  function ensure(sub) {
    if (loaded[sub]) return;
    loaded[sub] = true;
    if (sub === "liquidity") {
      loadLiquiditySummary(); loadLiquidityTrend();
      loadTurnoverSummary(); loadTurnoverTrend();
    } else if (sub === "cma") {
      loadCmaSummary(); loadCmaMix(); loadCmaRates();
    } else if (sub === "issuance" && window.Issuance) {
      window.Issuance.load();
    }
  }

  function activateSub(sub) {
    var root = document.getElementById("capital-root");
    var bar = document.getElementById("capital-subtabs");
    if (!root || !bar) return;
    bar.querySelectorAll(".subtab-btn").forEach(function (b) {
      b.classList.toggle("active", b.dataset.sub === sub);
    });
    root.querySelectorAll(".sub-panel").forEach(function (p) {
      p.hidden = p.dataset.sub !== sub;
    });
    ensure(sub);
  }

  function initSubtabs() {
    var bar = document.getElementById("capital-subtabs");
    if (!bar) return;
    bar.addEventListener("click", function (e) {
      var btn = e.target.closest(".subtab-btn");
      if (btn) activateSub(btn.dataset.sub);
    });
  }

  // 다른 모듈(홈 알림·전사 위젯 등)이 "자본시장 > 특정 세부탭"으로 바로 이동시킬 때 사용.
  window.CapitalNav = { goSub: activateSub };

  function capitalVisible() {
    var p = document.querySelector('.tab-panel[data-panel="capital"]');
    return p && !p.hidden;
  }
  function maybeLoad() { if (capitalVisible()) ensure("liquidity"); }

  // "!" 기준일 안내 아이콘 — 클릭하면 작은 팝업으로 안내 문구를 보여준다(호버 툴팁 대신).
  function closeAsofPopups() {
    document.querySelectorAll(".asof-popup").forEach(function (p) { p.remove(); });
  }
  // KPI 카드 안의 "!"(k-info)는 데이터를 받은 뒤에 그려지므로 버튼마다 묶지 않고 탭 전체에 위임한다.
  // 카드 안 팝업은 카드 자체에 붙여 카드 폭으로 띄운다(모바일 2열에서 화면 밖으로 나가지 않게).
  function initAsofInfo() {
    var root = document.querySelector('.tab-panel[data-panel="capital"]') || document;
    root.addEventListener("click", function (e) {
      var btn = e.target.closest(".asof-info");
      if (!btn) return;
      e.stopPropagation();
      var host = btn.classList.contains("k-info") ? btn.closest(".kpi") : btn.parentElement;
      var already = host.querySelector(":scope > .asof-popup");
      closeAsofPopups();
      if (already) return;               // 같은 버튼 다시 누르면 닫기만
      var pop = document.createElement("div");
      pop.className = "asof-popup";
      pop.textContent = btn.dataset.msg || "";
      host.appendChild(pop);
    });
    document.addEventListener("click", closeAsofPopups);
  }

  function boot() {
    initSubtabs();
    initAsofInfo();
    maybeLoad();
    var tabs = document.getElementById("main-tabs");
    if (tabs) tabs.addEventListener("click", function () { setTimeout(maybeLoad, 0); });
    var home = document.getElementById("home-link");
    if (home) home.addEventListener("click", function () { setTimeout(maybeLoad, 0); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
