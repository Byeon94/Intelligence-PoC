/* 단기자금 탭: 원화(단기금리·스프레드·추이) / 외화(환율·원달러 추이·한미 정책금리) — ECOS 실데이터 */
(function () {
  "use strict";

  var esc = window.KSFC.esc, get = window.KSFC.get;

  function num(n, d) {
    if (n == null || isNaN(n)) return "-";
    return Number(n).toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  // 'YYYY-MM-DD' → 'MM.DD', 'YYYY-MM' → 'YYYY.MM'
  function shortDate(s) {
    s = String(s || "");
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s.slice(5).replace("-", ".");
    if (/^\d{4}-\d{2}$/.test(s)) return s.replace("-", ".");
    return s;
  }
  function signed(n, d) { return (n > 0 ? "+" : "") + num(n, d); }
  function deltaHTML(text, dir, label) {
    return '<div class="k-delta ' + dir + '">' + text +
      (label ? ' <span class="k-delta-label">' + esc(label) + '</span>' : "") + '</div>';
  }
  function bpDelta(bp) {
    if (bp == null) return deltaHTML("—", "flat", "전일 대비");
    if (bp === 0) return deltaHTML("0bp", "flat", "전일 대비");
    return deltaHTML((bp > 0 ? "▲ +" : "▼ ") + bp + "bp", bp > 0 ? "up" : "down", "전일 대비");
  }
  function kpi(o) {
    return '<div class="kpi">' +
      '<div class="k-label">' + esc(o.label) + '</div>' +
      '<div class="k-value">' + o.value + (o.unit ? '<span class="k-unit">' + esc(o.unit) + '</span>' : "") + '</div>' +
      (o.sub ? '<div class="k-sub">' + esc(o.sub) + '</div>' : "") +
      (o.delta || "") + '</div>';
  }
  function loading(id) { var e = document.getElementById(id); if (e) e.innerHTML = '<div class="chart-loading">불러오는 중…</div>'; }
  function fail(ids, msg) {
    ids.forEach(function (id) {
      var e = document.getElementById(id);
      if (e) e.innerHTML = '<div class="chart-error">' + esc(msg || "데이터를 불러오지 못했습니다") + '</div>';
    });
  }

  /* ── 원화 ── */
  var WON_IDS = ["won-kpis", "won-spreads", "won-trend"];
  function loadWon() {
    WON_IDS.forEach(loading);
    get("/api/funding/won").then(function (d) {
      document.getElementById("won-asof").textContent = shortDate(d.as_of) + " 기준";
      document.getElementById("won-kpis").innerHTML = d.items.map(function (it) {
        return kpi({ label: it.label, value: num(it.value, it.key === "base" ? 2 : 3), unit: "%",
                     sub: it.date ? shortDate(it.date) + " 기준" : "", delta: bpDelta(it.change_bp) });
      }).join("");

      var sd = d.spread_dates || {};
      var rows = d.spreads.map(function (s) {
        var chg = (s.value_bp != null && s.week_ago_bp != null) ? s.value_bp - s.week_ago_bp : null;
        var chgCls = chg > 0 ? "up" : chg < 0 ? "down" : "";
        return '<tr><td>' + esc(s.label) + '</td>' +
          '<td class="fund-strong">' + (s.value_bp == null ? "-" : signed(s.value_bp, 0)) + '</td>' +
          '<td>' + (s.week_ago_bp == null ? "-" : signed(s.week_ago_bp, 0)) + '</td>' +
          '<td class="fund-chg ' + chgCls + '">' + (chg == null ? "-" : signed(chg, 0)) + '</td></tr>';
      }).join("");
      document.getElementById("won-spreads").innerHTML =
        '<table class="rate-table fund-spread-table"><thead><tr>' +
        '<th>구간</th><th>' + esc(shortDate(sd.today)) + '</th><th>1주 전(' + esc(shortDate(sd.week_ago)) + ')</th><th>변화</th>' +
        '</tr></thead><tbody>' + rows + '</tbody></table>';

      window.Charts.line(document.getElementById("won-trend"), {
        labels: d.trend.labels,
        series: d.trend.series.map(function (s, i) {
          return { name: s.name, values: s.values, varName: ["--c6", "--c1", "--c2", "--c3"][i] };
        })
      });
    }).catch(function (e) { fail(WON_IDS, e.message); });
  }

  /* ── 외화 ── */
  var FX_IDS = ["fx-kpis", "fx-usd-trend", "fx-policy-kpis", "fx-policy-trend"];
  function loadFx() {
    FX_IDS.forEach(loading);
    get("/api/funding/fx").then(function (d) {
      document.getElementById("fx-asof").textContent = shortDate(d.as_of) + " 기준";
      document.getElementById("fx-kpis").innerHTML = d.items.map(function (it) {
        var delta;
        if (it.change == null) delta = deltaHTML("—", "flat", "전일 대비");
        else delta = deltaHTML((it.change > 0 ? "▲ +" : it.change < 0 ? "▼ " : "") + num(it.change, 2) +
          " (" + signed(it.change_pct, 2) + "%)", it.change > 0 ? "up" : it.change < 0 ? "down" : "flat", "전일 대비");
        return kpi({ label: it.label, value: num(it.value, 2), unit: "원", delta: delta });
      }).join("");

      window.Charts.line(document.getElementById("fx-usd-trend"), {
        labels: d.usd_trend.labels,
        series: [{ name: "원/달러", values: d.usd_trend.values, varName: "--c1" }]
      });

      var p = d.policy;
      document.getElementById("fx-policy-kpis").innerHTML = [
        kpi({ label: "한국 기준금리", value: num(p.kr.value, 2), unit: "%", sub: shortDate(p.kr.date) + " 기준" }),
        kpi({ label: "미국 정책금리(상단)", value: num(p.us.value, 2), unit: "%",
              sub: (p.us.lower != null ? num(p.us.lower, 2) + "~" + num(p.us.value, 2) + "% · " : "") + shortDate(p.us.date) }),
        kpi({ label: "한·미 금리차", value: p.gap_bp == null ? "-" : signed(p.gap_bp, 0), unit: "bp",
              sub: p.gap_bp == null ? "" : (p.gap_bp < 0 ? "역전(미국↑)" : "한국↑") })
      ].join("");
      window.Charts.line(document.getElementById("fx-policy-trend"), {
        labels: p.trend.labels,
        series: [
          { name: "한국 기준금리", values: p.trend.kr, varName: "--c1" },
          { name: "미국 정책금리(상단)", values: p.trend.us, varName: "--c2" }
        ]
      });
    }).catch(function (e) { fail(FX_IDS, e.message); });
  }

  /* ── AI 시황 브리프(원화) — KIDB·한국자금중개 일일 PDF 요약 ── */
  function briefCardHTML(b) {
    if (b.error) {
      return '<div class="fund-brief"><div class="fund-brief-head"><span class="fund-brief-name">📑 ' + esc(b.name) + '</span></div>' +
        '<div class="fund-brief-foot"><span>' + esc(b.error) + (b.reason ? ' (' + esc(b.reason) + ')' : '') +
        ' 원문 게시판에서 직접 확인해주세요.</span>' +
        (b.url ? '<a class="fund-brief-link" href="' + esc(window.KSFC.safeUrl(b.url)) + '" target="_blank" rel="noopener">원문 →</a>' : '') +
        '</div></div>';
    }
    var when = (b.doc_date ? shortDate(b.doc_date) + " 자료" : "") +
      (b.briefed_at ? " · " + esc(String(b.briefed_at).slice(11)) + " 자동요약" : "") + (b.stale ? " · 이전 자료" : "");
    var bullets = (b.bullets || []).map(function (x) {
      return '<li><b>' + esc(x.head) + '</b> ' + esc(x.text) + '</li>';
    }).join("");
    var body = bullets
      ? '<ul class="fund-brief-list">' + bullets + '</ul>'
      : '<div class="page-note">' + esc(b.note || "AI 요약을 준비 중입니다.") + '</div>';
    var link = b.url ? '<a class="fund-brief-link" href="' + esc(window.KSFC.safeUrl(b.url)) +
      '" target="_blank" rel="noopener">원문 →</a>' : "";
    return '<div class="fund-brief">' +
      '<div class="fund-brief-head"><span class="fund-brief-name">📑 ' + esc(b.name) + '</span>' +
        '<span class="fund-chip">AI 요약</span><span class="fund-chip">일간</span>' +
        '<span class="fund-brief-when">' + when + '</span></div>' +
      body +
      '<div class="fund-brief-foot"><span>' + (b.summary ? '💬 <b>AI 종합:</b> ' + esc(b.summary) : "") + '</span>' + link + '</div>' +
      '</div>';
  }
  function loadBriefs() {
    loading("won-briefs");
    get("/api/funding/briefs").then(function (d) {
      document.getElementById("won-briefs").innerHTML = (d.items || []).map(briefCardHTML).join("");
    }).catch(function (e) { fail(["won-briefs"], e.message); });
  }

  /* ── 관련 뉴스(원화·외화 각 3건, 하루 1회 AI 추천 — 한 번 받아 두 탭에 나눠 그림) ── */
  var newsPromise = null;
  function newsData() {
    if (!newsPromise) newsPromise = get("/api/funding/news").catch(function (e) { newsPromise = null; throw e; });
    return newsPromise;
  }
  function renderNews(topic) {
    var box = "fx" === topic ? "fx-news" : "won-news";
    loading(box);
    newsData().then(function (d) {
      var part = d[topic] || {};
      var asof = document.getElementById(topic + "-news-asof");
      if (asof) asof.textContent = part.picked_by === "ai" ? "AI 추천" : part.picked_by === "latest" ? "최신순" : "";
      var items = part.items || [];
      document.getElementById(box).innerHTML = items.length
        ? '<div class="fund-news">' + items.map(function (a) {
            return '<a class="fund-news-item" href="' + esc(window.KSFC.safeUrl(a.url)) + '" target="_blank" rel="noopener">' +
              '<span class="fund-chip">뉴스</span>' +
              '<span class="fund-news-body"><span class="fund-news-title">' + esc(a.title) + '</span>' +
              '<span class="fund-news-meta">' + esc(shortDate(String(a.published || "").slice(0, 10))) +
                (a.reason ? " · " + esc(a.reason) : "") + '</span></span></a>';
          }).join("") + '</div>'
        : '<div class="page-note">관련 뉴스를 아직 찾지 못했습니다.</div>';
    }).catch(function (e) { fail([box], e.message); });
  }

  /* ── 하위 탭 전환 · 지연 로딩(탭이 처음 보일 때 한 번) ── */
  var loaded = {};
  function ensure(sub) {
    if (loaded[sub]) return;
    loaded[sub] = true;
    if (sub === "won") { loadWon(); loadBriefs(); renderNews("won"); }
    else if (sub === "fx") { loadFx(); renderNews("fx"); }
  }
  function activateSub(sub) {
    var root = document.getElementById("funding-root");
    if (!root) return;
    root.querySelectorAll("#funding-subtabs .subtab-btn").forEach(function (b) {
      b.classList.toggle("active", b.dataset.sub === sub);
    });
    root.querySelectorAll(".sub-panel").forEach(function (p) { p.hidden = p.dataset.sub !== sub; });
    ensure(sub);
  }
  function visible() {
    var p = document.querySelector('.tab-panel[data-panel="funding"]');
    return p && !p.hidden;
  }
  function maybeLoad() { if (visible()) ensure("won"); }

  function boot() {
    var bar = document.getElementById("funding-subtabs");
    if (bar) bar.addEventListener("click", function (e) {
      var btn = e.target.closest(".subtab-btn");
      if (btn) activateSub(btn.dataset.sub);
    });
    maybeLoad();
    var tabs = document.getElementById("main-tabs");
    if (tabs) tabs.addEventListener("click", function () { setTimeout(maybeLoad, 0); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
