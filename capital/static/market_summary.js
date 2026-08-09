(function () {
  function formatValue(value) {
    return value.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function buildTile({ title, value, change, changePct, asOf }) {
    const tile = document.createElement("div");
    tile.className = "stat-tile";

    const label = document.createElement("div");
    label.className = "st-label";
    label.textContent = title;
    tile.appendChild(label);

    const valueEl = document.createElement("div");
    valueEl.className = "st-value";
    valueEl.textContent = formatValue(value);
    tile.appendChild(valueEl);

    const isUp = change >= 0;
    const sign = isUp ? "+" : "";
    const delta = document.createElement("div");
    delta.className = "st-delta " + (isUp ? "up" : "down");
    delta.textContent = `${isUp ? "▲" : "▼"} ${sign}${formatValue(change)} (${sign}${changePct.toFixed(2)}%)`;
    tile.appendChild(delta);

    const asOfEl = document.createElement("div");
    asOfEl.className = "st-asof";
    asOfEl.textContent = `${asOf} 기준`;
    tile.appendChild(asOfEl);

    return tile;
  }

  async function loadIndices() {
    const statusEl = document.getElementById("ms-status");
    const gridEl = document.getElementById("ms-grid");
    if (!statusEl || !gridEl) return;

    statusEl.textContent = "지수 데이터를 불러오는 중입니다...";
    gridEl.innerHTML = "";

    try {
      const res = await fetch("/api/widgets/market-summary/indices");
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "지수 데이터를 가져오지 못했습니다.");

      for (const idx of data.indices) {
        const country = idx.market === "KR" ? "대한민국" : "미국";
        gridEl.appendChild(
          buildTile({
            title: `${idx.name} · ${country}`,
            value: idx.value,
            change: idx.change,
            changePct: idx.change_pct,
            asOf: idx.as_of,
          })
        );
      }
      statusEl.textContent = "";
    } catch (err) {
      statusEl.textContent = err.message;
    }
  }

  async function loadFundFlow() {
    const statusEl = document.getElementById("ff-status");
    const gridEl = document.getElementById("ff-grid");
    if (!statusEl || !gridEl) return;

    statusEl.textContent = "자금동향 데이터를 불러오는 중입니다...";
    gridEl.innerHTML = "";

    try {
      const res = await fetch("/api/widgets/market-summary/fund-flow");
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "자금동향 데이터를 가져오지 못했습니다.");

      for (const item of data.fund_flow) {
        gridEl.appendChild(
          buildTile({
            title: `${item.name} (${item.unit})`,
            value: item.value,
            change: item.change,
            changePct: item.change_pct,
            asOf: item.as_of,
          })
        );
      }
      statusEl.textContent = "";
    } catch (err) {
      statusEl.textContent = err.message;
    }
  }

  loadIndices();
  loadFundFlow();
})();
