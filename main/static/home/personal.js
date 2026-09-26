/* 나의 대시보드 — 위젯 카드, 내 위젯 목록(탭처럼 하나씩 보기), 위젯 추가 모달, AI 추천(mock),
 * 그리고 옛 링크(#gallery) 호환용 전사 위젯 갤러리. */
(function (K, H) {
  "use strict";

  var esc = K.esc;

  // 아래 위젯들은 "자세히 보기"가 가리키는 곳이 위젯 내용과 안 맞거나(외부 검색
  // 결과로 이동 등) 카드 안에 이미 내용이 다 보여 detail 이동 자체가 불필요해
  // 갤러리·내 위젯 모두에서 버튼을 없앤다.
  var NO_DETAIL_IDS = ["market-reports", "it-news", "credit-equity-glance", "sector-map"];

  // 내부 업무 화면이 있으면 SPA 내 이동, 없으면(externalUrl) 새 탭으로 외부 원문 링크.
  // externalUrl 은 카탈로그 상수(내부 경로 "/sector" 포함)라 safeUrl 대신 esc 만 한다.
  function actionButtonHTML(w) {
    if (w.externalUrl) {
      return '<a class="dart-btn gal-open" href="' + esc(w.externalUrl) + '" target="_blank" rel="noopener">자세히 보기 →</a>';
    }
    return '<button type="button" class="dart-btn gal-open" data-work="' + esc(w.tab) + '"' +
      (w.sub ? ' data-sub="' + esc(w.sub) + '"' : "") + '>자세히 보기 →</button>';
  }

  // ── 카드(갤러리·위젯 추가 모달 / 내 위젯 공용) ──
  // opts.mini: 내 위젯 전용 — 있으면 실데이터 미리보기 영역을 넣고 "내 위젯에 추가" 토글 대신
  // "그만보기"(제거) 버튼을 보여준다. 제거해도 위젯 추가 목록에서는 다시 "+ 추가"로 보인다.
  function galCardHTML(w, opts) {
    opts = opts || {};
    if (opts.mini && w.id === "credit-equity-glance") return H.creditGlanceCardHTML(w);
    if (opts.mini && w.id === "sector-map") return H.sectorMapCardHTML(w);
    var mine = H.isMine(w.id);
    var miniHTML = (opts.mini && H.MINI_LOADERS[w.id])
      ? '<div class="gal-mini" id="mini-' + w.id + '"><span class="page-note">불러오는 중…</span></div>'
      : "";
    var toggleHTML = opts.mini
      ? '<button type="button" class="gal-remove" data-id="' + w.id + '">✕ 그만보기</button>'
      : '<button type="button" class="gal-toggle' + (mine ? " active" : "") + '" data-id="' + w.id + '">' +
        (mine ? "✓ 나의 대시보드에 추가됨" : "+ 나의 대시보드에 추가") +
      "</button>";
    var showActionBtn = NO_DETAIL_IDS.indexOf(w.id) < 0;
    return (
      '<div class="gal-card">' +
        '<div class="gal-top">' +
          '<span class="gal-emoji">' + w.emoji + "</span>" +
          '<span class="gal-badges">' + H.statusBadgesHTML(w) + "</span>" +
        "</div>" +
        '<div class="gal-title">' + esc(w.title) + "</div>" +
        '<div class="gal-desc">' + esc(w.desc) + "</div>" +
        miniHTML +
        '<div class="gal-actions">' +
          (showActionBtn ? actionButtonHTML(w) : "") +
          toggleHTML +
        "</div>" +
      "</div>"
    );
  }

  function bindGalleryCardEvents(scope) {
    // data-work 가 있는(=내부 화면으로 이동하는) 버튼만 SPA 네비게이션을 건다.
    // externalUrl 카드는 <a href target=_blank> 자체로 동작하므로 별도 바인딩 불필요.
    scope.querySelectorAll(".gal-open[data-work]").forEach(function (btn) {
      btn.addEventListener("click", function () { H.goWork(btn.dataset.work, btn.dataset.sub); });
    });
    scope.querySelectorAll(".gal-toggle").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var mine = H.toggleMyWidget(btn.dataset.id).indexOf(btn.dataset.id) >= 0;
        btn.classList.toggle("active", mine);
        btn.textContent = mine ? "✓ 나의 대시보드에 추가됨" : "+ 나의 대시보드에 추가";
      });
    });
    // "그만보기"(내 위젯 전용) — 제거 후 목록을 다시 맞춰 카드가 즉시 사라지게 한다.
    // 위젯 추가 목록의 "+ 추가" 버튼은 열 때마다 H.isMine() 기준으로 다시 그려지므로
    // 자동으로 원상복구된다(별도 처리 불필요).
    scope.querySelectorAll(".gal-remove").forEach(function (btn) {
      btn.addEventListener("click", function () {
        H.toggleMyWidget(btn.dataset.id);
        renderPersonal();
      });
    });
  }

  // 전사 위젯 갤러리(#gallery) — 사이드바에서는 빠졌지만 옛 링크·/sector 페이지의
  // "← 전사 위젯" 링크 호환을 위해 화면은 남겨둔다.
  function renderGallery() {
    var box = document.getElementById("gallery-grid");
    if (!box) return;
    box.innerHTML = H.galItemsForCatalog().map(function (w) { return galCardHTML(w); }).join("");
    bindGalleryCardEvents(box);
  }

  function personalAnchorId(id) { return "personal-w-" + id; }

  // 위젯을 여러 개 담으면 한 화면에 다 쌓여 복잡해지니, 제목 칩을 탭처럼 써서
  // 한 번에 하나씩만 보여준다(선택 상태는 탭이 열려 있는 동안만 메모리로 유지).
  var personalActiveId = null;

  function renderPersonalJumpNav(items) {
    var nav = document.getElementById("personal-jump-nav");
    if (!nav) return;
    if (items.length < 2) { nav.innerHTML = ""; return; }
    nav.innerHTML = items.map(function (w) {
      return '<button type="button" class="pd-jump-chip' + (w.id === personalActiveId ? " active" : "") +
        '" data-id="' + esc(w.id) + '">' + w.emoji + " " + esc(w.title) + "</button>";
    }).join("");
    nav.querySelectorAll(".pd-jump-chip").forEach(function (chip) {
      chip.addEventListener("click", function () {
        personalActiveId = chip.dataset.id;
        showPersonalWidget(personalActiveId);
        nav.querySelectorAll(".pd-jump-chip").forEach(function (c) {
          c.classList.toggle("active", c === chip);
        });
      });
    });
  }

  function showPersonalWidget(id) {
    document.querySelectorAll(".pd-widget-anchor").forEach(function (el) {
      el.hidden = el.id !== personalAnchorId(id);
    });
  }

  // 나의 대시보드 방문·모달 닫기·그만보기 때마다 불린다. 카드를 매번 새로 그리면 위젯이
  // 초기화되고(예: 기업분석 위젯이 삼성전자로 돌아감) 전부 다시 불러오므로, 이미 있는 카드는
  // 그대로 두고 새로 담은 위젯 카드만 추가·초기화하고, 뺀 위젯 카드만 지운다.
  function renderPersonal() {
    var box = document.getElementById("personal-grid");
    if (!box) return;
    var ids = H.getMyWidgetIds();
    var items = H.WIDGET_CATALOG.filter(function (w) { return ids.indexOf(w.id) >= 0; });

    box.querySelectorAll(".pd-widget-anchor").forEach(function (el) {
      if (ids.indexOf(el.dataset.id) < 0) el.remove();
    });
    if (!items.length) {
      personalActiveId = null;
      renderPersonalJumpNav(items);
      // 상단 헤더의 "+ 위젯 추가" 버튼과 소개 문구가 이미 안내하므로 빈 채로 둔다.
      return;
    }
    // 이전에 선택했던 위젯이 아직 있으면 유지, 없으면(처음이거나 방금 제거됐으면) 첫 위젯으로.
    if (!items.some(function (w) { return w.id === personalActiveId; })) {
      personalActiveId = items[0].id;
    }

    var added = [];
    items.forEach(function (w, i) {
      var el = document.getElementById(personalAnchorId(w.id));
      if (!el) {
        var tmp = document.createElement("div");
        tmp.innerHTML = '<div class="pd-widget-anchor" id="' + personalAnchorId(w.id) + '" data-id="' + esc(w.id) + '">' +
          galCardHTML(w, { mini: true }) + "</div>";
        el = tmp.firstChild;
        added.push({ w: w, el: el });
      }
      // 카탈로그 순서 유지 — 기존 카드는 필요할 때만 자리를 옮긴다(내용·상태는 그대로).
      if (box.children[i] !== el) box.insertBefore(el, box.children[i] || null);
    });
    showPersonalWidget(personalActiveId);
    renderPersonalJumpNav(items);

    added.forEach(function (a) {
      bindGalleryCardEvents(a.el);
      if (a.w.id === "credit-equity-glance") H.initCreditGlanceSearch(a.el.querySelector(".gal-card-glance"));
      else if (a.w.id === "sector-map") H.initSectorMapWidget();
    });
    H.loadMiniPreviews(added.map(function (a) { return a.w; }));
  }

  // ── 위젯 추가 모달 ── "전사 위젯/부서 위젯" 같은 내부 용어 대신, 실제 있는 구분(담당자가
  // 직접 만든 위젯 vs 자본시장 정보)만 자연어로 묶어 보여준다(없는 "인기순위"는 지어내지 않음).
  function waGroupHTML(title, items) {
    if (!items.length) return "";
    return (
      '<div class="wa-group"><div class="wa-group-title">' + esc(title) + "</div>" +
      items.map(function (w) { return galCardHTML(w); }).join("") +
      "</div>"
    );
  }
  function renderWidgetAddModal(query) {
    var body = document.getElementById("wa-body");
    if (!body) return;
    var all = H.galItemsForCatalog();
    var q = (query || "").trim().toLowerCase();
    var filtered = q ? all.filter(function (w) {
      return (w.title + " " + w.desc).toLowerCase().indexOf(q) >= 0;
    }) : all;
    var madeByStaff = filtered.filter(function (w) { return !!w.creditBadge; });
    var capitalInfo = filtered.filter(function (w) { return w.tab === "capital"; });
    var rest = filtered.filter(function (w) {
      return madeByStaff.indexOf(w) < 0 && capitalInfo.indexOf(w) < 0;
    });
    var html =
      waGroupHTML("✍️ 담당자가 직접 만든 위젯", madeByStaff) +
      waGroupHTML("📈 자본시장 정보", capitalInfo) +
      waGroupHTML("그 밖의 위젯", rest);
    body.innerHTML = html || '<div class="page-note">검색 결과가 없습니다.</div>';
    bindGalleryCardEvents(body);
  }
  function openWidgetAddModal() {
    var modal = document.getElementById("widget-add-modal");
    if (!modal) return;
    var search = document.getElementById("wa-search");
    if (search) search.value = "";
    renderWidgetAddModal("");
    modal.hidden = false;
    document.body.style.overflow = "hidden";
  }
  function closeWidgetAddModal() {
    var modal = document.getElementById("widget-add-modal");
    if (modal) modal.hidden = true;
    document.body.style.overflow = "";
    renderPersonal(); // 모달에서 추가/제거한 결과를 나의 대시보드에 바로 반영
  }

  // ── AI가 추천하기(mock) ── 실제 개인화 백엔드가 없어, 선택한 업무·키워드를 위젯
  // 카탈로그의 제목·설명과 단순 매칭해 추천한다(프런트 mock 플로우 — 실제 AI 판단 아님).
  var AI_ROLE_OPTIONS = ["투자금융", "리스크", "여신", "자금", "영업", "기타"];
  var AI_ROLE_MATCH = {
    "투자금융": ["sector-map", "capital-issuance", "market-reports"],
    "리스크": ["capital-liquidity", "credit-equity-glance"],
    "여신": ["credit-equity-glance", "capital-liquidity"],
    "자금": ["capital-liquidity", "capital-cma"],
    "영업": ["market-reports", "sector-map"],
    "기타": ["it-news", "sector-map"]
  };
  function aiRecommendFormHTML() {
    return (
      '<p class="page-note">주로 어떤 업무를 하시나요?</p>' +
      '<div class="ai-role-options">' +
        AI_ROLE_OPTIONS.map(function (r) {
          return '<label class="ai-role-opt"><input type="radio" name="ai-role" value="' + esc(r) + '">' + esc(r) + "</label>";
        }).join("") +
      "</div>" +
      '<p class="page-note" style="margin-top:14px">최근 관심 있는 주제나 기업이 있나요?</p>' +
      '<input type="text" class="wa-search" id="ai-keyword" placeholder="예: 2차전지, CFD, 삼성전자">' +
      '<button type="button" class="dart-btn" id="ai-run-btn" style="margin-top:14px">AI가 추천하기</button>'
    );
  }
  // 위젯별로 하나씩 "+ 추가"/"✓ 추가됨"을 토글한다(예전엔 "모두 추가" 하나뿐이라
  // 원치 않는 항목까지 한 번에 담기게 됐음). 목록 자체는 role·keyword가 바뀔 때만
  // 다시 그리고, 토글은 버튼 하나만 갱신해 리스트가 다시 그려지며 깜빡이지 않게 한다.
  function aiResultItemHTML(w) {
    var mine = H.isMine(w.id);
    return (
      '<li class="ai-result-item" data-id="' + esc(w.id) + '">' +
        '<span class="ai-result-name">' + esc(w.emoji) + " " + esc(w.title) + "</span>" +
        '<button type="button" class="gal-toggle ai-result-add' + (mine ? " active" : "") + '" data-id="' + esc(w.id) + '">' +
          (mine ? "✓ 추가됨" : "+ 추가") +
        "</button>" +
      "</li>"
    );
  }
  function aiRecommendResultHTML(role, keyword) {
    var all = H.galItemsForCatalog();
    var picked = {};
    (AI_ROLE_MATCH[role] || []).forEach(function (id) { picked[id] = true; });
    var kw = (keyword || "").trim().toLowerCase();
    if (kw) {
      all.forEach(function (w) {
        if ((w.title + " " + w.desc).toLowerCase().indexOf(kw) >= 0) picked[w.id] = true;
      });
    }
    var items = all.filter(function (w) { return picked[w.id]; });
    if (!items.length) items = all.slice(0, 3);
    return (
      '<p class="page-note">' + esc(role) + ' 업무에 맞는 위젯을 추천해드릴게요 — 원하는 위젯만 골라 추가하세요</p>' +
      '<ul class="ai-result-list">' +
        items.map(aiResultItemHTML).join("") +
      "</ul>"
    );
  }
  function bindAiRecommendForm() {
    var runBtn = document.getElementById("ai-run-btn");
    if (!runBtn) return;
    runBtn.addEventListener("click", function () {
      var checked = document.querySelector('input[name="ai-role"]:checked');
      var role = checked ? checked.value : "기타";
      var keywordEl = document.getElementById("ai-keyword");
      var body = document.getElementById("ai-body");
      body.innerHTML = aiRecommendResultHTML(role, keywordEl ? keywordEl.value : "");
    });
    var body = document.getElementById("ai-body");
    if (body && !body.dataset.bound) {
      body.dataset.bound = "1";
      body.addEventListener("click", function (e) {
        var btn = e.target.closest(".ai-result-add");
        if (!btn) return;
        var mine = H.toggleMyWidget(btn.dataset.id).indexOf(btn.dataset.id) >= 0;
        btn.classList.toggle("active", mine);
        btn.textContent = mine ? "✓ 추가됨" : "+ 추가";
      });
    }
  }
  function openAiRecommendModal() {
    var modal = document.getElementById("ai-recommend-modal");
    if (!modal) return;
    var body = document.getElementById("ai-body");
    if (body) body.innerHTML = aiRecommendFormHTML();
    bindAiRecommendForm();
    modal.hidden = false;
    document.body.style.overflow = "hidden";
  }
  function closeAiRecommendModal() {
    var modal = document.getElementById("ai-recommend-modal");
    if (modal) modal.hidden = true;
    document.body.style.overflow = "";
    renderPersonal();
  }

  // 정적 버튼(모달 열기/닫기/검색)은 페이지 로드 시 한 번만 바인딩한다.
  function on(id, type, fn) {
    var el = document.getElementById(id);
    if (el) el.addEventListener(type, fn);
    return el;
  }
  on("personal-add-widget-btn", "click", openWidgetAddModal);
  on("wa-close-btn", "click", closeWidgetAddModal);
  on("wa-backdrop", "click", closeWidgetAddModal);
  var waSearchInput = on("wa-search", "input", function () { renderWidgetAddModal(waSearchInput.value); });
  on("personal-ai-recommend-btn", "click", openAiRecommendModal);
  on("ai-close-btn", "click", closeAiRecommendModal);
  on("ai-backdrop", "click", closeAiRecommendModal);
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    var wa = document.getElementById("widget-add-modal");
    var ai = document.getElementById("ai-recommend-modal");
    if (wa && !wa.hidden) closeWidgetAddModal();
    if (ai && !ai.hidden) closeAiRecommendModal();
  });

  H.renderGallery = renderGallery;
  H.renderPersonal = renderPersonal;
})(window.KSFC, window.KSFC.home);
