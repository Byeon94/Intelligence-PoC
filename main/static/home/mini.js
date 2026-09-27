/* 나의 대시보드 위젯 카드 안의 "미니 미리보기" — 위젯마다 가벼운 실데이터를 카드 안에 바로
 * 보여준다. 공용 포맷터·HTML 조각(H.jo/H.miniRow 등)은 stock-glance.js 도 같이 쓴다. */
(function (K, H) {
  "use strict";

  var esc = K.esc, get = K.get;

  // ── 포맷터 ──
  function jo(v) { return v == null ? "-" : (Math.round(v * 10) / 10).toLocaleString("ko-KR", { maximumFractionDigits: 1 }) + "조"; }
  // 재무요약 표: 무조건 조 단위로 맞추면 조 미만 규모 기업은 "0.0조"처럼 실제 크기가
  // 사라져 버린다 — 1조 이상이면 조(0.1조 단위), 미만이면 억(1억 단위)으로 자동 전환한다.
  function finWon(v) {
    if (v == null) return "-";
    var abs = Math.abs(v);
    if (abs >= 1e12) return jo(v / 1e12);
    return Math.round(v / 1e8).toLocaleString("ko-KR") + "억";
  }
  // 실적분석 차트의 축 단위 — 표와 같은 이유로, 여러 계열 중 최댓값 기준으로 조/억 중 고른다.
  function finChartUnit(seriesList) {
    var max = 0;
    seriesList.forEach(function (arr) {
      (arr || []).forEach(function (v) { if (v != null) max = Math.max(max, Math.abs(v)); });
    });
    return max >= 1e12 ? { div: 1e12, label: "조원" } : { div: 1e8, label: "억원" };
  }
  function mktNameShort(m) {
    return m === "KOSDAQ" ? "코스닥" : m === "KOSPI" ? "코스피" : (m || "");
  }
  function bulletsFromBriefing(b) {
    if (!b) return [];
    var arr = Array.isArray(b) ? b.slice() : String(b).split("\n");
    return arr.map(function (l) { return l.replace(/^\s*[-•*]\s*/, "").trim(); })
      .filter(Boolean).slice(0, 3);
  }

  // ── HTML 조각 ──
  function asOfLine(asOf) {
    return asOf ? '<div class="gal-mini-asof">' + esc(asOf) + ' 기준</div>' : "";
  }
  function miniSubtitle(t) {
    return '<div class="gal-mini-subtitle">' + esc(t) + "</div>";
  }
  function miniRow(pairs) {
    return '<div class="gal-mini-row">' + pairs.map(function (p) {
      var cls = p[2] ? " " + p[2] : "";
      return '<div class="gal-mini-item"><span class="gmi-label">' + esc(p[0]) + '</span>' +
        '<span class="gmi-value' + cls + '">' + esc(String(p[1])) + '</span></div>';
    }).join("") + "</div>";
  }
  function miniRateTable(rows) {
    if (!rows.length) return '<div class="gal-mini-note">금리 정보가 없습니다.</div>';
    return '<table class="gal-mini-table"><thead><tr><th>증권사</th><th>RP형</th><th>발행어음형</th></tr></thead><tbody>' +
      rows.map(function (r) {
        return "<tr><td>" + esc(r.company) + "</td><td>" +
          (r.rp_rate != null ? r.rp_rate.toFixed(2) + "%" : "-") + "</td><td>" +
          (r.note_rate != null ? r.note_rate.toFixed(2) + "%" : "-") + "</td></tr>";
      }).join("") + "</tbody></table>";
  }
  // rows: [{label, values, fmt}] — fmt 결과는 숫자 문자열이라 이스케이프 불필요.
  function finTableHTML(labels, rows) {
    return '<table class="gal-mini-table gm-ca-fin"><thead><tr><th>구분</th>' +
      labels.map(function (y) { return "<th>" + esc(y) + "</th>"; }).join("") + "</tr></thead><tbody>" +
      rows.map(function (r) {
        return "<tr><td>" + esc(r.label) + "</td>" + (r.values || []).map(function (v) {
          return "<td>" + esc(r.fmt(v)) + "</td>";
        }).join("") + "</tr>";
      }).join("") + "</tbody></table>";
  }
  function thisWeekRange() {
    var now = new Date();
    now.setHours(0, 0, 0, 0);
    var start = new Date(now); start.setDate(now.getDate() - now.getDay());
    var end = new Date(start); end.setDate(start.getDate() + 6);
    return [start, end];
  }
  function thisWeekEvents(events) {
    var range = thisWeekRange();
    return (events || []).filter(function (e) {
      if (!e.date) return false;
      var d = new Date(e.date + "T00:00:00");
      return d >= range[0] && d <= range[1];
    }).sort(function (a, b) { return a.date < b.date ? -1 : (a.date > b.date ? 1 : 0); });
  }
  function miniWeekList(events) {
    if (!events.length) return '<div class="gal-mini-note">이번 주 예정된 일정이 없습니다.</div>';
    return '<ul class="gal-mini-week">' + events.slice(0, 6).map(function (e) {
      return "<li><span class=\"gmw-date\">" + esc((e.date || "").slice(5)) + "</span>" +
        '<span class="gmw-type">' + esc(e.type || "") + "</span>" +
        '<span class="gmw-company">' + esc(e.company || "") + "</span></li>";
    }).join("") + "</ul>";
  }
  function miniBullets(bullets, note) {
    var body = (!bullets || !bullets.length)
      ? '<div class="gal-mini-note">' + esc(note || "표시할 내용이 없습니다.") + "</div>"
      : '<ul class="gal-mini-bullets">' + bullets.slice(0, 2).map(function (b) {
          return "<li>" + esc(b) + "</li>";
        }).join("") + "</ul>";
    return '<div class="gal-mini-ai"><div class="gal-mini-ai-label">🤖 AI 브리핑</div>' + body + "</div>";
  }
  // 번호 붙은 링크 목록(리포트·기사·공시 최신 5건 공용). badge 는 번호 옆 작은 라벨.
  function miniLinkList(items, toRow) {
    return '<ul class="gal-mini-reports">' + items.map(function (it, i) {
      var r = toRow(it);
      return '<li><a href="' + esc(K.safeUrl(r.url)) + '" target="_blank" rel="noopener">' +
        '<span class="gmr-no">' + (i + 1) + "</span>" +
        '<span class="gmr-broker">' + esc(r.badge || "") + "</span>" +
        '<span class="gmr-title">' + esc(r.title || "") + "</span></a></li>";
    }).join("") + "</ul>";
  }

  // 각 로더는 자신의 미리보기 영역(el)을 직접 채운다(el) => Promise.
  // 전용 레이아웃을 쓰는 위젯(credit-equity-glance, sector-map)은 각자 파일에서 처리한다.
  var MINI_LOADERS = {
    "capital-liquidity": function (el) {
      return get("/api/capital/liquidity/summary").then(function (d) {
        var it = d.items || {};
        el.innerHTML = asOfLine(d.as_of) + miniRow([
          ["예탁금", jo(it.investor_deposits && it.investor_deposits.value)],
          ["신용공여", jo(it.credit_balance && it.credit_balance.value)],
          ["CMA", jo(it.cma_balance && it.cma_balance.value)]
        ]) + '<div class="gal-mini-chart" id="' + el.id + '-chart"></div>';
        // 추이 차트는 부가 정보 — 실패해도 이미 그린 잔고 행을 지우지 않고 차트 자리만 안내한다.
        return get("/api/capital/liquidity/trend").then(function (t) {
          var chartEl = document.getElementById(el.id + "-chart");
          if (!chartEl || !window.Charts) return;
          var s = t.series || {};
          var n = 12; // 최근 1년만 (카드 공간이 작아 전체 24개월은 과함)
          window.Charts.line(chartEl, {
            labels: (t.labels || []).slice(-n),
            series: [
              { name: "예탁금", values: (s.investor_deposits || []).slice(-n), varName: "--c1" },
              { name: "신용공여", values: (s.credit_balance || []).slice(-n), varName: "--c2" },
              { name: "CMA", values: (s.cma_balance || []).slice(-n), varName: "--c3" }
            ]
          });
        }).catch(function () {
          var chartEl = document.getElementById(el.id + "-chart");
          if (chartEl) chartEl.innerHTML = '<div class="gal-mini-note">추이를 불러오지 못했습니다.</div>';
        });
      });
    },
    "capital-cma": function (el) {
      return Promise.all([get("/api/capital/cma/summary"), get("/api/capital/cma/mix"), get("/api/capital/cma/rates")]).then(function (res) {
        var summary = res[0], mix = res[1], rates = res[2];
        var it = summary.items || {};
        var top = (mix.mix || []).slice().sort(function (a, b) { return b.share - a.share; })[0] || {};
        var top5 = (rates.companies || []).slice()
          .sort(function (a, b) { return (b.rp_rate || 0) - (a.rp_rate || 0); }).slice(0, 5);
        el.innerHTML =
          miniSubtitle("CMA 잔고 현황") + asOfLine(summary.as_of) +
          miniRow([
            ["CMA 총잔고", jo(it.total && it.total.value)],
            ["RP형 잔고", jo(it.rp && it.rp.value)],
            ["발행어음형 잔고", jo(it.note && it.note.value)],
            ["RP형 최고금리", (it.rp_top_rate && it.rp_top_rate.value != null) ? it.rp_top_rate.value.toFixed(2) + "%" : "-"]
          ]) +
          miniSubtitle("CMA 유형별 비중") + asOfLine(mix.as_of) +
          '<div class="gal-mini-chart gal-mini-donut" id="' + el.id + '-donut"></div>' +
          miniSubtitle("증권사별 금리 비교") + asOfLine(rates.as_of) + miniRateTable(top5);
        var chartEl = document.getElementById(el.id + "-donut");
        if (chartEl && window.Charts) {
          window.Charts.donut(chartEl, {
            items: mix.mix,
            centerLabel: "최다 " + (top.type || ""),
            centerValue: top.share != null ? Math.round(top.share * 10) / 10 + "%" : ""
          });
        }
      });
    },
    "capital-issuance": function (el) {
      return get("/api/issuance/digest").then(function (d) {
        var c = d.counts || {};
        el.innerHTML =
          miniSubtitle((d.month_label || "이번 달") + " IPO·유상증자 캘린더 요약") + asOfLine(d.date) +
          miniRow([
            ["수요예측", c["수요예측"] || 0],
            ["청약", c["청약"] || 0],
            ["상장", c["상장"] || 0],
            ["유상증자", c["유상증자"] || 0]
          ]) +
          miniBullets(bulletsFromBriefing(d.briefing), d.briefing_note) +
          miniSubtitle("이번 주 일정") + miniWeekList(thisWeekEvents(d.events));
      });
    },
    "market-reports": function (el) {
      return get("/api/credit/market-reports").then(function (d) {
        var cc = d.category_counts || {};
        // 세부 분류(괄호 안)는 총 건수만큼 강조할 필요가 없어 더 작고 가는 글씨로 따로 감싼다
        // (miniRow는 값 전체를 esc()로 감싸 HTML을 못 끼워 넣으므로 이 줄만 직접 그린다).
        var catTxt = Object.keys(cc).sort(function (a, b) { return cc[b] - cc[a]; })
          .map(function (k) { return esc(k) + " " + esc(cc[k]); }).join(" · ");
        var totalTxt = (d.total || 0) + (d.total_capped ? "+" : "") + "건";
        var totalRow = '<div class="gal-mini-row"><div class="gal-mini-item">' +
          '<span class="gmi-label">리포트 총 건수</span>' +
          '<span class="gmi-value">' + esc(totalTxt) +
          (catTxt ? ' <span class="gmi-value-sub">(' + catTxt + ")</span>" : "") +
          "</span></div></div>";
        var html = asOfLine(d.as_of) + totalRow +
          miniBullets(d.briefing, d.briefing_note);
        var top = (d.items || []).slice(0, 5);
        if (top.length) {
          html += miniSubtitle("최근 리포트") + miniLinkList(top, function (r) {
            return { url: r.url || d.list_url, badge: r.broker, title: r.title };
          });
        }
        el.innerHTML = html;
      });
    },
    "it-news": function (el) {
      return get("/api/it-news/digest").then(function (d) {
        var html = asOfLine(d.date) + miniBullets(d.briefing, d.briefing_note);
        var top = (d.articles || []).slice(0, 5);
        if (top.length) {
          html += miniSubtitle("오늘의 기사(AI 추천)") + miniLinkList(top, function (a) {
            return { url: a.url, badge: a.keyword, title: a.title };
          });
        }
        el.innerHTML = html;
      });
    }
  };

  function loadMiniPreviews(items) {
    items.forEach(function (w) {
      var loader = MINI_LOADERS[w.id];
      var el = document.getElementById("mini-" + w.id);
      if (!loader || !el) return;
      loader(el).catch(function () {
        el.innerHTML = '<div class="gal-mini-note">불러오지 못했습니다.</div>';
      });
    });
  }

  H.jo = jo;
  H.finWon = finWon;
  H.finChartUnit = finChartUnit;
  H.mktNameShort = mktNameShort;
  H.miniSubtitle = miniSubtitle;
  H.miniRow = miniRow;
  H.finTableHTML = finTableHTML;
  H.miniLinkList = miniLinkList;
  H.MINI_LOADERS = MINI_LOADERS;
  H.loadMiniPreviews = loadMiniPreviews;
})(window.KSFC, window.KSFC.home);
