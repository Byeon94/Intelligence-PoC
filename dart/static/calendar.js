(function () {
  const DOW = ["일", "월", "화", "수", "목", "금", "토"];

  const CAL_CONFIG = {
    ipo: { grid: "cal-ipo-grid", title: "cal-ipo-title", status: "cal-ipo-status" },
    rights: { grid: "cal-rights-grid", title: "cal-rights-title", status: "cal-rights-status" },
  };

  const state = {};
  const now = new Date();
  for (const cat of Object.keys(CAL_CONFIG)) {
    state[cat] = { year: now.getFullYear(), month: now.getMonth() + 1 };
  }

  function ym(s) {
    return `${s.year}-${String(s.month).padStart(2, "0")}`;
  }

  function shiftMonth(cat, dir) {
    const s = state[cat];
    s.month += dir;
    if (s.month > 12) { s.month = 1; s.year += 1; }
    if (s.month < 1) { s.month = 12; s.year -= 1; }
    loadCalendar(cat);
  }

  function buildGrid(gridEl, year, month, itemsByDay) {
    gridEl.innerHTML = "";

    for (const d of DOW) {
      const el = document.createElement("div");
      el.className = "cal-dow";
      el.textContent = d;
      gridEl.appendChild(el);
    }

    const firstDow = new Date(year, month - 1, 1).getDay();
    const daysInMonth = new Date(year, month, 0).getDate();

    for (let i = 0; i < firstDow; i++) {
      const empty = document.createElement("div");
      empty.className = "cal-day empty";
      gridEl.appendChild(empty);
    }

    for (let day = 1; day <= daysInMonth; day++) {
      const cell = document.createElement("div");
      cell.className = "cal-day";

      const num = document.createElement("div");
      num.className = "cal-day-num";
      num.textContent = day;
      cell.appendChild(num);

      const dateKey = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
      for (const item of itemsByDay[dateKey] || []) {
        const tag = document.createElement("a");
        tag.className = "cal-item";
        if (item.right_type) tag.classList.add("cal-item-" + item.right_type);
        tag.href = item.source_url;
        tag.target = "_blank";
        tag.rel = "noopener";
        tag.textContent = item.corp_name;
        tag.title = item.right_label
          ? `${item.corp_name} · ${item.right_label} — ${item.report_nm}`
          : item.corp_name + " — " + item.report_nm;
        cell.appendChild(tag);
      }

      gridEl.appendChild(cell);
    }
  }

  async function loadCalendar(cat) {
    const cfg = CAL_CONFIG[cat];
    const gridEl = document.getElementById(cfg.grid);
    const titleEl = document.getElementById(cfg.title);
    const statusEl = document.getElementById(cfg.status);
    if (!gridEl || !titleEl || !statusEl) return;

    const s = state[cat];
    titleEl.textContent = `${s.year}년 ${s.month}월`;
    statusEl.textContent = "불러오는 중입니다...";
    gridEl.innerHTML = "";

    try {
      const res = await fetch(`/api/widgets/dart/calendar?month=${ym(s)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "캘린더를 가져오지 못했습니다.");

      const itemsByDay = {};
      let count = 0;
      for (const item of data.items || []) {
        if (item.category !== cat || !item.rcept_dt) continue;
        (itemsByDay[item.rcept_dt] = itemsByDay[item.rcept_dt] || []).push(item);
        count += 1;
      }

      buildGrid(gridEl, s.year, s.month, itemsByDay);
      statusEl.textContent = `${count}건 · ` + (data.cached ? "캐시된 결과입니다." : "방금 조회했습니다.");
    } catch (err) {
      statusEl.textContent = err.message;
    }
  }

  document.querySelectorAll(".cal-nav .chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      shiftMonth(btn.dataset.cal, parseInt(btn.dataset.dir, 10));
    });
  });

  for (const cat of Object.keys(CAL_CONFIG)) loadCalendar(cat);
})();
