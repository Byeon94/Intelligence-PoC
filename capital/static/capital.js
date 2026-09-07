/* 자본시장 탭: 하위 탭 전환 + 지표/차트 렌더 */
(function () {
  "use strict";

  function num(n, d) {
    if (n == null || isNaN(n)) return "-";
    return Number(n).toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  function srcBadge(source) {
    if (source === "live") return '<span class="src-badge live">● 연결됨</span>';
    if (source === "curated") return '<span class="src-badge sample">● 큐레이션</span>';
    return '<span class="src-badge sample">● 샘플</span>';
  }
  function deltaHTML(change, unit) {
    if (change == null || isNaN(change) || change === 0)
      return '<div class="k-delta flat">전월 대비 —</div>';
    var up = change > 0;
    return '<div class="k-delta ' + (up ? "up" : "down") + '">' +
      (up ? "▲ +" : "▼ ") + num(change, Math.abs(change) < 10 ? 2 : 1) + (unit || "") +
      ' <span style="color:var(--muted);font-weight:600">전월 대비</span></div>';
  }
  function kpi(o) {
    return '<div class="kpi">' +
      '<div class="k-label">' + o.label + (o.source ? srcBadge(o.source) : "") + '</div>' +
      '<div class="k-value">' + o.value + (o.unit ? '<span class="k-unit">' + o.unit + '</span>' : "") + '</div>' +
      (o.sub ? '<div class="k-sub">' + o.sub + '</div>' : "") +
      (o.delta || "") +
      '</div>';
  }
  function get(url) {
    return fetch(url).then(function (r) {
      return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "요청 실패"); return j; });
    });
  }
  function loading(id) { var e = document.getElementById(id); if (e) e.innerHTML = '<div class="chart-loading">불러오는 중…</div>'; }
  function fail(id, msg) { var e = document.getElementById(id); if (e) e.innerHTML = '<div class="chart-error">' + (msg || "데이터를 불러오지 못했습니다") + '</div>'; }

  /* ── 증시자금 · 유동성 ── */
  function loadLiquiditySummary() {
    loading("liq-kpis");
    get("/api/capital/liquidity/summary").then(function (d) {
      var it = d.items, u = "조원";
      document.getElementById("liq-asof-date").textContent = (d.as_of || "") + " 기준";
      document.getElementById("liq-kpis").innerHTML = [
        kpi({ label: "투자자예탁금", value: num(it.investor_deposits.value, 1), unit: u,
              delta: deltaHTML(it.investor_deposits.change, ""), source: d.source }),
        kpi({ label: "신용공여 잔고", value: num(it.credit_balance.value, 1), unit: u,
              delta: deltaHTML(it.credit_balance.change, ""), source: d.source }),
        kpi({ label: "CMA 잔고", value: num(it.cma_balance.value, 1), unit: u,
              delta: deltaHTML(it.cma_balance.change, ""), source: d.source }),
        kpi({ label: "신용공여 / 예탁금", value: num(it.credit_deposit_ratio.value, 2), unit: "%",
              delta: deltaHTML(it.credit_deposit_ratio.change, "%p"), source: d.source })
      ].join("");
    }).catch(function (e) { fail("liq-kpis", e.message); });
  }

  function loadLiquidityTrend() {
    loading("liq-trend");
    get("/api/capital/liquidity/trend").then(function (d) {
      window.Charts.line(document.getElementById("liq-trend"), {
        labels: d.labels,
        series: [
          { name: "투자자예탁금", values: d.series.investor_deposits, varName: "--c1" },
          { name: "신용공여", values: d.series.credit_balance, varName: "--c2" },
          { name: "CMA", values: d.series.cma_balance, varName: "--c3" }
        ]
      });
    }).catch(function (e) { fail("liq-trend", e.message); });
  }

  function loadTurnoverSummary() {
    loading("turnover-kpis");
    get("/api/capital/turnover/summary").then(function (d) {
      var it = d.items, u = "조원";
      document.getElementById("turnover-asof").textContent =
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
      document.getElementById("cma-asof").textContent = (d.as_of || "") + " 기준";
      document.getElementById("cma-kpis").innerHTML = [
        kpi({ label: "CMA 총잔고", value: num(it.total.value, 1), unit: "조원", source: d.source }),
        kpi({ label: "RP형 잔고", value: num(it.rp.value, 1), unit: "조원",
              sub: "점유율 " + num(it.rp.share, 1) + "%", source: d.source }),
        kpi({ label: "발행어음형 잔고", value: num(it.note.value, 1), unit: "조원",
              sub: "점유율 " + num(it.note.share, 1) + "%", source: d.source }),
        kpi({ label: "RP형 최고금리", value: num(it.rp_top_rate.value, 2), unit: "%",
              sub: (it.rp_top_rate.company || "-"), source: "curated" })
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
      var tag = d.source === "ai_search" ? "AI 검색 기준" : "큐레이션 기준";
      document.getElementById("cma-rate-asof").textContent =
        (d.as_of || "") + " · " + tag + (d.stale ? " · 이전값" : "");
      document.getElementById("cma-rate-note").textContent = d.note || "";
      var rows = d.companies.map(function (c, i) {
        return '<tr class="' + (i === 0 ? "top-row" : "") + '">' +
          '<td>' + c.company + '</td>' +
          '<td>' + num(c.rp_rate, 2) + '%</td>' +
          '<td>' + (c.note_rate != null ? num(c.note_rate, 2) + "%" : '<span class="dash">–</span>') + '</td>' +
          '</tr>';
      }).join("");
      document.getElementById("cma-rates").innerHTML =
        '<table class="rate-table"><thead><tr>' +
        '<th>증권사</th><th>RP형 CMA</th><th>발행어음형 CMA</th>' +
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

  function initSubtabs() {
    var root = document.getElementById("capital-root");
    if (!root) return;
    var bar = document.getElementById("capital-subtabs");
    bar.addEventListener("click", function (e) {
      var btn = e.target.closest(".subtab-btn");
      if (!btn) return;
      var sub = btn.dataset.sub;
      bar.querySelectorAll(".subtab-btn").forEach(function (b) {
        b.classList.toggle("active", b === btn);
      });
      root.querySelectorAll(".sub-panel").forEach(function (p) {
        p.hidden = p.dataset.sub !== sub;
      });
      ensure(sub);
    });
  }

  function capitalVisible() {
    var p = document.querySelector('.tab-panel[data-panel="capital"]');
    return p && !p.hidden;
  }
  function maybeLoad() { if (capitalVisible()) ensure("liquidity"); }

  function boot() {
    initSubtabs();
    maybeLoad();
    var tabs = document.getElementById("main-tabs");
    if (tabs) tabs.addEventListener("click", function () { setTimeout(maybeLoad, 0); });
    var home = document.getElementById("home-link");
    if (home) home.addEventListener("click", function () { setTimeout(maybeLoad, 0); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
