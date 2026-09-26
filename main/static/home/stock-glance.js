/* "한눈에 보는 기업분석 정보" 위젯(나의 대시보드 전용) — 종목 검색 1번으로 기초정보·주가흐름·
 * 재무요약·실적분석·최근 공시를 한 카드 안에서 같이 보여준다. 여신 화면과는 독립적이며
 * 카드 안의 검색창이 유일한 입력 지점이다. */
(function (K, H) {
  "use strict";

  var esc = K.esc, get = K.get;

  H.creditGlanceCardHTML = function (w) {
    return (
      '<div class="gal-card gal-card-glance">' +
        '<div class="gal-top">' +
          '<span class="gal-emoji">' + w.emoji + "</span>" +
          '<span class="gal-badges">' + H.statusBadgesHTML(w) + "</span>" +
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
  };

  // 종목을 빠르게 연달아 고르면 앞 요청의 응답이 늦게 도착해 뒤 종목 화면을 덮어쓸 수 있다
  // — 요청마다 번호를 매기고, 가장 마지막 요청의 응답만 그린다.
  var glanceSeq = 0;

  function scaled(arr, div) {
    return (arr || []).map(function (v) { return v == null ? null : v / div; });
  }

  function renderGlancePreview(resultEl, code, name) {
    var seq = ++glanceSeq;
    resultEl.innerHTML = '<span class="page-note">불러오는 중…</span>';
    Promise.all([
      get("/api/credit/equity/basics?code=" + encodeURIComponent(code)),
      // 재무는 부가 정보 — 실패해도 기초정보는 그리고, 서버 메시지만 재무요약 자리에 보여준다.
      get("/api/credit/equity/financials?code=" + encodeURIComponent(code)).catch(function (e) {
        return { annual: null, note: e.message };
      }),
      get("/api/credit/equity/filings?code=" + encodeURIComponent(code)).catch(function () { return null; })
    ]).then(function (res) {
      if (seq !== glanceSeq) return; // 그 사이 다른 종목을 골랐음
      var d = res[0], fin = res[1], fil = res[2];
      var chg = d.change_pct;
      var chgUp = chg != null && chg > 0, chgDn = chg != null && chg < 0;
      var chgTxt = chg == null ? "-" : (chgUp ? "▲" : chgDn ? "▼" : "") + Math.abs(chg).toFixed(2) + "%";

      var html = '<div class="gm-ca-stockhead">' + esc(d.name || name) +
        ' <span class="mono">(' + esc(d.code || code) + ')</span>' +
        (d.market ? '<span class="eq-mkt">' + esc(H.mktNameShort(d.market)) + "</span>" : "") +
        // 원천 장애 시 서버가 샘플로 대체한 값이면 표시(실데이터로 오해하지 않게).
        (d.source === "sample" || (fin && fin.source === "sample") ? '<span class="src-badge sample">● 샘플</span>' : "") +
        "</div>";

      html += H.miniSubtitle("기초정보") + H.miniRow([
        ["종가" + (d.as_of ? "(" + d.as_of + " 기준)" : ""), d.close != null ? Number(d.close).toLocaleString("ko-KR") + "원" : "-"],
        ["등락", chgTxt, chgUp ? "k-up" : chgDn ? "k-dn" : ""],
        ["시가총액", d.market_cap != null ? H.jo(d.market_cap / 1e12) : "-"]
      ]) + H.miniRow([
        ["거래대금", d.trade_value != null ? H.jo(d.trade_value / 1e12) : "-"],
        ["거래량", d.volume != null ? Number(d.volume).toLocaleString("ko-KR") + "주" : "-"],
        ["상장주식수", d.shares != null ? Number(d.shares).toLocaleString("ko-KR") + "주" : "-"]
      ]);

      var ps = d.price_series;
      var hasPrice = ps && ps.values && ps.values.length > 1;
      if (hasPrice) {
        // 실적분석 차트 박스와 같은 크기로 보이도록 동일한 gm-ca-charts/gm-ca-chart-box 래퍼를 재사용
        html += H.miniSubtitle("주가흐름") +
          '<div class="gm-ca-charts"><div class="gm-ca-chart-box">' +
            '<div class="gm-ca-chart-label">종가(최근 120거래일, 원)</div>' +
            '<div class="gal-mini-chart" id="' + resultEl.id + '-pricechart"></div>' +
          "</div></div>";
      }

      var a = fin && fin.annual;
      var hasFin = a && a.labels && a.labels.length;
      var unit1, unit2;
      if (hasFin) {
        html += H.miniSubtitle("재무요약 (연간)") + H.finTableHTML(a.labels, [
          { label: "매출액", values: a.revenue, fmt: H.finWon },
          { label: "영업이익", values: a.operating_income, fmt: H.finWon },
          { label: "순이익", values: a.net_income, fmt: H.finWon },
          { label: "자산총계", values: a.assets, fmt: H.finWon },
          { label: "부채총계", values: a.liabilities, fmt: H.finWon },
          { label: "자본총계", values: a.equity, fmt: H.finWon }
        ]);
        unit1 = H.finChartUnit([a.revenue, a.operating_income, a.net_income]);
        unit2 = H.finChartUnit([a.liabilities, a.equity]);
        html += H.miniSubtitle("실적분석") +
          '<div class="gm-ca-charts">' +
            '<div class="gm-ca-chart-box"><div class="gm-ca-chart-label">매출액·영업이익·순이익(' + unit1.label + ')</div>' +
              '<div class="gal-mini-chart" id="' + resultEl.id + '-chart1"></div></div>' +
            '<div class="gm-ca-chart-box"><div class="gm-ca-chart-label">자산·부채·자본(' + unit2.label + ')</div>' +
              '<div class="gal-mini-chart" id="' + resultEl.id + '-chart2"></div></div>' +
          "</div>";
      } else if (fin && fin.note) {
        html += H.miniSubtitle("재무요약 (연간)") + '<div class="gal-mini-note">' + esc(fin.note) + "</div>";
      }

      var filings = (fil && fil.items || []).slice(0, 5);
      html += H.miniSubtitle("최근 공시(DART)");
      if (!filings.length) {
        html += '<div class="gal-mini-note">' + esc((fil && fil.note) || "최근 공시가 없습니다.") + "</div>";
      } else {
        html += H.miniLinkList(filings, function (it) {
          return { url: it.url, badge: it.date, title: it.title };
        });
      }
      resultEl.innerHTML = html;

      if (!window.Charts) return;
      var pc = hasPrice && document.getElementById(resultEl.id + "-pricechart");
      if (pc) {
        window.Charts.line(pc, {
          labels: ps.labels,
          series: [{ name: "종가", values: ps.values, varName: "--c1" }]
        });
      }
      if (!hasFin) return;
      var c1 = document.getElementById(resultEl.id + "-chart1");
      if (c1) {
        window.Charts.line(c1, {
          labels: a.labels,
          series: [
            { name: "매출액", values: scaled(a.revenue, unit1.div), varName: "--c1" },
            { name: "영업이익", values: scaled(a.operating_income, unit1.div), varName: "--c2" },
            { name: "순이익", values: scaled(a.net_income, unit1.div), varName: "--c5" }
          ]
        });
      }
      var c2 = document.getElementById(resultEl.id + "-chart2");
      if (c2) {
        window.Charts.stackBar(c2, {
          labels: a.labels,
          series: [
            { name: "부채", values: scaled(a.liabilities, unit2.div), varName: "--c2" },
            { name: "자본", values: scaled(a.equity, unit2.div), varName: "--c3" }
          ]
        });
      }
    }).catch(function (e) {
      if (seq !== glanceSeq) return;
      // 기초정보 404/502 는 서버의 {error} 문구(예: 종목을 찾지 못함)를 그대로 보여준다.
      resultEl.innerHTML = '<div class="gal-mini-note">' + esc((e && e.message) || "불러오지 못했습니다.") + "</div>";
    });
  }

  // 서제스트 바깥 클릭 시 닫기 — 카드마다 따로 걸지 않도록 문서에 한 번만 건다.
  document.addEventListener("click", function (e) {
    if (e.target.closest(".gm-ca-search")) return;
    document.querySelectorAll(".gm-ca-suggest").forEach(function (s) { s.hidden = true; });
  });

  // card: 방금 DOM 에 붙인 .gal-card-glance 요소. 카드를 처음 만들 때 한 번만 호출한다
  // (personal.js 가 카드를 유지하므로 재방문 시 사용자가 고른 종목이 그대로 남는다).
  H.initCreditGlanceSearch = function (card) {
    if (!card) return;
    var input = card.querySelector(".gm-ca-input");
    var sugBox = card.querySelector(".gm-ca-suggest");
    var resultEl = card.querySelector(".gm-ca-result");
    var timer = null;
    var searchSeq = 0;

    function search() {
      var q = input.value.trim();
      if (q.length < 2) { sugBox.hidden = true; return; }
      // 종목코드(영숫자 6자리, 예: 0009K0)는 대문자로 맞춰 보낸다 — 이름 검색은 그대로.
      if (/^[0-9a-z]{6}$/i.test(q)) q = q.toUpperCase();
      var seq = ++searchSeq;
      get("/api/credit/equity/search?q=" + encodeURIComponent(q)).then(function (d) {
        if (seq !== searchSeq) return;
        if (!d.items || !d.items.length) { sugBox.hidden = true; return; }
        sugBox.innerHTML = d.items.map(function (it) {
          return '<button type="button" class="eq-sug" data-code="' + esc(it.code) +
            '" data-name="' + esc(it.name) + '"><b>' + esc(it.name) + "</b> " +
            '<span class="mono">' + esc(it.code) + "</span>" +
            '<span class="eq-sug-mkt">' + esc(H.mktNameShort(it.market)) + "</span></button>";
        }).join("");
        sugBox.hidden = false;
      }).catch(function () { if (seq === searchSeq) sugBox.hidden = true; });
    }
    input.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(search, 250);
    });
    sugBox.addEventListener("click", function (e) {
      var btn = e.target.closest(".eq-sug");
      if (!btn) return;
      var code = String(btn.dataset.code || "").toUpperCase(), name = btn.dataset.name;
      input.value = name + " (" + code + ")";
      sugBox.hidden = true;
      renderGlancePreview(resultEl, code, name);
    });

    // 처음 담았을 때 빈 화면 대신 예시(삼성전자)를 바로 보여준다 — 입력창의 기본값과
    // 짝을 맞춘 코드/이름. 사용자가 검색하면 renderGlancePreview가 그대로 덮어쓴다.
    renderGlancePreview(resultEl, "005930", "삼성전자");
  };
})(window.KSFC, window.KSFC.home);
