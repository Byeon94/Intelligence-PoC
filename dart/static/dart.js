(function () {
  const CATEGORY_LIST_IDS = {
    collateral: "dart-collateral",
    employee_stock: "dart-employee-stock",
  };
  const CATEGORY_STATUS_IDS = {
    collateral: "dart-collateral-status",
    employee_stock: "dart-employee-stock-status",
  };

  function buildFilingCard(f) {
    const card = document.createElement("div");
    card.className = "article-card";

    const meta = document.createElement("div");
    meta.className = "a-meta";
    meta.textContent = "DART" + (f.rcept_dt ? " · " + f.rcept_dt : "") + (f.stock_code ? " · " + f.stock_code : "");
    card.appendChild(meta);

    const title = document.createElement("a");
    title.className = "a-title";
    title.href = f.source_url;
    title.target = "_blank";
    title.rel = "noopener";
    title.textContent = f.corp_name + " — " + f.report_nm;
    card.appendChild(title);

    if (f.flr_nm) {
      const filer = document.createElement("div");
      filer.className = "a-desc";
      filer.textContent = "제출인: " + f.flr_nm;
      card.appendChild(filer);
    }

    return card;
  }

  async function loadDartFilings() {
    const lists = {};
    const statuses = {};
    for (const [cat, id] of Object.entries(CATEGORY_LIST_IDS)) lists[cat] = document.getElementById(id);
    for (const [cat, id] of Object.entries(CATEGORY_STATUS_IDS)) statuses[cat] = document.getElementById(id);
    if (Object.values(lists).some((el) => !el)) return;

    for (const cat of Object.keys(lists)) {
      statuses[cat].textContent = "DART 공시를 불러오는 중입니다...";
      lists[cat].innerHTML = "";
    }

    try {
      const res = await fetch("/api/widgets/dart/filings");
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "DART 공시를 가져오지 못했습니다.");

      for (const f of data.filings || []) {
        const list = lists[f.category];
        if (list) list.appendChild(buildFilingCard(f));
      }

      const doneMessage = data.cached
        ? "오늘 수집한 결과를 보여드려요 (하루 1회 갱신)."
        : "방금 새로 수집했습니다.";

      for (const cat of Object.keys(lists)) {
        if (lists[cat].children.length === 0) {
          lists[cat].innerHTML = '<div class="page-note">표시할 항목이 없습니다.</div>';
        }
        statuses[cat].textContent = doneMessage;
      }
    } catch (err) {
      for (const cat of Object.keys(lists)) statuses[cat].textContent = err.message;
    }
  }

  function buildStatTile(label, value, asOf) {
    const tile = document.createElement("div");
    tile.className = "stat-tile";

    const labelEl = document.createElement("div");
    labelEl.className = "st-label";
    labelEl.textContent = label;
    tile.appendChild(labelEl);

    const valueEl = document.createElement("div");
    valueEl.className = "st-value";
    valueEl.textContent = value.toLocaleString("ko-KR") + "건";
    tile.appendChild(valueEl);

    const asOfEl = document.createElement("div");
    asOfEl.className = "st-asof";
    asOfEl.textContent = `${asOf} 기준`;
    tile.appendChild(asOfEl);

    return tile;
  }

  async function loadDartStats() {
    const statusEl = document.getElementById("dart-stats-status");
    const gridEl = document.getElementById("dart-stats-grid");
    if (!statusEl || !gridEl) return;

    statusEl.textContent = "공시 현황을 불러오는 중입니다...";
    gridEl.innerHTML = "";

    try {
      const res = await fetch("/api/widgets/dart/stats");
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "공시 현황을 가져오지 못했습니다.");

      for (const s of data.stats || []) {
        gridEl.appendChild(buildStatTile(s.label, s.count, data.date));
      }
      statusEl.textContent = "";
    } catch (err) {
      statusEl.textContent = err.message;
    }
  }

  loadDartFilings();
  loadDartStats();
})();
