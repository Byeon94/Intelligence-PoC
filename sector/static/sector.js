/* 국내 업종별 순위 및 밸류체인 — 업종 순위표 + 밸류체인 다이어그램.
 * window.SectorWidget 으로 렌더 함수를 공개해, 독립 페이지(/sector)와 홈(main/static/home.js)의
 * "내 위젯" 인라인 카드가 같은 렌더 로직을 공유한다(중복 구현 방지).
 * 시가총액 트리맵 맵은 모바일에서 레이아웃이 깨져 기능을 제거했다. */
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
    renderRankTable: renderRankTable,
    renderChainButtons: renderChainButtons,
    renderValueChain: renderValueChain,
    findChain: findChain
  };

  /* ── 독립 페이지(/sector) 전용 부트스트랩 ──
   * SPA(내 위젯) 컨텍스트에서 이 파일이 로드될 땐 #sector-rank-table 이 없어 그냥 no-op 한다
   * (내 위젯 카드는 home.js 가 위 SectorWidget API 를 직접 호출해 렌더한다). */
  function bootStandalonePage() {
    var rankBox = document.getElementById("sector-rank-table");
    if (!rankBox) return;

    fetchMap().then(function (d) {
      renderRankTable(rankBox, d.sectors || [], d.total_market_cap);
      var noteEl = document.getElementById("map-note");
      if (noteEl) noteEl.textContent = d.as_of ? d.as_of + " 기준" : "";
    }).catch(function (e) {
      rankBox.innerHTML = '<div class="chart-error">' + esc(e.message) + "</div>";
    });

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

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bootStandalonePage);
  else bootStandalonePage();
})(window);
