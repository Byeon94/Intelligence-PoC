/* 여신·심사 탭: 종목 검색 + 기업분석(기초정보·가격범위·재무요약·실적분석). 리포트/공시는 준비 중. */
(function () {
  "use strict";

  var state = { code: null, name: null };
  var qEl, sugEl, tmr;

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
  function nf(n, d) {
    if (n == null || isNaN(n)) return "-";
    return Number(n).toLocaleString("ko-KR", {
      minimumFractionDigits: d || 0, maximumFractionDigits: d || 0,
    });
  }
  // 원 단위 금액 → "1,493조 7,241억 원"
  function money(won) {
    if (won == null || isNaN(won)) return "-";
    var neg = won < 0, n = Math.round(Math.abs(Number(won)));
    var jo = Math.floor(n / 1e12);
    var eok = Math.floor((n % 1e12) / 1e8);
    var out;
    if (jo > 0) out = nf(jo) + "조 " + (eok > 0 ? nf(eok) + "억 " : "") + "원";
    else if (eok > 0) out = nf(eok) + "억 원";
    else out = nf(n) + " 원";
    return (neg ? "−" : "") + out;
  }
  function eok(won) { return won == null || isNaN(won) ? null : won / 1e8; }
  function srcBadge(s) {
    return s === "live"
      ? '<span class="src-badge live">● 연결됨</span>'
      : '<span class="src-badge sample">● 샘플</span>';
  }
  function kpi(label, value, unit, sub, src) {
    return '<div class="kpi"><div class="k-label">' + label + (src ? srcBadge(src) : "") + "</div>" +
      '<div class="k-value">' + value + (unit ? '<span class="k-unit">' + unit + "</span>" : "") + "</div>" +
      (sub ? '<div class="k-sub">' + sub + "</div>" : "") + "</div>";
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function mktName(m) { return m === "KOSDAQ" ? "코스닥" : m === "KOSPI" ? "코스피" : (m || ""); }

  /* ── 검색 ── */
  function doSuggest() {
    var q = qEl.value.trim();
    if (q.length < 2) { sugEl.hidden = true; return; }
    get("/api/credit/equity/search?q=" + encodeURIComponent(q)).then(function (d) {
      if (!d.items || !d.items.length) { sugEl.hidden = true; return; }
      sugEl.innerHTML = d.items.map(function (it) {
        return '<button type="button" class="eq-sug" data-code="' + esc(it.code) +
          '" data-name="' + esc(it.name) + '"><b>' + esc(it.name) + "</b> " +
          '<span class="mono">' + esc(it.code) + "</span>" +
          '<span class="eq-sug-mkt">' + esc(mktName(it.market)) + "</span></button>";
      }).join("");
      sugEl.hidden = false;
    }).catch(function () { sugEl.hidden = true; });
  }

  function choose(code, name) {
    state.code = code;
    state.name = name || code;
    state.filFor = null;                 // 새 종목 → 공시·리포트 다시 로드
    state.rptFor = null;
    qEl.value = state.name + " (" + code + ")";
    sugEl.hidden = true;
    document.getElementById("eq-cur-name").textContent = state.name;
    document.getElementById("eq-cur-code").textContent = code;
    document.getElementById("eq-cur-tags").innerHTML = "";
    document.getElementById("eq-current").hidden = false;
    loadBasics();
    loadFinancials();
    if (filingSubtabActive()) loadFilings();
    if (reportSubtabActive()) loadReports();
  }

  /* ── 기초정보 + 가격범위 ── */
  function loadBasics() {
    if (!state.code) return;
    var empty = document.getElementById("eq-empty");
    var bBlock = document.getElementById("eq-basic-block");
    var rBlock = document.getElementById("eq-range-block");
    empty.hidden = false;
    empty.textContent = "불러오는 중…";
    bBlock.hidden = true;
    rBlock.hidden = true;

    get("/api/credit/equity/basics?code=" + state.code).then(function (d) {
      empty.hidden = true;
      bBlock.hidden = false;
      rBlock.hidden = false;
      state.close = d.close;

      // 헤더 태그 (시장 / 업종 / 결산·설립)
      var tags = [];
      if (d.market) tags.push('<span class="eq-mkt">' + esc(mktName(d.market)) + "</span>");
      if (d.sector) tags.push('<span class="eq-sector">' + esc(d.sector) + "</span>");
      var meta = [];
      if (d.settle_month) meta.push(esc(d.settle_month) + "월 결산");
      if (d.est_year) meta.push(esc(d.est_year) + "년 설립");
      if (meta.length) tags.push('<span class="eq-meta">' + meta.join(" · ") + "</span>");
      document.getElementById("eq-cur-tags").innerHTML = tags.join("");

      document.getElementById("eq-asof-date").textContent = (d.as_of || "") + " 기준";

      var chg = d.change || 0, up = chg > 0, dn = chg < 0;
      var chgTxt = (up ? "▲ +" : dn ? "▼ " : "") + nf(Math.abs(chg)) + " 원 (" +
        (up ? "+" : "") + nf(d.change_pct, 2) + "%)";

      var rank = [];
      if (d.market_cap_rank_in_market) rank.push(mktName(d.market) + " " + d.market_cap_rank_in_market + "위");
      if (d.market_cap_rank) rank.push("전체 " + d.market_cap_rank + "위");

      document.getElementById("eq-kpis").innerHTML = [
        kpi("종가", nf(d.close), "원",
          '<span class="' + (up ? "k-up" : dn ? "k-dn" : "") + '">' + chgTxt + "</span>", d.source),
        kpi("시가총액", money(d.market_cap), "", rank.join(" · "), d.source),
        kpi("거래대금", money(d.trade_value), "",
          d.trade_value_pct != null ? "시총 대비 " + nf(d.trade_value_pct, 2) + "%" : "", d.source),
        kpi("거래량", nf(d.volume), "주", "", d.source),
        kpi("상장주식수", nf(d.shares), "주", "", d.source),
      ].join("");

      var V = d.valuation || {};
      document.getElementById("eq-val").innerHTML = [
        ["PER", V.per], ["PBR", V.pbr], ["PSR", V.psr],
      ].map(function (x) {
        return '<div class="val-box"><span class="val-k">' + x[0] + "</span>" +
          '<span class="val-v">' + (x[1] == null ? "-" : nf(x[1], 2)) + "</span></div>";
      }).join("");

      var R = d.ranges || {};
      document.getElementById("eq-ranges").innerHTML = [
        ["52주", R.w52], ["20주", R.w20], ["10주", R.w10],
      ].map(function (row) {
        var x = row[1];
        if (!x) return "";
        return '<div class="range-row"><div class="range-top">' +
          '<span class="range-k">' + row[0] + "</span>" +
          '<span class="range-lo">신저 ' + nf(x.low) + "</span>" +
          '<span class="range-hi">신고 ' + nf(x.high) + "</span></div>" +
          '<div class="range-bar"><i style="left:' + x.pos_pct + '%"></i></div>' +
          '<div class="range-cur">현재 ' + x.pos_pct + "%</div></div>";
      }).join("");
    }).catch(function (e) {
      empty.hidden = false;
      empty.textContent = e.message || "데이터를 불러오지 못했습니다";
      bBlock.hidden = true;
      rBlock.hidden = true;
    });
  }

  /* ── 재무요약 표 ── */
  // [라벨, 필드, 단위, 그룹]  그룹: pl(손익) / bs(재무상태) / roe
  var FIN_ROWS = [
    ["매출액", "revenue", "won", "pl"],
    ["영업이익", "operating_income", "won", "pl"],
    ["영업이익률", "op_margin", "pct", "pl"],
    ["순이익", "net_income", "won", "pl"],
    ["순이익률", "net_margin", "pct", "pl"],
    ["자산총계", "assets", "won", "bs"],
    ["부채총계", "liabilities", "won", "bs"],
    ["자본총계", "equity", "won", "bs"],
    ["부채비율", "debt_ratio", "pct", "bs"],
    ["ROE", "roe", "pct", "roe"],
  ];

  function finCell(v, kind, cls) {
    if (v == null) return '<td class="' + cls + '"><span class="dash">–</span></td>';
    var txt = kind === "pct" ? nf(v, 1) + "%" : nf(Math.round(v / 1e8));
    return '<td class="' + cls + '">' + txt + "</td>";
  }

  function finTable(F) {
    var A = F.annual || F;
    var Q = F.quarters;
    var qL = Q ? Q.labels : [];
    var yL = A.labels || [];

    var head = "<tr><th>구분</th>" +
      qL.map(function (l) { return "<th>" + l + "</th>"; }).join("") +
      yL.map(function (l, i) {
        return '<th class="yr' + (i === 0 ? " yr-start" : "") + '">' + l + "년</th>";
      }).join("") + "</tr>";

    var prevGroup = null;
    var body = FIN_ROWS.map(function (m) {
      var group = m[3];
      var trCls = "g-" + group + (group !== prevGroup ? " g-start" : "");
      prevGroup = group;
      var qc = (Q ? Q[m[1]] || [] : []).map(function (v) { return finCell(v, m[2], ""); }).join("");
      var yc = (A[m[1]] || []).map(function (v, i) {
        return finCell(v, m[2], "yr" + (i === 0 ? " yr-start" : ""));
      }).join("");
      return '<tr class="' + trCls + '"><td>' + m[0] + "</td>" + qc + yc + "</tr>";
    }).join("");

    return '<table class="rate-table fin-table"><thead>' + head +
      "</thead><tbody>" + body + "</tbody></table>";
  }

  /* ── 실적분석 차트 (조원 단위) ── */
  var JO = 1e12;

  function pfChart(id, label, vals, labels, varName, mode) {
    var el = document.getElementById(id);
    if (!el) return;
    var arr = mode === "pct" ? vals.slice()
      : vals.map(function (v) { return v == null ? null : v / JO; });
    if (!arr.some(function (v) { return v != null; })) {
      el.innerHTML = '<div class="chart-error">데이터 없음</div>';
      return;
    }
    var series = [{ name: label, values: arr, varName: varName }];
    var neg = arr.some(function (v) { return v != null && v < 0; });
    if (mode === "pct" || neg) window.Charts.line(el, { labels: labels, series: series });
    else window.Charts.stackBar(el, { labels: labels, series: series });
  }

  function loadFinancials() {
    if (!state.code) return;
    var fBlock = document.getElementById("eq-fin-block");
    var pBlock = document.getElementById("eq-perf-block");
    fBlock.hidden = true;
    pBlock.hidden = true;

    get("/api/credit/equity/financials?code=" + state.code).then(function (F) {
      fBlock.hidden = false;
      pBlock.hidden = false;

      var span = (F.quarters ? "분기 + " : "") + (F.fiscal_year ? "연간" : "");
      document.getElementById("eq-fin-asof").textContent =
        span + (F.source === "live" ? " · DART" : " · 샘플");
      document.getElementById("eq-fin-note").textContent =
        "단위: 억원 (률은 %) · 연결 기준(없으면 별도) · 분기는 단일 분기 환산 · " +
        "ROE = 순이익 ÷ 자본총계 (분기는 해당 분기 기준)";
      document.getElementById("eq-fin-table").innerHTML = finTable(F);

      var L = F.labels;
      document.getElementById("eq-perf-unit").textContent = "조원 · 연간";
      pfChart("pf-rev", "매출액", F.revenue, L, "--c1");
      pfChart("pf-opi", "영업이익", F.operating_income, L, "--c3");
      pfChart("pf-ni", "순이익", F.net_income, L, "--c5");
      window.Charts.stackBar(document.getElementById("pf-bs"), {
        labels: L,
        series: [
          { name: "부채", values: F.liabilities.map(function (v) { return v == null ? null : v / JO; }), varName: "--c2" },
          { name: "자본", values: F.equity.map(function (v) { return v == null ? null : v / JO; }), varName: "--c3" },
        ],
      });
      pfChart("pf-dr", "부채비율(%)", F.debt_ratio, L, "--c6", "pct");
    }).catch(function (e) {
      document.getElementById("eq-fin-table").innerHTML =
        '<div class="chart-error">' + (e.message || "재무정보를 불러오지 못했습니다") + "</div>";
      document.getElementById("eq-fin-block").hidden = false;
      document.getElementById("eq-perf-block").hidden = true;
    });
  }

  /* ── 공시 (DART) ── */
  function loadFilings() {
    if (!state.code || state.filFor === state.code) return;
    state.filFor = state.code;
    var empty = document.getElementById("eq-fil-empty");
    var block = document.getElementById("eq-fil-block");
    empty.hidden = false;
    empty.textContent = "불러오는 중…";
    block.hidden = true;

    get("/api/credit/equity/filings?code=" + state.code).then(function (d) {
      if (!d.items || !d.items.length) {
        empty.hidden = false;
        empty.textContent = d.note || "최근 1년 내 공시가 없습니다.";
        block.hidden = true;
        return;
      }
      empty.hidden = true;
      block.hidden = false;
      document.getElementById("eq-fil-asof").textContent =
        "최근 " + d.items.length + "건" +
        (d.total && d.total > d.items.length ? " / 1년 전체 " + nf(d.total) + "건" : "") + " · DART";
      document.getElementById("eq-fil-list").innerHTML = d.items.map(function (it) {
        return '<a class="fil-row" href="' + esc(it.url) + '" target="_blank" rel="noopener">' +
          '<span class="fil-date">' + esc(it.date) + "</span>" +
          '<span class="fil-title">' + esc(it.title) +
            (it.tag ? ' <span class="fil-tag">' + esc(it.tag) + "</span>" : "") + "</span>" +
          '<span class="fil-filer">' + esc(it.filer) + "</span>" +
          '<span class="fil-go" aria-hidden="true">↗</span></a>';
      }).join("");
      var more = document.getElementById("eq-fil-more");
      more.href = d.corp_name
        ? "https://dart.fss.or.kr/dsab007/main.do?option=corp&textCrpNm=" + encodeURIComponent(d.corp_name)
        : "https://dart.fss.or.kr/";
    }).catch(function (e) {
      state.filFor = null;
      empty.hidden = false;
      empty.textContent = e.message || "공시를 불러오지 못했습니다";
      block.hidden = true;
    });
  }

  /* ── 리포트 (한경컨센서스) ── */
  function chgChip(c) {
    if (c === "up") return '<span class="chg up">▲ 상향</span>';
    if (c === "down") return '<span class="chg down">▼ 하향</span>';
    if (c === "flat") return '<span class="chg flat">— 유지</span>';
    if (c === "new") return '<span class="chg new">신규</span>';
    return "";
  }

  function loadReports() {
    if (!state.code || state.rptFor === state.code) return;
    state.rptFor = state.code;
    var empty = document.getElementById("eq-rpt-empty");
    var conB = document.getElementById("eq-rpt-con-block");
    var listB = document.getElementById("eq-rpt-list-block");
    empty.hidden = false;
    empty.textContent = "불러오는 중…";
    conB.hidden = true;
    listB.hidden = true;

    get("/api/credit/equity/reports?code=" + state.code).then(function (d) {
      if (!d.reports || !d.reports.length) {
        empty.hidden = false;
        empty.textContent = d.note || "최근 증권사 리포트가 없습니다.";
        return;
      }
      empty.hidden = true;
      listB.hidden = false;

      var C = d.consensus;
      if (C) {
        conB.hidden = false;
        document.getElementById("eq-rpt-asof").textContent =
          (d.year || "") + "년 · 리포트 " + C.n_reports + "건 · 증권사 " + C.n_brokers + "곳 · 한경컨센서스";
        var up = state.close ? (C.avg - state.close) / state.close * 100 : null;
        var opTxt = Object.keys(C.opinions || {}).map(function (k) {
          return k + " " + C.opinions[k];
        }).join(" · ") || "-";
        document.getElementById("eq-rpt-kpis").innerHTML = [
          kpi("평균 목표주가", nf(C.avg), "원", "", "live"),
          kpi("최저 · 최고", nf(C.low) + " ~ " + nf(C.high), "원", "", "live"),
          kpi("투자의견", opTxt, "", C.n_reports + "건 집계", "live"),
          kpi("현재가 대비", up == null ? "-" : (up >= 0 ? "+" : "") + nf(up, 1) + "%", "",
            up == null ? "" : (up >= 0 ? "상승 여력" : "목표주가 하회"), "live"),
        ].join("");
        document.getElementById("eq-rpt-basis").textContent =
          (d.year || "") + "년 발간 리포트 중 목표주가를 제시한 증권사의 최신 리포트 " + C.n_brokers +
          "건 기준 · 평균/최저/최고는 그 목표주가들의 산술평균·최솟값·최댓값 · " +
          "현재가 대비 = (평균 목표주가 − 종가) ÷ 종가";
      }

      document.getElementById("eq-rpt-list").innerHTML = d.reports.map(function (it) {
        var meta = [it.broker, it.analyst].filter(Boolean).join(" · ");
        return '<div class="rpt-row">' +
          '<div class="rpt-main">' +
            '<span class="rpt-date">' + esc(it.date) + "</span>" +
            (it.url
              ? '<a class="rpt-title" href="' + esc(it.url) + '" target="_blank" rel="noopener">' + esc(it.title) + " ↗</a>"
              : '<span class="rpt-title">' + esc(it.title) + "</span>") +
            '<span class="rpt-meta">' + esc(meta) + "</span>" +
          "</div>" +
          '<div class="rpt-side">' +
            (it.target ? '<span class="rpt-tp">' + nf(it.target) + "</span>" : '<span class="dash">–</span>') +
            chgChip(it.change) +
            (it.opinion ? '<span class="rpt-op">' + esc(it.opinion) + "</span>" : "") +
          "</div></div>";
      }).join("");
    }).catch(function (e) {
      state.rptFor = null;
      document.getElementById("eq-rpt-empty").hidden = false;
      document.getElementById("eq-rpt-empty").textContent = e.message || "리포트를 불러오지 못했습니다";
    });
  }

  /* ── 서브탭 ── */
  function initSubtabs() {
    var root = document.getElementById("credit-root");
    var bar = document.getElementById("credit-subtabs");
    bar.addEventListener("click", function (e) {
      var btn = e.target.closest(".subtab-btn");
      if (!btn) return;
      bar.querySelectorAll(".subtab-btn").forEach(function (b) {
        b.classList.toggle("active", b === btn);
      });
      root.querySelectorAll(".sub-panel").forEach(function (p) {
        p.hidden = p.dataset.sub !== btn.dataset.sub;
      });
      if (btn.dataset.sub === "filing") loadFilings();   // 열 때 로드(호출 절약)
      if (btn.dataset.sub === "report") loadReports();
    });
  }

  function subActive(sub) {
    var p = document.querySelector('.sub-panel[data-sub="' + sub + '"]');
    return p && !p.hidden;
  }
  function filingSubtabActive() { return subActive("filing"); }
  function reportSubtabActive() { return subActive("report"); }

  function boot() {
    var root = document.getElementById("credit-root");
    if (!root) return;
    qEl = document.getElementById("eq-q");
    sugEl = document.getElementById("eq-suggest");
    initSubtabs();

    qEl.addEventListener("input", function () {
      clearTimeout(tmr);
      tmr = setTimeout(doSuggest, 250);
    });
    qEl.addEventListener("focus", doSuggest);
    qEl.addEventListener("keydown", function (e) {
      if (e.key === "Enter") document.getElementById("eq-q-btn").click();
    });
    document.getElementById("eq-q-btn").addEventListener("click", function () {
      var q = qEl.value.trim();
      var m = q.match(/(\d{6})/);
      if (m) choose(m[1], q.replace(/\s*\(?\d{6}\)?\s*/, "").trim());
      else doSuggest();
    });
    sugEl.addEventListener("click", function (e) {
      var b = e.target.closest(".eq-sug");
      if (b) choose(b.dataset.code, b.dataset.name);
    });
    document.addEventListener("click", function (e) {
      if (!e.target.closest(".eq-search")) sugEl.hidden = true;
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
