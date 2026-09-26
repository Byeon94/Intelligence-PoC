/* "국내 업종별 시가총액 순위 및 밸류체인" 위젯(나의 대시보드 전용) — 별도 페이지로 이동하지 않고
 * 카드 안에서 업종 순위(기본 5개, 더보기로 전체) + 밸류체인(버튼 선택)을 모두 보여준다.
 * 렌더 함수 자체는 sector/static/sector.js 가 window.SectorWidget 으로 공개한 것을 그대로 쓴다
 * (독립 페이지 /sector 와 중복 구현하지 않기 위함). 시가총액 트리맵 맵은 모바일에서
 * 레이아웃이 깨져 기능을 제거했다. */
(function (K, H) {
  "use strict";

  var esc = K.esc;

  H.sectorMapCardHTML = function (w) {
    var id = "mini-" + w.id;
    return (
      '<div class="gal-card gal-card-sector">' +
        '<div class="gal-top">' +
          '<span class="gal-emoji">' + w.emoji + "</span>" +
          '<span class="gal-badges">' + H.statusBadgesHTML(w) + "</span>" +
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
  };

  // 카드를 처음 만들 때 한 번만 호출한다(personal.js).
  H.initSectorMapWidget = function () {
    var SW = window.SectorWidget;
    if (!SW) return;
    var id = "mini-sector-map";
    var rankEl = document.getElementById(id + "-rank");
    var mapNoteEl = document.getElementById(id + "-map-note");
    var btnBox = document.getElementById(id + "-vc-buttons");
    var detailEl = document.getElementById(id + "-vc-detail");
    if (!rankEl) return;

    SW.fetchMap().then(function (d) {
      SW.renderRankTable(rankEl, d.sectors || [], d.total_market_cap);
      if (mapNoteEl) mapNoteEl.textContent = d.as_of ? d.as_of + " 기준" : "";
    }).catch(function (e) {
      rankEl.innerHTML = '<div class="chart-error">' + esc(e.message) + "</div>";
    });

    SW.fetchChains().then(function (d) {
      var chains = d.chains || [];
      if (!chains.length) { detailEl.innerHTML = '<div class="gal-mini-note">표시할 데이터가 없습니다.</div>'; return; }
      SW.renderChainButtons(btnBox, chains, function (key) {
        SW.renderValueChain(detailEl, SW.findChain(chains, key), d.as_of);
      });
      SW.renderValueChain(detailEl, chains[0], d.as_of);
    }).catch(function (e) {
      detailEl.innerHTML = '<div class="chart-error">' + esc(e.message) + "</div>";
    });
  };
})(window.KSFC, window.KSFC.home);
