/* 홈·나의 대시보드 진입점 — index.html 의 applyView 가 부르는 window.HomeDashboard 를 연결한다.
 * 실제 구현은 main/static/home/*.js(window.KSFC.home 공유)에 있고, 이 파일은 그 뒤에 로드한다. */
(function (H) {
  "use strict";

  window.HomeDashboard = {
    enterHome: function () { H.ensureBriefing(); },
    enterGallery: function () { H.renderGallery(); },
    enterPersonal: function () { H.renderPersonal(); },
    // 온보딩은 보통 홈 화면의 브리핑 로딩 완료 시점에 시작되지만, 첫 진입 화면이 홈이
    // 아닌 경우(예: 북마크한 #capital 링크로 접속)를 위한 안전장치로 노출한다.
    obStart: function () { H.obStart(); }
  };
})(window.KSFC.home);
