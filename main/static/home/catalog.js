/* 홈·나의 대시보드 공용 — 위젯 카탈로그, "내 위젯" 선택 상태, 업무 화면 이동.
 *
 * main/static/home/*.js 는 빌드 없이 순서대로 로드되며 window.KSFC.home(이하 H)을 공유
 * 네임스페이스로 쓴다. 이 파일이 H 를 만들므로 home/*.js 중 가장 먼저 로드해야 한다.
 * 로드 순서: catalog → mini → stock-glance → sector-card → personal → briefing → onboarding → home.js
 *
 * 위젯 "선택"은 로그인 없이, 이 탭이 열려 있는 동안(메모리)만 유지한다 — 새로고침·재접속하면
 * 초기화된다(PoC 범위, 영속 저장 없음). */
(function (K) {
  "use strict";

  var H = K.home = K.home || {};
  var esc = K.esc;

  // ── 위젯 카탈로그(= 업무별 화면의 주요 섹션 단위) — 위젯 추가 모달·전사 위젯 갤러리·
  // AI 추천에 이 순서 그대로 노출된다.
  // tab/sub: 내부 업무 화면으로 이동("자세히 보기"). sub 는 자본시장 세부탭 힌트.
  // externalUrl: 내부 화면 대신 새 탭으로 여는 링크.
  // creditBadge: 특정 부서 담당자가 직접 만든 위젯의 제작 출처(파란 배지).
  H.WIDGET_CATALOG = [
    { id: "credit-equity-glance", tab: "credit", title: "한눈에 보는 기업분석 정보", emoji: "🔎",
      creditBadge: "투자금융부 박OO 과장 제작",
      desc: "예시로 삼성전자 정보를 바로 보여드려요 — 종목을 검색하면 다른 기업 정보도 바로 확인할 수 있습니다." },
    { id: "sector-map", externalUrl: "/sector",
      title: "국내 업종별 시가총액 순위 및 밸류체인", emoji: "📊", creditBadge: "투자금융부 이OO 과장 제작",
      desc: "국내 업종별 시가총액 순위 및 대표산업(4가지) 밸류체인" },
    { id: "market-reports", externalUrl: "https://consensus.hankyung.com/analysis/list",
      title: "오늘의 증권사 리포트", emoji: "📑", creditBadge: "기획부 유OO 과장 제작",
      desc: "조회 기준일(전영업일) 시장 전체 리포트 건수 + AI 브리핑" },
    { id: "it-news", externalUrl: "https://search.naver.com/search.naver?where=news&query=" +
        encodeURIComponent("금융IT 정보보호 생성형AI"),
      title: "오늘의 IT·정보보호 뉴스", emoji: "🖥️", creditBadge: "IT부 변OO 과장 제작",
      desc: "IT·정보보호 관련 참고하기 좋은 뉴스 및 AI 브리핑" },
    { id: "capital-liquidity", tab: "capital", sub: "liquidity", title: "증시자금·유동성", emoji: "📈",
      desc: "투자자예탁금·신용공여·CMA 잔고 및 추이" },
    { id: "capital-cma", tab: "capital", sub: "cma", title: "CMA·단기수신", emoji: "💰",
      desc: "CMA 유형별 비중, 증권사별 금리 비교" },
    { id: "capital-issuance", tab: "capital", sub: "issuance", title: "발행시장", emoji: "🏗️",
      desc: "IPO·유상증자 캘린더 + AI 브리핑" }
  ];

  // 나의 대시보드에 기본으로 미리 담아두는 위젯 2개 — 처음 열었을 때부터 실데이터로
  // 바로 보여주기 위함(빈 화면 대신). 위젯 추가 목록에서도 처음부터 "추가됨"으로 보인다.
  var DEFAULT_WIDGET_IDS = ["credit-equity-glance", "sector-map"];

  // 모든 위젯이 "전사 등재" 상태다. 그 옆에 출처 배지를 붙인다 — creditBadge 가 있으면
  // 제작 부서/담당자(파란색), 없으면 "부서 위젯"(업무별 화면에서 만들어졌다는 표시).
  H.statusBadgesHTML = function (w) {
    var deptBadge = w.creditBadge
      ? '<span class="gal-status st-credit">' + esc(w.creditBadge) + "</span>"
      : '<span class="gal-status st-deptw">부서 위젯</span>';
    return deptBadge + '<span class="gal-status st-live">전사 등재</span>';
  };

  // ── 내가 고른 위젯: 이 탭이 열려 있는 동안만(메모리) 유지 ──
  var myWidgetIds = DEFAULT_WIDGET_IDS.slice();
  H.getMyWidgetIds = function () {
    return myWidgetIds.slice();
  };
  H.toggleMyWidget = function (id) {
    var i = myWidgetIds.indexOf(id);
    if (i >= 0) myWidgetIds.splice(i, 1); else myWidgetIds.push(id);
    return myWidgetIds.slice();
  };
  H.isMine = function (id) {
    return myWidgetIds.indexOf(id) >= 0;
  };

  // 위젯 추가 모달·갤러리·AI 추천이 고를 수 있는 전체 목록(카탈로그 순서).
  H.galItemsForCatalog = function () {
    return H.WIDGET_CATALOG.slice();
  };

  H.goWork = function (tab, sub) {
    if (window.AppNav) window.AppNav.go(tab);
    if (sub && tab === "capital" && window.CapitalNav) window.CapitalNav.goSub(sub);
    // 각 업무 모듈(정책/뉴스 등)은 #main-tabs 클릭을 감지해 처음 한 번
    // 데이터를 지연 로딩한다. 홈/나의 대시보드에서 곧장 이동할 때도 그 로딩이 걸리도록
    // 같은 이벤트를 한 번 흉내 낸다.
    var bar = document.getElementById("main-tabs");
    if (bar) bar.dispatchEvent(new Event("click", { bubbles: true }));
  };
})(window.KSFC);
