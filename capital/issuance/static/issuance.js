/* 자본시장 > 발행시장: IPO·발행시장 월 캘린더 + 브리핑 + 일정 리스트 */
(function () {
  "use strict";

  var TYPE_VAR = { "수요예측": "--c1", "청약": "--c3", "상장": "--c2", "유상증자": "--c4" };
  var DOW = ["일", "월", "화", "수", "목", "금", "토"];

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function renderCalendar(d) {
    var box = document.getElementById("iss-calendar");
    if (!box) return;
    var m = /^(\d{4})-(\d{2})/.exec(d.date || "");
    if (!m) { box.innerHTML = '<div class="chart-error">월 정보 없음</div>'; return; }
    var year = +m[1], mon = +m[2];
    var first = new Date(year, mon - 1, 1);
    var startDow = first.getDay();
    var daysInMonth = new Date(year, mon, 0).getDate();

    var byDay = {};
    (d.events || []).forEach(function (e) {
      var dm = /-(\d{2})$/.exec(e.date || "");
      if (!dm) return;
      var day = +dm[1];
      (byDay[day] = byDay[day] || []).push(e);
    });

    var cells = [];
    for (var i = 0; i < startDow; i++) cells.push('<div class="cal-day cal-empty"></div>');
    for (var day = 1; day <= daysInMonth; day++) {
      var evs = (byDay[day] || []).map(function (e) {
        return '<a class="cal-ev" href="' + esc(e.url) + '" target="_blank" rel="noopener" ' +
          'style="border-left-color:var(' + (TYPE_VAR[e.type] || "--muted") + ')" ' +
          'title="' + esc(e.company + " · " + e.type + (e.detail ? " · " + e.detail : "")) + '">' +
          esc(e.company) + " <span class=\"ce-t\">" + esc(e.type) + "</span></a>";
      }).join("");
      var dow = (startDow + day - 1) % 7;
      cells.push(
        '<div class="cal-day' + (dow === 0 ? " cal-sun" : dow === 6 ? " cal-sat" : "") + '">' +
          '<div class="cal-num">' + day + "</div>" + evs +
        "</div>"
      );
    }
    while (cells.length % 7) cells.push('<div class="cal-day cal-empty"></div>');

    box.innerHTML =
      '<div class="cal-grid">' +
        DOW.map(function (n, i) {
          return '<div class="cal-dow' + (i === 0 ? " cal-sun" : i === 6 ? " cal-sat" : "") + '">' + n + "</div>";
        }).join("") +
        cells.join("") +
      "</div>";
  }

  function renderBrief(d) {
    var box = document.getElementById("iss-brief");
    if (!box) return;
    var when = d.briefing_at || d.generated_at || "";
    var bullets = (d.briefing || []).filter(Boolean).slice(0, 3);
    if (!bullets.length) {
      box.innerHTML = '<div class="brief-note">' + esc(d.briefing_note || "브리핑을 사용할 수 없습니다.") + "</div>";
      return;
    }
    box.innerHTML =
      '<div class="brief-head">' +
        '<span class="brief-label">💡 발행시장 브리핑</span>' +
        '<span class="brief-when">' + esc(when) + " 생성</span>" +
      "</div>" +
      '<ol class="brief-list">' +
        bullets.map(function (b, i) {
          return '<li><span class="bl-no">' + ["①", "②", "③"][i] + "</span><span class=\"bl-tx\">" + esc(b) + "</span></li>";
        }).join("") +
      "</ol>" +
      '<div class="brief-meta">📌 38커뮤니케이션 공모일정 + 금융감독원 DART 유상증자 공시 기반, AI 자동 생성.</div>';
  }


  function fetchDigest(refresh) {
    var btn = document.getElementById("iss-regen");
    if (refresh && btn) { btn.disabled = true; btn.textContent = "재생성 중…"; }
    fetch("/api/issuance/digest" + (refresh ? "?refresh=1" : ""))
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "요청 실패"); return j; }); })
      .then(function (d) {
        var mo = document.getElementById("iss-month");
        if (mo) mo.textContent = "— " + (d.month_label || "");
        var as = document.getElementById("iss-asof");
        if (as) as.textContent = (d.generated_at || "") + " 수집" + (d.stale ? " · 이전 자료" : "");
        if (btn) { btn.disabled = false; btn.textContent = "↻ 재생성"; }
        renderBrief(d); renderCalendar(d);
      })
      .catch(function (e) {
        var box = document.getElementById("iss-calendar");
        if (box) box.innerHTML = '<div class="chart-error">' + esc(e.message) + "</div>";
        if (btn) { btn.disabled = false; btn.textContent = "↻ 재생성"; }
      });
  }

  var done = false;
  window.Issuance = {
    load: function () {
      if (done) return;
      done = true;
      var b = document.getElementById("iss-regen");
      if (b) b.addEventListener("click", function () { fetchDigest(true); });
      fetchDigest(false);
    },
  };
})();
