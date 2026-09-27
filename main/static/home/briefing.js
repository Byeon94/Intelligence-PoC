/* 홈 "오늘의 브리핑" — /api/home/summary(main/home.py) 한 번으로 오늘의 핵심·시장 한눈에·
 * 오늘의 시장 브리핑·오늘의 주요뉴스를 그린다. */
(function (K, H) {
  "use strict";

  var esc = K.esc, get = K.get;

  // 날짜 "20260921" → "2026-09-21" (data.go.kr 등 원천이 하이픈 없는 basDt 형식을 줄 때).
  function fmtDate(s) {
    s = String(s || "");
    return /^\d{8}$/.test(s) ? s.slice(0, 4) + "-" + s.slice(4, 6) + "-" + s.slice(6, 8) : s;
  }

  // [data-work] 요소 → 해당 업무 화면으로 이동(오늘의 핵심 알림 카드, 주요뉴스 "더보기").
  function bindGoWorkButtons(scope) {
    scope.querySelectorAll("[data-work]").forEach(function (btn) {
      btn.addEventListener("click", function () { H.goWork(btn.dataset.work, btn.dataset.sub); });
    });
  }

  // ── 오늘의 핵심 ── AI가 먼저 골라낸 최대 3건만 보여준다(시장 브리핑 요약 → 심사·리스크
  // 공시 시그널 → 유동성 이상징후 알림 → 정책 발표 → 여신 신규 리드 → AI 선별 뉴스 기사 순으로 채워짐,
  // main/home.py get_home_summary 참고). 뉴스 feed처럼 보이지 않도록 01번은 크게
  // (+"왜 중요한가?"), 02/03은 컴팩트하게 렌더한다. 새 Gemini 호출 없음.
  // 알림 제목 뒤 "(YYYY-MM-DD 기준)" — detail 안의 날짜가 하나로 모일 때만 붙인다
  // (예: 여신 리드는 공시일·뉴스일이 다를 수 있어 그땐 detail 문구에만 둘 다 남긴다).
  function alertLineTitle(a) {
    var dates = a.detail ? (String(a.detail).match(/\d{4}-\d{2}-\d{2}/g) || []) : [];
    var one = dates.length && dates.every(function (d) { return d === dates[0]; });
    return esc(a.title) + (one ? " (" + dates[0] + " 기준)" : "");
  }
  function todayKeyCardHTML(h, rank) {
    var cat, badge, reason, dateText;
    if (h.kind === "alert") {
      cat = h.cat || "알림";
      badge = h.level === "warn" ? '<span class="hl-badge">HOT</span>' : "";
      reason = h.detail || "";
      dateText = "";
    } else if (h.kind === "policy") {
      cat = h.org || "정책";
      badge = '<span class="hl-badge">HOT</span>';
      reason = "금융당국 발표 — 관련 업무 영향 확인이 필요합니다.";
      dateText = fmtDate(h.date);
    } else if (h.kind === "market") {
      cat = "시장 브리핑";
      badge = "";
      reason = h.detail || "";
      dateText = "";
    } else {
      cat = h.tag || "일반";
      badge = "";
      reason = h.reason || "";
      dateText = fmtDate(h.date);
    }
    var primary = rank === 1;
    var reasonHTML = "";
    if (reason && primary) {
      // 모바일에서 01번 카드의 긴 설명(시장 브리핑 4줄)이 한 화면을 다 차지해, 기본은 접어두고
      // "더보기"로 펼친다(renderHighlights 에서 토글 바인딩).
      reasonHTML = '<div class="hl-reason is-collapsed">' +
        '<button type="button" class="hl-reason-toggle" aria-expanded="false">' +
          '<span class="hl-reason-label">왜 중요한가?</span><span class="hl-reason-more">더보기 ▾</span></button>' +
        '<div class="hl-reason-body">' + esc(reason) + "</div></div>";
    } else if (reason) {
      reasonHTML = '<div class="hl-reason-sm">' + esc(reason) + "</div>";
    }
    var inner =
      '<div class="hl-no">' + String(rank).padStart(2, "0") + "</div>" +
      '<div class="hl-body">' +
        '<div class="hl-top"><span class="hl-cat">' + esc(cat) + "</span>" + badge +
          (dateText ? '<span class="hl-date">' + esc(dateText) + "</span>" : "") + "</div>" +
        '<div class="hl-title">' +
          (h.kind === "alert" ? alertLineTitle(h) : esc(h.title || "")) +
        "</div>" + reasonHTML +
      "</div>";
    var cls = "hl-card" + (primary ? " hl-card-primary" : " hl-card-compact");
    if (h.kind === "alert") {
      return '<div class="' + cls + ' hl-card-btn" data-work="' + esc(h.tab || "") + '"' +
        (h.sub ? ' data-sub="' + esc(h.sub) + '"' : "") + ">" + inner + "</div>";
    }
    if (h.kind === "market") {
      // 다른 탭으로 이동하는 대신, 같은 화면 아래 "오늘의 시장 브리핑" 섹션으로 스크롤한다.
      return '<div class="' + cls + ' hl-card-btn" data-scroll="brief-briefing-block">' + inner + "</div>";
    }
    return '<a class="' + cls + '" href="' + esc(K.safeUrl(h.url)) + '" target="_blank" rel="noopener">' + inner + "</a>";
  }

  function renderHighlights(d) {
    var box = document.getElementById("brief-highlights");
    if (!box) return;
    var items = d.today_key || [];
    box.innerHTML = items.length
      ? items.map(function (h, i) { return todayKeyCardHTML(h, i + 1); }).join("")
      : '<div class="page-note">오늘은 꼭 확인할 만큼 중요한 항목이 없습니다.</div>';
    bindGoWorkButtons(box);
    // "왜 중요한가? 더보기" — 카드 자체의 클릭(탭 이동·스크롤·외부 링크)으로 번지지 않게 막는다.
    box.querySelectorAll(".hl-reason-toggle").forEach(function (t) {
      t.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        var wrap = t.parentElement;
        var collapsed = wrap.classList.toggle("is-collapsed");
        t.setAttribute("aria-expanded", collapsed ? "false" : "true");
        t.querySelector(".hl-reason-more").textContent = collapsed ? "더보기 ▾" : "접기 ▴";
      });
    });
    box.querySelectorAll("[data-scroll]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var el = document.getElementById(btn.dataset.scroll);
        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  }

  // ── 시장 한눈에 ── 국내(코스피·코스닥, data.go.kr)와 해외(다우·나스닥·S&P500, Yahoo
  // Finance 비공식 API)를 탭 전환 없이 한 화면에 같이 보여주고, 환율·금리는 그 아래 별도
  // 줄로 붙인다(지수와 단위가 달라 같은 그리드에 섞지는 않음).
  // sparkValues가 있으면 카드 안에 빈 자리(id 부여)를 만들어두고, box.innerHTML 대입
  // 이후에 window.Charts.sparkline로 채운다(SVG를 문자열로 직접 만들지 않기 위함).
  var mktSparkQueue = [];
  function mktIdxHTML(label, close, chg, sparkValues, unit) {
    var cls = chg > 0 ? "st-c-up" : chg < 0 ? "st-c-down" : "";
    var arrow = chg > 0 ? "▲" : chg < 0 ? "▼" : "";
    var chgText = chg == null ? "-" : arrow + Math.abs(chg).toFixed(2) + "%";
    var sparkHTML = "";
    if (sparkValues && sparkValues.length > 1) {
      var id = "mkt-spark-" + mktSparkQueue.length;
      mktSparkQueue.push({ id: id, values: sparkValues });
      sparkHTML = '<div class="mkt-idx-spark" id="' + id + '"></div>';
    }
    return (
      '<div class="mkt-idx"><div class="mkt-idx-name">' + esc(label) + "</div>" +
        '<div class="mkt-idx-value">' + esc(Number(close).toLocaleString("ko-KR") + (unit || "")) + "</div>" +
        '<div class="mkt-idx-chg ' + cls + '">' + chgText + "</div>" +
        sparkHTML +
      "</div>"
    );
  }
  function renderMarket(d) {
    var box = document.getElementById("brief-market");
    if (!box) return;
    var m = d.market, gm = d.global_market;
    var mh = d.market_history, gh = d.global_market_history;
    var mhLive = mh && mh.source === "live";
    var ghLive = gh && gh.source === "live";
    mktSparkQueue = [];
    var html = "";

    // 기준일 안내는 "시장 한눈에" 제목 바로 밑에 둔다 — 국내 지수가 오늘이 아닌 공공데이터
    // 기준일 값이라는 걸 카드를 보기 전에 먼저 알 수 있도록. 상단 인사말 문구에도 같은 기준일을 채운다.
    var asofBits = [];
    if (m && m.source === "live") asofBits.push(esc(fmtDate(m.as_of)) + " 기준 코스피·코스닥(공공데이터포털)");
    if (gm && gm.source === "live") asofBits.push("실시간 해외·환율·금리(Yahoo Finance, 참고용)");
    if (asofBits.length) {
      html += '<div class="page-note mkt-asof"><span class="mkt-asof-inline">' + asofBits.join(" · ") +
        '<button type="button" class="asof-info" data-msg="코스피·코스닥은 공공데이터 특성상 통계가 집계되어 제공되기까지 시간이 걸려, 화면에 표시되는 기준일이 오늘보다 며칠 늦을 수 있습니다. 해외 지수·환율·금리는 Yahoo Finance 실시간 시세로, 공식 통계가 아닌 참고용입니다. 그래프는 최근 1년 일별 종가 추이입니다." ' +
          'aria-label="기준일 안내">!</button></span></div>';
    }

    var idxCards = "";
    if (m && m.source === "live") {
      idxCards += mktIdxHTML("KOSPI", m.kospi.close, m.kospi.change_pct, mhLive && mh.kospi.values) +
        mktIdxHTML("KOSDAQ", m.kosdaq.close, m.kosdaq.change_pct, mhLive && mh.kosdaq.values);
    }
    if (gm && gm.source === "live") {
      idxCards += gm.us_indices.map(function (idx) {
        var hist = ghLive && gh[idx.name];
        return mktIdxHTML(idx.name, idx.close, idx.change_pct, hist && hist.values);
      }).join("");
    }
    if (idxCards) {
      html += '<div class="mkt-grid mkt-grid-3">' + idxCards + "</div>";
    } else {
      html += '<div class="page-note">시장 지수를 일시적으로 불러오지 못했습니다.</div>';
    }

    if (gm && gm.source === "live") {
      html += '<div class="mkt-sub-label">환율</div>' +
        '<div class="mkt-grid mkt-grid-3">' +
          gm.fx.map(function (f) { return mktIdxHTML(f.name, f.value, f.change_pct); }).join("") +
        "</div>";
    }

    // 국고채 3년물은 아직 안정적인 데이터 소스를 못 구해 표시하지 않는다(있는 척 지어내지
    // 않음). 미국채10년은 Yahoo Finance(^TNX)로 붙였다.
    if (gm && gm.source === "live" && gm.bond_us10y) {
      var bondHist = ghLive && gh.bond_us10y;
      html += '<div class="mkt-sub-label">금리</div>' +
        '<div class="mkt-grid mkt-grid-3">' +
          mktIdxHTML(gm.bond_us10y.name, gm.bond_us10y.value, gm.bond_us10y.change_pct,
            bondHist && bondHist.values, "%") +
        "</div>";
    }

    box.innerHTML = html;
    bindAsofInfo(box);
    mktSparkQueue.forEach(function (s) {
      var el = document.getElementById(s.id);
      if (el && window.Charts) window.Charts.sparkline(el, { values: s.values });
    });
  }

  // "!" 기준일 안내 아이콘 — 자본시장 탭(capital.js)과 같은 UX(클릭 시 작은 팝업)를
  // 쓰지만, 이 박스는 페이지 로드 후 fetch로 늦게 채워지므로 그때마다 새로 바인딩한다.
  var asofInfoDocBound = false;
  function closeAsofPopups() {
    document.querySelectorAll(".asof-popup").forEach(function (p) { p.remove(); });
  }
  function bindAsofInfo(scope) {
    scope.querySelectorAll(".asof-info").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        var already = btn.parentElement.querySelector(".asof-popup");
        closeAsofPopups();
        if (already) return; // 같은 버튼 다시 누르면 닫기만
        var pop = document.createElement("div");
        pop.className = "asof-popup";
        pop.textContent = btn.dataset.msg || "";
        btn.parentElement.appendChild(pop);
      });
    });
    if (!asofInfoDocBound) {
      asofInfoDocBound = true;
      document.addEventListener("click", closeAsofPopups);
    }
  }

  // ── 오늘의 시장 브리핑(AI, 주식/채권/환율/장전 4개 카테고리, 하루 1회) ──
  // 카테고리 순서·아이콘은 서버(main/home.py _CATEGORY_ICON)가 market_briefing.categories 로
  // 내려준다. 없으면(구버전 응답) 아래 기본값을 쓴다.
  var DEFAULT_BRIEFING_CATS = [
    { key: "주식", icon: "📊" },
    { key: "채권", icon: "💵" },
    { key: "환율", icon: "💱" },
    { key: "장전", icon: "🌙" }
  ];
  // 블록 제목 옆 "HH:MM 업데이트" — 서버 스냅샷 시각('YYYY-MM-DD HH:MM', KST) 기준
  function setUpdatedAt(id, stamp) {
    var el = document.getElementById(id);
    if (!el) return;
    var m = /(\d{4})-(\d{2})-(\d{2})\s+(\d{2}:\d{2})/.exec(stamp || "");
    el.textContent = m ? m[2] + "." + m[3] + " " + m[4] + " 업데이트" : "";
  }

  function renderMarketBriefing(d) {
    var box = document.getElementById("brief-briefing");
    if (!box) return;
    var mb = d.market_briefing;
    setUpdatedAt("brief-briefing-time", mb && mb.sections && mb.generated_at);
    var sections = mb && mb.sections;
    var allCats = (mb && mb.categories && mb.categories.length) ? mb.categories : DEFAULT_BRIEFING_CATS;
    var cats = sections ? allCats.filter(function (c) { return sections[c.key]; }) : [];
    if (!cats.length) {
      box.innerHTML = '<div class="page-note">' + esc((mb && mb.note) || "오늘 시장 브리핑을 아직 준비하지 못했습니다.") + "</div>";
      return;
    }
    var relMap = (mb && mb.related_articles) || {};
    box.innerHTML = '<div class="mb-grid">' + cats.map(function (c) {
      var rel = relMap[c.key];
      var relHTML = rel && rel.url && rel.title
        ? '<a class="mb-item-link" href="' + esc(K.safeUrl(rel.url)) + '" target="_blank" rel="noopener" title="' + esc(rel.title) + '">' +
            '📎 ' + esc(rel.title) + '</a>'
        : '';
      return '<div class="mb-item">' +
        '<div class="mb-item-head"><span class="mb-item-icon">' + esc(c.icon) + '</span>' +
          '<span class="mb-item-label">' + esc(c.key) + '</span></div>' +
        '<div class="mb-item-text">' + esc(sections[c.key]) + '</div>' +
        relHTML +
      '</div>';
    }).join('') + '</div>';
  }

  // ── 오늘의 주요뉴스(AI 선별 상위 5건, 전체는 뉴스 탭에서) ──
  function briefNewsRowHTML(a) {
    // 태그·제목·날짜를 한 줄에 나란히 두면 제목 칸이 좁아져 줄바꿈이 잦았다.
    // 태그+날짜는 위 메타줄로 따로 빼고, 제목은 카드 전체 너비를 쓰게 해 줄바꿈을 최소화한다.
    return (
      '<a class="brief-news-item" href="' + esc(K.safeUrl(a.url)) + '" target="_blank" rel="noopener">' +
        '<span class="bni-top">' +
          '<span class="bni-tag">' + esc(a.tag || "일반") + "</span>" +
          '<span class="bni-date">' + esc(a.published || "") + "</span>" +
        "</span>" +
        '<span class="bni-title">' + esc(a.title) + "</span>" +
      "</a>"
    );
  }
  function renderBriefNews(d) {
    var box = document.getElementById("brief-news");
    if (!box) return;
    var arts = d.today_news || [];
    var rs = d.research;
    setUpdatedAt("brief-news-time", arts.length && rs && (rs.briefing_at || rs.generated_at));
    box.innerHTML = arts.length
      ? arts.map(briefNewsRowHTML).join("")
      : '<div class="page-note">' + esc((d.research && d.research.briefing_note) || "오늘 선별된 뉴스가 없습니다.") + "</div>";
  }

  // home.html의 정적 버튼(오늘의 주요뉴스 "더보기 →")은 매번 다시 그려지지 않으니
  // 페이지 로드 시 한 번만 바인딩한다(ensureBriefing은 재시도 시 다시 불릴 수 있어
  // 거기서 바인딩하면 리스너가 중복 등록된다).
  var briefNewsMoreBtn = document.querySelector('#brief-news-block [data-work]');
  if (briefNewsMoreBtn) bindGoWorkButtons(briefNewsMoreBtn.parentElement);

  function renderGreetTitle() {
    var titleEl = document.getElementById("brief-greet-title");
    if (titleEl) titleEl.textContent = "좋은 하루입니다.";
  }

  // "오늘의 핵심" 제목 옆 업데이트 시각 — 여러 출처를 모아 만든 블록이라 단일 스냅샷 시각이
  // 없어, 홈 요약을 받아온 시각을 다른 블록과 같은 형식(MM.DD HH:MM 업데이트)으로 표시한다.
  function renderKeyUpdatedAt() {
    var now = new Date();
    function p(n) { return String(n).padStart(2, "0"); }
    setUpdatedAt("brief-greet-time", now.getFullYear() + "-" + p(now.getMonth() + 1) + "-" +
      p(now.getDate()) + " " + p(now.getHours()) + ":" + p(now.getMinutes()));
  }

  var briefingLoaded = false;
  H.ensureBriefing = function () {
    if (briefingLoaded) return;
    briefingLoaded = true;
    renderGreetTitle();
    get("/api/home/summary").then(function (d) {
      renderHighlights(d);
      renderKeyUpdatedAt();
      renderMarket(d);
      renderMarketBriefing(d);
      renderBriefNews(d);
      H.obStart(); // 브리핑 데이터가 실제 렌더된 뒤에 시작해야 스포트라이트 박스가
                   // "불러오는 중" 자리(짧음)가 아니라 실제 콘텐츠 크기에 맞는다.
    }).catch(function (e) {
      ["brief-highlights", "brief-market", "brief-briefing", "brief-news"].forEach(function (id) {
        var box = document.getElementById(id);
        if (box) box.innerHTML = '<div class="chart-error">' + esc(e.message) + "</div>";
      });
      briefingLoaded = false; // 재방문 시 재시도
      H.obStart(); // 브리핑 로딩이 실패해도 온보딩 자체는 계속 보여준다.
    });
  };
})(window.KSFC, window.KSFC.home);
