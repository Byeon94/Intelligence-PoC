/* 온보딩 투어 — 오늘의 브리핑의 "오늘의 핵심/시장 한눈에/오늘의 시장 브리핑/오늘의 주요뉴스"
 * 4개 영역을 소개한 뒤, 사이드바 버튼만 가리키는 대신 실제로 나의 대시보드·자본시장 화면으로
 * 이동해(step.nav) 위젯 추가·부서 화면을 직접 보여주며 설명한다(환영 화면 + 완료 화면 포함
 * 총 8스텝). 로그인이 없는 PoC라 "이 사람이 처음 왔는지"를 판단할 방법이 없어, 웹페이지를
 * 열 때마다 매번 짧게 보여준다. 사이드바는 데스크톱에선 세로, 모바일에선 상단 가로 바로
 * 바뀌므로, 스포트라이트·말풍선 위치는 매번 실제 렌더된 좌표(getBoundingClientRect)를
 * 기준으로 계산하고, 화면 밖에 있을 수 있는 대상은 먼저 scrollIntoView로 보이게 한다. */
(function (K, H) {
  "use strict";

  var esc = K.esc;

  var OB_STEPS = [
    { type: "welcome" },
    { type: "spot", sel: "#brief-key-block", titleSel: "#brief-key-block .block-head",
      title: "오늘의 핵심",
      body: "오늘 가장 먼저 확인할 곳입니다. AI가 여러 정보 중 업무에 중요한 변화를 먼저 선별해 보여드립니다." },
    { type: "spot", sel: "#brief-market-block", titleSel: "#brief-market-block .block-head",
      title: "시장 한눈에",
      body: "국내외 주요 지수와 환율을 한눈에 확인하세요." },
    { type: "spot", sel: "#brief-briefing-block", titleSel: "#brief-briefing-block .block-head",
      title: "오늘의 시장 브리핑",
      body: "매일 새벽 AI가 전영업일 마감 기준 주식·채권·환율·장전(미국시장)을 데이터로 분석해 정리합니다. 관련 기사 링크를 누르면 원문으로 바로 이동합니다." },
    { type: "spot", sel: "#brief-news-block", titleSel: "#brief-news-block .block-head",
      title: "오늘의 주요뉴스",
      body: "더 많은 뉴스가 필요하면 여기서 확인하고, \"더보기\"로 뉴스 탭에서 더 깊이 살펴볼 수 있습니다." },
    { type: "spot", nav: "personal", sel: "#personal-add-widget-btn",
      title: "나의 대시보드 — 위젯 추가",
      body: "지금처럼 기본 위젯 2개를 미리 담아드렸어요. \"+ 위젯 추가\"를 누르면 내가 자주 보는 정보만 골라 더 담아 나만의 화면을 만들 수 있습니다." },
    // 배경 화면이 "나의 대시보드"로 남아 있는 게 어색하다는 피드백 — 자본시장 탭으로
    // 실제 이동해(nav) 그 화면을 배경으로 두고, 사이드바의 부서 메뉴 4개를 가리킨다.
    { type: "spot", nav: "capital",
      selRange: ['.side-btn[data-cat="capital"]', '.side-btn[data-cat="research"]'],
      title: "업무별 메뉴(부서 위젯)",
      body: "자본시장·여신·단기자금·정책·규제·뉴스처럼 부서별 상세 화면은 여기서 바로 이동해 확인할 수 있습니다." },
    { type: "done" }
  ];
  var SPOT_STEPS = OB_STEPS.filter(function (s) { return s.type === "spot"; });
  var obIndex = 0;
  // 투어가 시작될 때 보고 있던 화면, 그리고 투어가 실제로 다른 화면으로 이동했는지.
  // 건너뛰기 시 이동한 적이 없으면 그 자리에 그대로 두고, 이동했으면 시작 화면으로 되돌린다.
  var obStartPanel = null;
  var obNavigated = false;

  function obUnionRect(el1, el2) {
    var a = el1.getBoundingClientRect(), b = el2.getBoundingClientRect();
    var top = Math.min(a.top, b.top), left = Math.min(a.left, b.left);
    var right = Math.max(a.right, b.right), bottom = Math.max(a.bottom, b.bottom);
    return { top: top, left: left, right: right, bottom: bottom, width: right - left, height: bottom - top };
  }

  function obWelcomeHTML() {
    return (
      "<h3>안녕하세요! 👋</h3>" +
      "<p>증금 인텔리전스에 오신 것을 환영합니다.<br>AI가 시장·정책·뉴스를 분석해 매일 아침 업무에 필요한 핵심만 먼저 알려드립니다.</p>" +
      '<div class="ob-tooltip-actions">' +
        '<button type="button" class="dart-btn" id="ob-next">1분 투어 시작하기 →</button>' +
        '<button type="button" class="ob-skip" id="ob-skip">건너뛰기</button>' +
      "</div>"
    );
  }
  function obDoneHTML() {
    return (
      "<h3>준비가 완료되었습니다 🎉</h3>" +
      "<p>이제 오늘의 브리핑, 나의 대시보드, 업무별 메뉴를 자유롭게 둘러보세요.</p>" +
      '<div class="ob-tooltip-actions">' +
        '<button type="button" class="dart-btn" id="ob-done-btn">오늘의 브리핑 보기 →</button>' +
      "</div>"
    );
  }
  function obSpotHTML(step) {
    var n = SPOT_STEPS.indexOf(step) + 1;
    return (
      '<div class="ob-tooltip-step">' + n + "/" + SPOT_STEPS.length + "</div>" +
      "<h3>" + esc(step.title) + "</h3>" +
      "<p>" + esc(step.body) + "</p>" +
      '<div class="ob-tooltip-actions">' +
        '<button type="button" class="ob-skip" id="ob-skip">건너뛰기</button>' +
        '<button type="button" class="dart-btn" id="ob-next">다음 →</button>' +
      "</div>"
    );
  }
  // 말풍선이 항상 뷰포트 안에 완전히 보이도록 가로·세로 모두 clamp한다. 데스크톱
  // 폭에서도 스포트라이트 대상이 화면 오른쪽 끝 가까이 있으면(예: 폭 넓은 "오늘의
  // 주요뉴스" 블록) 오른쪽에 붙일 공간이 없어 잘려 보이던 문제를 막기 위해, 오른쪽에
  // 공간이 없으면 왼쪽에, 그것도 부족하면 화면 안쪽으로 강제로 당긴다.
  function obPosition(rect) {
    var spot = document.getElementById("ob-spot");
    var tip = document.getElementById("ob-tooltip");
    var pad = 6;
    var boxLeft = rect.left - pad;
    var boxTop = rect.top - pad;
    var boxWidth = rect.width + pad * 2;
    var boxHeight = rect.height + pad * 2;
    // 사이드바 버튼처럼 대상이 컨테이너 경계에 딱 붙어 있으면, 패딩만큼 그 경계를 넘어
    // 튀어나와(진한 남색 사이드바 밖 흰 배경까지 파란 테두리가 걸쳐) 보인다 — 대상이
    // 사이드바 안에 있을 때는 그 오른쪽 경계를 넘지 않게 잘라준다.
    var sidebar = document.getElementById("main-tabs");
    if (sidebar) {
      var sbRect = sidebar.getBoundingClientRect();
      if (rect.left >= sbRect.left - 1 && rect.right <= sbRect.right + 1) {
        var maxRight = sbRect.right - 2;
        if (boxLeft + boxWidth > maxRight) boxWidth = Math.max(0, maxRight - boxLeft);
      }
    }
    // 그 밖에도 화면 가장자리에 바짝 붙은 대상은(예: 모바일 헤더 버튼) 패딩만큼 화면
    // 밖으로 밀려나 잘려 보일 수 있어, 뷰포트 경계도 넘지 않게 한 번 더 잘라준다.
    if (boxLeft < 2) { boxWidth -= (2 - boxLeft); boxLeft = 2; }
    if (boxTop < 2) { boxHeight -= (2 - boxTop); boxTop = 2; }
    if (boxLeft + boxWidth > window.innerWidth - 2) boxWidth = Math.max(0, window.innerWidth - 2 - boxLeft);
    if (boxTop + boxHeight > window.innerHeight - 2) boxHeight = Math.max(0, window.innerHeight - 2 - boxTop);
    spot.style.top = boxTop + "px";
    spot.style.left = boxLeft + "px";
    spot.style.width = boxWidth + "px";
    spot.style.height = boxHeight + "px";

    var margin = 12;
    var tipW = Math.min(300, window.innerWidth - margin * 2);
    var mobile = window.innerWidth <= 880;
    var top, left;
    if (mobile) {
      top = rect.bottom + 14;
      left = Math.min(Math.max(margin, rect.left), window.innerWidth - tipW - margin);
    } else {
      var spaceRight = window.innerWidth - rect.right - 18;
      var spaceLeft = rect.left - 18;
      if (spaceRight >= tipW) {
        left = rect.right + 18;
      } else if (spaceLeft >= tipW + margin) {
        left = rect.left - 18 - tipW;
      } else {
        left = Math.max(margin, Math.min(rect.left, window.innerWidth - tipW - margin));
      }
      top = Math.max(margin, rect.top);
    }
    tip.style.width = tipW + "px";
    tip.style.left = left + "px";
    tip.style.top = top + "px";
    // 내용을 이미 채운 뒤에 호출되므로 실제 렌더된 높이로 세로 clamp가 가능하다
    // (화면 아래로 넘쳐 하단 버튼이 안 보이는 것을 막음).
    var tipH = tip.offsetHeight || 0;
    if (tipH) {
      tip.style.top = Math.max(margin, Math.min(top, window.innerHeight - tipH - margin)) + "px";
    }
  }
  function obBindStepButtons() {
    var next = document.getElementById("ob-next");
    if (next) next.addEventListener("click", obNext);
    var skip = document.getElementById("ob-skip");
    if (skip) skip.addEventListener("click", function () { obEnd(false); });
    var doneBtn = document.getElementById("ob-done-btn");
    if (doneBtn) doneBtn.addEventListener("click", function () { obEnd(true); });
  }
  // 스텝 전환마다 증가 — 이동 대기 중(obWaitNavReady) 사용자가 "다음/건너뛰기"로 다른
  // 스텝으로 넘어가면, 늦게 도착하는 이전 폴링 콜백이 더 이상 화면을 덮어쓰지 않게 막는다.
  var obRenderToken = 0;

  function stepRect(step, scroll) {
    if (step.selRange) {
      var a = document.querySelector(step.selRange[0]), b = document.querySelector(step.selRange[1]);
      if (!a || !b) return null;
      if (scroll) a.scrollIntoView({ block: "center", behavior: "auto" });
      return obUnionRect(a, b);
    }
    var el = document.querySelector(step.sel);
    if (!el) return null;
    if (scroll) {
      // 내용이 길어 화면보다 큰 블록(시장 한눈에·오늘의 시장 브리핑 등)은 스포트라이트는
      // 여전히 블록 전체를 감싸 보여주되(el 기준 rect), scrollIntoView(block:"center")로
      // 블록 전체를 중앙 정렬하면 블록 중간 어딘가만 화면에 걸쳐 보이고 정작 제목은
      // 화면 밖으로 밀려났다 — titleSel이 있으면 제목(.block-head)을 화면 위쪽에
      // 오도록 스크롤하고(block:"start"), 스포트라이트 박스는 그대로 전체 블록 rect를
      // 써서(아래는 뷰포트 밖으로 넘어가면 obPosition이 알아서 잘라 보여준다) "전체는
      // 강조하되 제목이 보이게" 두 요구를 함께 만족시킨다.
      var scrollEl = (step.titleSel && document.querySelector(step.titleSel)) || el;
      scrollEl.scrollIntoView({ block: scrollEl === el ? "center" : "start", behavior: "auto" });
    }
    return el.getBoundingClientRect();
  }

  // 대상이 실제로 화면에 잡힐 때까지 스포트라이트·말풍선을 그리고 위치를 맞춘다
  // (nav 스텝이든 아니든 공통 — 대상 엘리먼트가 "지금" 존재한다고 가정).
  function obShowSpot(step) {
    var backdrop = document.getElementById("ob-backdrop");
    var spot = document.getElementById("ob-spot");
    var tip = document.getElementById("ob-tooltip");
    if (!backdrop || !spot || !tip) return;
    var rect = stepRect(step, true);
    if (!rect) { obNext(); return; }
    backdrop.hidden = true;
    spot.hidden = false;
    tip.hidden = false;
    tip.className = "ob-tooltip";
    tip.innerHTML = obSpotHTML(step);
    obPosition(rect);
    obBindStepButtons();
  }

  // step.navReady가 있으면(예: 자본시장의 유동성 요약) 그게 true가 될 때까지 짧게
  // 폴링한다 — 원천 장애 등으로 끝내 안 채워져도 3초 뒤엔 그냥 지금 상태로 보여준다.
  function obWaitNavReady(step, token, cb) {
    if (!step.navReady) { cb(); return; }
    var start = Date.now();
    (function poll() {
      if (token !== obRenderToken) return; // 그 사이 다른 스텝으로 넘어감
      if (step.navReady() || Date.now() - start > 3000) { cb(); return; }
      setTimeout(poll, 80);
    })();
  }

  function obRenderStep() {
    var step = OB_STEPS[obIndex];
    if (!step) { obEnd(true); return; }
    var backdrop = document.getElementById("ob-backdrop");
    var spot = document.getElementById("ob-spot");
    var tip = document.getElementById("ob-tooltip");
    if (!backdrop || !spot || !tip) return;
    var token = ++obRenderToken;

    if (step.type === "spot") {
      if (step.nav) {
        // 이 스텝은 다른 업무 화면으로 실제 이동해서 설명한다(나의 대시보드/업무별 메뉴).
        // 이동 도중 이전 스텝의 스포트라이트가 잘못된 위치에 잠깐 보였다 다시 그려지는
        // "깜빡임"을 막기 위해, 화면이 준비될 때까지는 아무것도 안 보여준다.
        backdrop.hidden = true; spot.hidden = true; tip.hidden = true;
        obNavigated = true;
        H.goWork(step.nav);
        obWaitNavReady(step, token, function () {
          if (token !== obRenderToken) return;
          obShowSpot(step);
        });
        return;
      }
      obShowSpot(step);
    } else {
      spot.hidden = true;
      backdrop.hidden = false;
      tip.hidden = false;
      tip.className = "ob-tooltip ob-centered";
      // 이전 스텝이 spot이었다면 obPosition()이 top/left/width를 인라인 스타일로
      // 박아뒀다 — 인라인 스타일은 .ob-centered의 top:50%/left:50%보다 우선순위가
      // 높아서 안 지우면 welcome·done 모달이 마지막 스포트라이트 위치에 걸려
      // 화면 밖으로 잘려 보인다(실제로 모바일에서 이렇게 잘려 보인다는 제보 확인).
      tip.style.top = ""; tip.style.left = ""; tip.style.width = "";
      tip.innerHTML = step.type === "welcome" ? obWelcomeHTML() : obDoneHTML();
      obBindStepButtons();
    }
  }
  function obNext() { obIndex++; obRenderStep(); }
  // toBriefing: 완료 화면의 "오늘의 브리핑 보기" — 항상 홈으로. 건너뛰기는 투어가 화면을
  // 옮긴 경우에만 시작 화면으로 되돌린다(예: #capital 로 들어와 환영 화면에서 건너뛰면 그대로).
  function obEnd(toBriefing) {
    obRenderToken++; // 진행 중이던 nav 대기가 있으면 이제 와서 화면을 덮어쓰지 않게
    ["ob-backdrop", "ob-spot", "ob-tooltip"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.hidden = true;
    });
    if (!window.AppNav) return;
    if (toBriefing) window.AppNav.go("home");
    else if (obNavigated) window.AppNav.go(obStartPanel || "home");
  }
  // 창 크기 변경 시에는 위치만 다시 잰다 — 내용을 다시 그리면(말풍선 재생성·버튼 재바인딩)
  // 크기 변화가 없어도 매번 다시 깜빡여 보인다.
  function obResize() {
    var step = OB_STEPS[obIndex];
    var spot = document.getElementById("ob-spot");
    if (!step || step.type !== "spot" || !spot || spot.hidden) return;
    var rect = stepRect(step, false);
    if (rect) obPosition(rect);
  }
  window.addEventListener("resize", obResize);

  var obStarted = false;
  H.obStart = function () {
    if (obStarted) return;
    obStarted = true;
    var panel = document.querySelector(".tab-panel:not([hidden])");
    obStartPanel = panel ? panel.dataset.panel : "home";
    // 브리핑 데이터 로딩이 끝난(성공/실패 모두) 시점에 호출된다. 사이드바 레이아웃이
    // 자리잡은 뒤 좌표를 재야 스포트라이트 위치가 어긋나지 않으므로 약간의 지연을 둔다.
    setTimeout(function () { obIndex = 0; obRenderStep(); }, 400);
  };
})(window.KSFC, window.KSFC.home);
