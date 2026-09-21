/* 국내 업종별 시가총액 맵 및 밸류체인 — 트리맵(squarified) + 밸류체인 다이어그램.
 * window.SectorWidget 으로 렌더 함수를 공개해, 독립 페이지(/sector)와 홈(main/static/home.js)의
 * "내 위젯" 인라인 카드가 같은 렌더 로직을 공유한다(중복 구현 방지). */
(function (global) {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function get(url) {
    return fetch(url).then(function (r) {
      return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "요청 실패"); return j; });
    });
  }
  function jo(v) { return v == null ? "-" : (Math.round(v / 1e11) / 10); }
  function chgClass(chg) { return chg == null ? "" : (chg > 0 ? "st-c-up" : chg < 0 ? "st-c-down" : ""); }
  function chgText(chg) {
    if (chg == null) return "-";
    return (chg > 0 ? "▲" : chg < 0 ? "▼" : "") + Math.abs(chg).toFixed(2) + "%";
  }
  function closeText(v) { return v == null ? "-" : Number(v).toLocaleString("ko-KR") + "원"; }

  /* ── squarified treemap: values(합=rect.w*rect.h 로 스케일된 값) → {x,y,w,h}[] (입력 순서 유지) ── */
  function sum(row) { return row.reduce(function (a, it) { return a + it.v; }, 0); }
  function worst(row, side) {
    var s = sum(row);
    if (!s) return Infinity;
    var vals = row.map(function (it) { return it.v; });
    var rmax = Math.max.apply(null, vals), rmin = Math.min.apply(null, vals);
    var s2 = s * s, side2 = side * side;
    return Math.max((side2 * rmax) / s2, s2 / (side2 * rmin));
  }
  function squarify(values, rect) {
    var remaining = values.map(function (v, i) { return { v: v, i: i }; });
    var r = { x: rect.x, y: rect.y, w: rect.w, h: rect.h };
    var result = [];
    while (remaining.length) {
      var shortSide = Math.min(r.w, r.h);
      var row = [remaining[0]];
      var rest = remaining.slice(1);
      while (rest.length && worst(row, shortSide) >= worst(row.concat([rest[0]]), shortSide)) {
        row.push(rest[0]);
        rest = rest.slice(1);
      }
      var rowSum = sum(row);
      if (r.w >= r.h) {
        var colW = rowSum / r.h;
        var yy = r.y;
        row.forEach(function (it) {
          var hh = it.v / colW;
          result.push({ i: it.i, x: r.x, y: yy, w: colW, h: hh });
          yy += hh;
        });
        r = { x: r.x + colW, y: r.y, w: r.w - colW, h: r.h };
      } else {
        var rowH = rowSum / r.w;
        var xx = r.x;
        row.forEach(function (it) {
          var ww = it.v / rowH;
          result.push({ i: it.i, x: xx, y: r.y, w: ww, h: rowH });
          xx += ww;
        });
        r = { x: r.x, y: r.y + rowH, w: r.w, h: r.h - rowH };
      }
      remaining = rest;
    }
    result.sort(function (a, b) { return a.i - b.i; });
    return result;
  }

  var TW = 1000, TH = 600; // 트리맵 계산용 논리 좌표(가로세로 비율은 CSS aspect-ratio가 담당)

  function renderTreemap(box, sectors) {
    if (!box) return;
    var total = sectors.reduce(function (a, s) { return a + (s.market_cap || 0); }, 0);
    if (!total) { box.innerHTML = '<div class="chart-error">표시할 데이터가 없습니다</div>'; return; }
    var scale = (TW * TH) / total;
    var rects = squarify(sectors.map(function (s) { return (s.market_cap || 0) * scale; }), { x: 0, y: 0, w: TW, h: TH });
    box.innerHTML = "";
    sectors.forEach(function (s, idx) {
      var r = rects[idx];
      var chg = s.change_pct;
      var dirClass = chg == null ? "st-flat" : chg > 0 ? "st-up" : chg < 0 ? "st-down" : "st-flat";
      var div = document.createElement("div");
      div.className = "st-box " + dirClass;
      var alpha = chg == null ? 0 : Math.min(0.55, 0.12 + Math.abs(chg) * 0.06);
      div.style.setProperty("--st-a", alpha.toFixed(2));
      div.style.left = (r.x / TW) * 100 + "%";
      div.style.top = (r.y / TH) * 100 + "%";
      div.style.width = (r.w / TW) * 100 + "%";
      div.style.height = (r.h / TH) * 100 + "%";
      if (r.w > 55 && r.h > 34) {
        div.innerHTML =
          '<div class="st-name">' + esc(s.sector) + "</div>" +
          '<div class="st-sub">' + jo(s.market_cap) + "조 · " + esc(s.top_name || "") + "</div>" +
          (chg != null ? '<div class="st-chg ' + chgClass(chg) + '">' + chgText(chg) + "</div>" : "");
      }
      div.title = s.sector + " — 시가총액 " + jo(s.market_cap) + "조원" + (chg != null ? " · 등락 " + chg.toFixed(2) + "%" : "");
      box.appendChild(div);
    });
  }

  function renderRankTable(box, sectors) {
    if (!box) return;
    var rows = sectors.map(function (s, i) {
      return "<tr><td>" + (i + 1) + ". " + esc(s.sector) + "</td>" +
        "<td>" + jo(s.market_cap) + "조원</td>" +
        '<td class="' + chgClass(s.change_pct) + '">' + chgText(s.change_pct) + "</td>" +
        "<td>" + esc(s.top_name || "-") + "</td></tr>";
    }).join("");
    box.innerHTML =
      "<table class=\"rate-table sector-rank\"><thead><tr><th>업종</th><th>시가총액</th><th>등락률</th><th>대표 종목</th></tr></thead><tbody>" +
      rows + "</tbody></table>";
  }

  /* ── 업종별 밸류체인 ── */
  function companyRowHTML(co) {
    // 주가(종가)는 기본 글자색으로 두고, 등락률만 상승/하락 색으로 구분한다.
    return (
      '<div class="vc-company">' +
        '<div class="vc-co-name">' + esc(co.name) + "</div>" +
        '<div class="vc-co-right">' +
          '<span class="vc-co-close">' + closeText(co.close) + "</span>" +
          '<span class="vc-co-chg ' + chgClass(co.change_pct) + '">' + chgText(co.change_pct) + "</span>" +
        "</div>" +
      "</div>"
    );
  }
  function renderValueChain(box, chain, asOf) {
    if (!box || !chain) return;
    var stagesHTML = chain.stages.map(function (stage, si) {
      var companiesHTML = stage.companies.map(companyRowHTML).join("");
      var stageHTML = '<div class="vc-stage vc-stage-c' + (si % 6) + '"><div class="vc-stage-name">' +
        esc(stage.name) + "</div>" + companiesHTML + "</div>";
      return si > 0 ? '<div class="vc-arrow">→</div>' + stageHTML : stageHTML;
    }).join("");
    box.innerHTML =
      (asOf ? '<div class="vc-asof">' + esc(asOf) + " 종가 기준</div>" : "") +
      '<div class="vc-stages">' + stagesHTML + "</div>";
  }
  function renderChainButtons(box, chains, onSelect) {
    if (!box) return;
    box.innerHTML = chains.map(function (c, i) {
      return '<button type="button" class="sub-select-btn' + (i === 0 ? " active" : "") +
        '" data-key="' + esc(c.key) + '">' + esc(c.label) + "</button>";
    }).join("");
    box.querySelectorAll(".sub-select-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        box.querySelectorAll(".sub-select-btn").forEach(function (b) { b.classList.toggle("active", b === btn); });
        onSelect(btn.dataset.key);
      });
    });
  }
  function findChain(chains, key) {
    var found = null;
    chains.forEach(function (c) { if (c.key === key) found = c; });
    return found;
  }

  function fetchMap() { return get("/api/sector/map"); }
  function fetchChains() { return get("/api/sector/value-chain"); }

  global.SectorWidget = {
    fetchMap: fetchMap,
    fetchChains: fetchChains,
    renderTreemap: renderTreemap,
    renderRankTable: renderRankTable,
    renderChainButtons: renderChainButtons,
    renderValueChain: renderValueChain,
    findChain: findChain
  };

  /* ── 독립 페이지(/sector) 전용 부트스트랩 ──
   * SPA(내 위젯) 컨텍스트에서 이 파일이 로드될 땐 #sector-subtabs 가 없어 그냥 no-op 한다
   * (내 위젯 카드는 home.js 가 위 SectorWidget API 를 직접 호출해 렌더한다). */
  function bootStandalonePage() {
    var subtabs = document.getElementById("sector-subtabs");
    if (!subtabs) return;

    function loadMap() {
      var box = document.getElementById("sector-treemap");
      var rankBox = document.getElementById("sector-rank-table");
      fetchMap().then(function (d) {
        renderTreemap(box, d.sectors || []);
        renderRankTable(rankBox, (d.sectors || []).slice(0, 10));
        var noteEl = document.getElementById("map-note");
        if (noteEl) noteEl.textContent = d.as_of ? d.as_of + " 기준" : "";
      }).catch(function (e) {
        if (box) box.innerHTML = '<div class="chart-error">' + esc(e.message) + "</div>";
        if (rankBox) rankBox.innerHTML = "";
      });
    }

    function loadChains() {
      var btnBox = document.getElementById("chain-buttons");
      var detailBox = document.getElementById("chain-detail");
      fetchChains().then(function (d) {
        var chains = d.chains || [];
        if (!chains.length) { detailBox.innerHTML = '<div class="chart-error">표시할 데이터가 없습니다</div>'; return; }
        renderChainButtons(btnBox, chains, function (key) {
          renderValueChain(detailBox, findChain(chains, key), d.as_of);
        });
        renderValueChain(detailBox, chains[0], d.as_of);
      }).catch(function (e) {
        if (detailBox) detailBox.innerHTML = '<div class="chart-error">' + esc(e.message) + "</div>";
      });
    }

    var loaded = {};
    function ensure(sub) {
      if (loaded[sub]) return;
      loaded[sub] = true;
      if (sub === "map") loadMap();
      else if (sub === "chain") loadChains();
    }
    subtabs.addEventListener("click", function (e) {
      var btn = e.target.closest(".subtab-btn");
      if (!btn) return;
      var sub = btn.dataset.sub;
      subtabs.querySelectorAll(".subtab-btn").forEach(function (b) { b.classList.toggle("active", b === btn); });
      document.querySelectorAll(".sub-panel").forEach(function (p) { p.hidden = p.dataset.sub !== sub; });
      ensure(sub);
    });
    ensure("map");
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bootStandalonePage);
  else bootStandalonePage();
})(window);
