(function () {
  const CATEGORY_LIST_IDS = {
    ksfc: "nf-ksfc",
    finance: "nf-finance",
    investment: "nf-investment",
    it: "nf-it",
  };
  const CATEGORY_STATUS_IDS = {
    ksfc: "nf-ksfc-status",
    finance: "nf-finance-status",
    investment: "nf-investment-status",
    it: "nf-it-status",
  };

  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function inlineMd(str) {
    return escapeHtml(str).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  }

  function renderMarkdown(text) {
    const lines = text.split("\n");
    let html = "";
    let inList = false;
    const closeList = () => { if (inList) { html += "</ul>"; inList = false; } };

    for (const raw of lines) {
      const line = raw.trim();
      if (!line) { closeList(); continue; }

      const bullet = line.match(/^[*-]\s+(.*)$/);
      if (bullet) {
        if (!inList) { html += "<ul>"; inList = true; }
        html += `<li>${inlineMd(bullet[1])}</li>`;
        continue;
      }

      closeList();
      html += `<p>${inlineMd(line)}</p>`;
    }
    closeList();
    return html;
  }

  function formatTime(pubDate) {
    if (!pubDate) return "";
    const d = new Date(pubDate);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false });
  }

  function buildArticleCard(item) {
    const card = document.createElement("div");
    card.className = "article-card";

    const meta = document.createElement("div");
    meta.className = "a-meta";
    const time = formatTime(item.published_label);
    meta.textContent = "뉴스" + (time ? " · " + time : "") + " · 국내";
    card.appendChild(meta);

    const title = document.createElement("a");
    title.className = "a-title";
    title.href = item.link;
    title.target = "_blank";
    title.rel = "noopener";
    title.textContent = item.title;
    card.appendChild(title);

    const desc = document.createElement("div");
    desc.className = "a-desc";
    desc.textContent = item.description || "";
    card.appendChild(desc);

    const tags = document.createElement("div");
    tags.className = "tags";
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.textContent = "#" + item.keyword;
    tags.appendChild(tag);
    card.appendChild(tags);

    return card;
  }

  async function loadNewsFeed() {
    const briefingStatus = document.getElementById("nf-briefing-status");
    const briefingBody = document.getElementById("nf-briefing-body");
    const lists = {};
    const statuses = {};
    for (const [cat, id] of Object.entries(CATEGORY_LIST_IDS)) lists[cat] = document.getElementById(id);
    for (const [cat, id] of Object.entries(CATEGORY_STATUS_IDS)) statuses[cat] = document.getElementById(id);
    if (!briefingStatus || !briefingBody || Object.values(lists).some((el) => !el)) return;

    briefingStatus.textContent = "오늘의 포인트 뉴스를 준비하는 중입니다...";
    briefingBody.innerHTML = '<p class="summary-loading">불러오는 중입니다...</p>';
    for (const cat of Object.keys(lists)) {
      statuses[cat].textContent = "뉴스를 불러오는 중입니다...";
      lists[cat].innerHTML = "";
    }

    try {
      const res = await fetch("/api/widgets/news-feed/today");
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "뉴스를 가져오지 못했습니다.");

      for (const item of data.items || []) {
        const list = lists[item.category];
        if (list) list.appendChild(buildArticleCard(item));
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

      if (data.summary) {
        briefingBody.innerHTML = renderMarkdown(data.summary);
        briefingStatus.textContent = doneMessage;
      } else {
        briefingBody.innerHTML = '<p class="summary-loading">AI 요약을 생성하지 못했습니다.</p>';
        briefingStatus.textContent = "";
      }
    } catch (err) {
      briefingStatus.textContent = err.message;
      briefingBody.innerHTML = "";
      for (const cat of Object.keys(lists)) statuses[cat].textContent = err.message;
    }
  }

  loadNewsFeed();
})();
