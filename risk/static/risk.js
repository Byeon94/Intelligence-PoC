/* 심사·리스크 탭: 리스크 시그널(DART 공시·급락·부정 기사) / 워치·섹터(시총 상위 30·업종지수) */
(function () {
  "use strict";

  var esc = window.KSFC.esc, get = window.KSFC.get, safeUrl = window.KSFC.safeUrl;
  var SIG_PREVIEW = 8;     // 공시 시그널은 처음 8건만, 나머지는 "더보기"
  var WATCH_PREVIEW = 10;  // 워치 유니버스는 상위 10개만, 나머지 20개는 "더보기"

  function num(n, d) {
    if (n == null || isNaN(n)) return "-";
    return Number(n).toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  function shortDate(s) {
    s = String(s || "");
    return /^\d{4}-\d{2}-\d{2}$/.test(s) ? s.slice(5).replace("-", ".") : s;
  }
  function pct(n, d) {
    if (n == null || isNaN(n)) return '<span class="risk-muted">-</span>';
    var cls = n > 0 ? "up" : n < 0 ? "down" : "";
    return '<span class="risk-chg ' + cls + '">' + (n > 0 ? "+" : "") + num(n, d == null ? 2 : d) + '%</span>';
  }
  function badge(level) {
    var cls = { ALERT: "alert", WARN: "warn", "고위험": "alert", "주의": "warn" }[level] || "ok";
    return '<span class="risk-badge ' + cls + '">' + esc(level) + '</span>';
  }
  function kpi(label, value, unit, sub, tone) {
    return '<div class="kpi' + (tone ? " risk-kpi-" + tone : "") + '">' +
      '<div class="k-label">' + esc(label) + '</div>' +
      '<div class="k-value">' + value + (unit ? '<span class="k-unit">' + esc(unit) + '</span>' : "") + '</div>' +
      (sub ? '<div class="k-sub">' + esc(sub) + '</div>' : "") + '</div>';
  }
  function el(id) { return document.getElementById(id); }
  function loading(id) { var e = el(id); if (e) e.innerHTML = '<div class="chart-loading">불러오는 중…</div>'; }
  function fail(ids, msg) {
    ids.forEach(function (id) {
      var e = el(id);
      if (e) e.innerHTML = '<div class="chart-error">' + esc(msg || "데이터를 불러오지 못했습니다") + '</div>';
    });
  }
  function count(n) { return n == null ? "-" : num(n, 0); }

  /* ── 리스크 시그널 ── */
  var sig = null, sigLevel = "", sigExpanded = false;
  var newsCount = null;

  function renderKpis() {
    if (!sig) return;
    var drops = sig.drops || {};
    el("risk-sig-kpis").innerHTML = [
      kpi("ALERT 기업", count(sig.alert_count), "곳", "상폐·회생·감사의견·거래정지 등", "alert"),
      kpi("WARN 기업", count(sig.warn_count), "곳", "관리종목·상폐 우려·불성실공시 등", "warn"),
      kpi("급락 종목", count(drops.count), "종목", drops.as_of ? shortDate(drops.as_of) + " 종가 · −8% 이하" : "−8% 이하"),
      kpi("부정 키워드 기사", count(newsCount), "건", "최근 2일 수집")
    ].join("");
  }

  function sigItemHTML(it) {
    var others = (it.others || []).map(function (o) {
      return '<li><a href="' + esc(safeUrl(o.url)) + '" target="_blank" rel="noopener">' +
        esc(shortDate(o.date)) + ' · ' + esc(o.title) + '</a></li>';
    }).join("");
    return '<div class="risk-sig ' + (it.level === "ALERT" ? "is-alert" : "is-warn") + '">' +
      '<div class="risk-sig-head">' + badge(it.level) +
        '<span class="risk-chip">' + esc(it.category) + '</span>' +
        '<span class="risk-sig-name">' + esc(it.name) + '</span>' +
        '<span class="risk-sig-market">' + esc(it.market) + '</span>' +
        '<span class="risk-sig-date">' + esc(shortDate(it.date)) + '</span></div>' +
      '<a class="risk-sig-title" href="' + esc(safeUrl(it.url)) + '" target="_blank" rel="noopener">' + esc(it.title) + ' ↗</a>' +
      '<div class="risk-sig-note">' + esc(it.note) + '</div>' +
      (others ? '<details class="risk-sig-more"><summary>관련 공시 ' + (it.count - 1) + '건 더</summary><ul>' + others + '</ul></details>' : "") +
      '</div>';
  }

  function renderSigList() {
    var box = el("risk-sig-list");
    if (!sig) return;
    if (sig.pending) {
      box.innerHTML = '<div class="page-note">' + esc(sig.note || "공시 시그널을 수집 중입니다. 잠시 후 다시 확인해주세요.") + '</div>';
      return;
    }
    var items = (sig.items || []).filter(function (it) { return !sigLevel || it.level === sigLevel; });
    if (!items.length) { box.innerHTML = '<div class="page-note">해당 기간에 리스크 공시가 없습니다.</div>'; return; }
    var shown = sigExpanded ? items : items.slice(0, SIG_PREVIEW);
    var rest = items.length - shown.length;
    box.innerHTML = '<div class="risk-sig-list">' + shown.map(sigItemHTML).join("") + '</div>' +
      (rest > 0 ? '<button type="button" class="brief-more-btn risk-more" id="risk-sig-more">더보기 (' + rest + '건)</button>' : "");
    var more = el("risk-sig-more");
    if (more) more.addEventListener("click", function () { sigExpanded = true; renderSigList(); });
  }

  function renderDrops() {
    var d = sig.drops || {};
    if (d.error) { fail(["risk-drops"], "시세 데이터를 불러오지 못했습니다"); return; }
    if (d.as_of) el("risk-drop-unit").textContent = shortDate(d.as_of) + " 종가 · −8% 이하 · 시총 1,000억 원 이상";
    var items = d.items || [];
    el("risk-drops").innerHTML = items.length
      ? '<table class="rate-table risk-table"><thead><tr><th>종목</th><th>종가</th><th>등락률</th><th>시가총액</th></tr></thead><tbody>' +
        items.map(function (s) {
          return '<tr><td><span class="risk-name">' + esc(s.name) + '</span><span class="risk-sub">' + esc(s.market) + '</span></td>' +
            '<td>' + num(s.close, 0) + '</td><td>' + pct(s.change_pct) + '</td>' +
            '<td>' + num(s.market_cap_eok, 0) + '억</td></tr>';
        }).join("") + '</tbody></table>'
      : '<div class="page-note">기준일에 조건에 해당하는 급락 종목이 없습니다.</div>';
  }

  function loadSignals() {
    ["risk-sig-kpis", "risk-sig-list", "risk-drops"].forEach(loading);
    get("/api/risk/signals").then(function (d) {
      sig = d;
      var r = d.range || {};
      // "최신 공시 09.23 · 09.27 12:19 업데이트" — 공시가 언제 것인지와 언제 새로 받아왔는지를 함께
      var latest = (d.items || []).reduce(function (m, it) { return it.date > m ? it.date : m; }, "");
      var gen = String(d.generated_at || "");
      el("risk-sig-asof").textContent = [
        latest ? "최신 공시 " + shortDate(latest) : "",
        gen ? shortDate(gen.slice(0, 10)) + " " + gen.slice(11) + " 업데이트" : "",
        d.stale ? "이전 자료" : ""
      ].filter(Boolean).join(" · ");
      if (r.from) el("risk-sig-range").textContent = "DART 거래소공시 · " + shortDate(r.from) + "~" + shortDate(r.to);
      renderKpis(); renderSigList(); renderDrops();
    }).catch(function (e) { fail(["risk-sig-kpis", "risk-sig-list", "risk-drops"], e.message); });
  }

  function loadNews() {
    loading("risk-news");
    get("/api/risk/news").then(function (d) {
      newsCount = d.candidate_count;
      renderKpis();
      el("risk-news-asof").textContent = d.picked_by === "ai" ? "AI 선별" : d.picked_by === "latest" ? "최신순" : "";
      var items = d.items || [];
      el("risk-news").innerHTML = items.length
        ? '<div class="risk-news">' + items.map(function (a) {
            return '<a class="risk-news-item" href="' + esc(safeUrl(a.url)) + '" target="_blank" rel="noopener">' +
              '<span class="risk-chip">' + esc(a.company || "뉴스") + '</span>' +
              '<span class="risk-news-body"><span class="risk-news-title">' + esc(a.title) + '</span>' +
              '<span class="risk-news-meta">' + esc(shortDate(String(a.published || "").slice(0, 10))) +
                (a.reason ? " · " + esc(a.reason) : "") + '</span></span></a>';
          }).join("") + '</div>'
        : '<div class="page-note">관련 기사를 아직 찾지 못했습니다.</div>';
    }).catch(function (e) { fail(["risk-news"], e.message); });
  }

  /* ── 워치·섹터 ── */
  var watchData = null, watchExpanded = false;
  function renderWatch(w) {
    if (w.error) { fail(["risk-watch"], w.error); return; }
    watchData = w;
    var rows = watchExpanded ? w.items : w.items.slice(0, WATCH_PREVIEW);
    var rest = w.items.length - rows.length;
    el("risk-watch-asof").textContent = shortDate(w.as_of) + " 종가 · ALERT " + w.alert + " · WARN " + w.warn + (w.stale ? " · 이전 자료" : "");
    el("risk-watch-rule").textContent = "상태 기준 — " + (w.rule || "");
    el("risk-watch").innerHTML = '<table class="rate-table risk-table risk-watch-table"><thead><tr>' +
      '<th>종목</th><th>등락률</th><th>20일</th><th class="risk-col-extra">거래량배율</th><th class="risk-col-extra">60일 변동성</th><th>상태</th></tr></thead><tbody>' +
      rows.map(function (s) {
        var vr = s.vol_ratio == null ? "-" : num(s.vol_ratio, 1) + "×";
        var vol = s.volatility60 == null ? "-" : num(s.volatility60, 0) + "%";
        return '<tr class="' + (s.status === "ALERT" ? "is-alert" : s.status === "WARN" ? "is-warn" : "") + '">' +
          '<td><span class="risk-rank">' + s.rank + '</span><span class="risk-name">' + esc(s.name) + '</span>' +
            '<span class="risk-sub">' + esc(s.market) + ' · ' + num(s.market_cap_jo, 1) + '조</span>' +
            // 모바일은 열을 줄이고 거래량배율·변동성을 종목명 아래 줄로(risk.css .risk-mob-only)
            '<span class="risk-sub risk-mob-only">거래량 ' + vr + ' · 변동성 ' + vol + '</span></td>' +
          '<td>' + pct(s.change_pct) + '</td><td>' + pct(s.ret20, 1) + '</td>' +
          '<td class="risk-col-extra">' + vr + '</td>' +
          '<td class="risk-col-extra">' + vol + '</td>' +
          '<td>' + badge(s.status) + (s.signal ? '<span class="risk-sub">DART ' + esc(s.signal) + '</span>' : "") + '</td></tr>';
      }).join("") + '</tbody></table>';
    el("risk-watch-more-box").innerHTML = rest > 0
      ? '<button type="button" class="brief-more-btn risk-more" id="risk-watch-more">더보기 (' + rest + '개)</button>' : "";
    var more = el("risk-watch-more");
    if (more) more.addEventListener("click", function () { watchExpanded = true; renderWatch(watchData); });
  }

  function renderSectors(s) {
    if (s.error) { fail(["risk-sectors"], s.error); return; }
    el("risk-sector-asof").textContent = "KRX 코스피 업종지수 · " + shortDate(s.as_of) + " 기준";
    el("risk-sector-rule").textContent = "등급 기준 — " + (s.rule || "");
    el("risk-sectors").innerHTML = s.sectors.map(function (x) {
      var cls = x.level === "고위험" ? "alert" : x.level === "주의" ? "warn" : "ok";
      return '<div class="risk-tile ' + cls + '">' +
        '<div class="risk-tile-head"><span class="risk-tile-name">' + esc(x.name) + '</span>' + badge(x.level) + '</div>' +
        '<div class="risk-tile-nums"><span>당일 ' + pct(x.d1) + '</span><span>20일 ' + pct(x.d20, 1) + '</span></div></div>';
    }).join("");
  }

  function loadWatch() {
    var ids = ["risk-watch", "risk-sectors"];
    el("risk-watch-more-box").innerHTML = "";
    ids.forEach(loading);
    get("/api/risk/watch").then(function (d) {
      renderWatch(d.watch || {}); renderSectors(d.sectors || {});
    }).catch(function (e) { fail(ids, e.message); });
  }

  /* ── 하위 탭 전환 · 지연 로딩 ── */
  var loaded = {};
  function ensure(sub) {
    if (loaded[sub]) return;
    loaded[sub] = true;
    if (sub === "signal") { loadSignals(); loadNews(); }
    else if (sub === "watch") loadWatch();
  }
  function activateSub(sub) {
    var root = el("risk-root");
    if (!root) return;
    root.querySelectorAll("#risk-subtabs .subtab-btn").forEach(function (b) {
      b.classList.toggle("active", b.dataset.sub === sub);
    });
    root.querySelectorAll(".sub-panel").forEach(function (p) { p.hidden = p.dataset.sub !== sub; });
    ensure(sub);
  }
  function visible() {
    var p = document.querySelector('.tab-panel[data-panel="risk"]');
    return p && !p.hidden;
  }
  function maybeLoad() { if (visible()) ensure("signal"); }

  function boot() {
    var bar = el("risk-subtabs");
    if (bar) bar.addEventListener("click", function (e) {
      var btn = e.target.closest(".subtab-btn");
      if (btn) activateSub(btn.dataset.sub);
    });
    var filter = el("risk-sig-filter");
    if (filter) filter.addEventListener("click", function (e) {
      var btn = e.target.closest(".risk-filter-btn");
      if (!btn) return;
      sigLevel = btn.dataset.level; sigExpanded = false;
      filter.querySelectorAll(".risk-filter-btn").forEach(function (b) { b.classList.toggle("active", b === btn); });
      renderSigList();
    });
    maybeLoad();
    var tabs = el("main-tabs");
    if (tabs) tabs.addEventListener("click", function () { setTimeout(maybeLoad, 0); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
