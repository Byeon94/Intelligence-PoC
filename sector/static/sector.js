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
  // 반도체(업종 1개가 전체의 절반 이상)처럼 극단적으로 쏠린 분포에서 업종 20여 개를 전부
  // 펼치면, 세로를 아무리 늘려도 꼬리 쪽 업종들은 한 칸 너비가 라벨 표시 기준(60px)에
  // 못 미치는 좁은 격자가 되어 대부분 빈 칸으로 보인다. 상위 업종만 개별로 보여주고
  // 나머지는 하나로 묶어서, 화면에 보이는 칸 수 자체를 줄인다(표시 전용 — 순위표는 그대로
  // 원본 sectors 를 쓴다).
  var MAX_TREEMAP_ITEMS = 9;

  function forTreemapDisplay(sectors) {
    if (sectors.length <= MAX_TREEMAP_ITEMS) return sectors;
    var sorted = sectors.slice().sort(function (a, b) { return (b.market_cap || 0) - (a.market_cap || 0); });
    var head = sorted.slice(0, MAX_TREEMAP_ITEMS - 1);
    var rest = sorted.slice(MAX_TREEMAP_ITEMS - 1);
    var restCap = rest.reduce(function (a, s) { return a + (s.market_cap || 0); }, 0);
    var restChgW = rest.reduce(function (a, s) { return a + (s.change_pct == null ? 0 : s.change_pct * (s.market_cap || 0)); }, 0);
    head.push({
      sector: "그 외 " + rest.length + "개 업종",
      market_cap: restCap,
      change_pct: restCap ? restChgW / restCap : null,
      top_name: null
    });
    return head;
  }

  function renderTreemap(box, sectors) {
    if (!box) return;
    var display = forTreemapDisplay(sectors);
    var total = display.reduce(function (a, s) { return a + (s.market_cap || 0); }, 0);
    if (!total) { box.innerHTML = '<div class="chart-error">표시할 데이터가 없습니다</div>'; return; }
    var scale = (TW * TH) / total;
    var rects = squarify(display.map(function (s) { return (s.market_cap || 0) * scale; }), { x: 0, y: 0, w: TW, h: TH });
    box.innerHTML = "";
    // 라벨 표시 여부는 실제 렌더 픽셀 크기로 판단한다(로직 좌표 기준으로만 재면, 모바일처럼
    // 컨테이너 자체가 좁을 때 작은 칸에도 글씨를 넣으려다 겹쳐 보이는 문제가 있었다).
    var boxW = box.clientWidth || 320, boxH = box.clientHeight || boxW * 0.75;
    display.forEach(function (s, idx) {
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
      var pxW = (r.w / TW) * boxW, pxH = (r.h / TH) * boxH;
      // 실제 텍스트가 CSS에서 nowrap+ellipsis 처리되므로, 조금 좁아도(2~3글자만 보여도)
      // 아예 안 보이는 것보단 낫다고 보고 기준을 낮춰뒀다.
      if (pxW > 44 && pxH > 30) {
        div.innerHTML =
          '<div class="st-name">' + esc(s.sector) + "</div>" +
          '<div class="st-sub">' + jo(s.market_cap) + "조</div>" +
          (chg != null ? '<div class="st-chg ' + chgClass(chg) + '">' + chgText(chg) + "</div>" : "");
      }
      div.title = s.sector + " — 시가총액 " + jo(s.market_cap) + "조원" + (chg != null ? " · 등락 " + chg.toFixed(2) + "%" : "");
      box.appendChild(div);
    });
  }

  var RANK_LIMIT = 5;

  // total 을 안 넘기면(과거 호출부 호환) 보여지는 업종들의 합으로 대체한다 — 이 경우 "기타"처럼
  // 화면엔 안 보이지만 실제 전체 시가총액에는 포함되는 항목의 비중까지는 못 담는다.
  function renderRankTable(box, sectors, total) {
    if (!box) return;
    var grandTotal = total || sectors.reduce(function (a, s) { return a + (s.market_cap || 0); }, 0);
    var expanded = false;
    function rowHTML(s, i) {
      var pct = grandTotal ? (s.market_cap || 0) / grandTotal * 100 : 0;
      return "<tr><td>" + (i + 1) + ". " + esc(s.sector) + "</td>" +
        "<td><div class=\"rank-share\"><span class=\"rank-share-bar\"><span style=\"width:" +
        Math.min(100, pct).toFixed(2) + "%\"></span></span><span class=\"rank-share-pct\">" +
        pct.toFixed(2) + "%</span></div></td>" +
        "<td>" + jo(s.market_cap) + "조원</td>" +
        '<td class="' + chgClass(s.change_pct) + '">' + chgText(s.change_pct) + "</td>" +
        "<td>" + esc(s.top_name || "-") + "</td></tr>";
    }
    function draw() {
      var shown = expanded ? sectors : sectors.slice(0, RANK_LIMIT);
      var html =
        (grandTotal ? '<div class="sector-rank-total">전체 업종 시가총액 <b>' + jo(grandTotal) + "조원</b></div>" : "") +
        "<table class=\"rate-table sector-rank\"><thead><tr><th>업종</th><th>비중</th><th>시가총액</th><th>등락률</th><th>대표 종목</th></tr></thead><tbody>" +
        shown.map(rowHTML).join("") + "</tbody></table>";
      if (sectors.length > RANK_LIMIT) {
        html += '<button type="button" class="lead-more-btn">' +
          (expanded ? "접기 ▲" : "더보기 (전체 " + sectors.length + "개) ▼") + "</button>";
      }
      box.innerHTML = html;
      var btn = box.querySelector(".lead-more-btn");
      if (btn) btn.addEventListener("click", function () { expanded = !expanded; draw(); });
    }
    draw();
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
        renderRankTable(rankBox, d.sectors || [], d.total_market_cap);
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
