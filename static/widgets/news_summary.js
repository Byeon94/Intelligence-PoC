(function () {
  const keywordInput = document.getElementById("ns-keyword");
  const submitButton = document.getElementById("ns-submit");
  const statusEl = document.getElementById("ns-status");
  const resultEl = document.getElementById("ns-result");
  const quickChips = document.getElementById("ns-quick-chips");

  function formatTime(pubDate) {
    if (!pubDate) return "";
    const d = new Date(pubDate);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false });
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function inlineMd(str) {
    return escapeHtml(str).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  }

  // Gemini가 돌려주는 마크다운(제목 #, 굵게 **, 목록 *, 구분선 ---)을 안전하게 HTML로 변환
  function renderMarkdown(text) {
    const lines = text.split("\n");
    let html = "";
    let inList = false;
    const closeList = () => { if (inList) { html += "</ul>"; inList = false; } };

    for (const raw of lines) {
      const line = raw.trim();
      if (!line) { closeList(); continue; }
      if (/^-{3,}$/.test(line)) { closeList(); html += "<hr>"; continue; }

      const heading = line.match(/^#{1,4}\s+(.*)$/);
      if (heading) { closeList(); html += `<p class="md-h">${inlineMd(heading[1])}</p>`; continue; }

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

  async function summarize() {
    const keyword = keywordInput.value.trim();
    if (!keyword) return;

    submitButton.disabled = true;
    statusEl.textContent = `'${keyword}' 관련 뉴스를 검색하고 요약하는 중입니다...`;
    resultEl.innerHTML = "";

    try {
      const response = await fetch("/api/widgets/news-summary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keyword }),
      });

      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "요약에 실패했습니다.");

      render(data);
      statusEl.textContent = `'${keyword}' 관련 뉴스 ${data.articles.length}건을 요약했습니다.`;
    } catch (err) {
      statusEl.textContent = err.message;
    } finally {
      submitButton.disabled = false;
    }
  }

  function render(data) {
    const summaryCard = document.createElement("div");
    summaryCard.className = "summary-card";

    const label = document.createElement("span");
    label.className = "s-label";
    label.textContent = "🤖 AI 요약";
    summaryCard.appendChild(label);

    const body = document.createElement("div");
    body.innerHTML = renderMarkdown(data.summary);
    summaryCard.appendChild(body);

    resultEl.appendChild(summaryCard);

    if (data.articles.length > 0) {
      const sectionLabel = document.createElement("h4");
      sectionLabel.className = "section-label";
      sectionLabel.textContent = "참고 기사";
      resultEl.appendChild(sectionLabel);

      for (const article of data.articles) {
        resultEl.appendChild(buildArticleCard(article, data.keyword));
      }
    }
  }

  function buildArticleCard(article, keyword) {
    const card = document.createElement("div");
    card.className = "article-card";

    const meta = document.createElement("div");
    meta.className = "a-meta";
    const time = formatTime(article.pubDate);
    meta.textContent = "뉴스" + (time ? " · " + time : "") + " · 국내";
    card.appendChild(meta);

    const title = document.createElement("a");
    title.className = "a-title";
    title.href = article.link;
    title.target = "_blank";
    title.rel = "noopener";
    title.textContent = article.title;
    card.appendChild(title);

    const desc = document.createElement("div");
    desc.className = "a-desc";
    desc.textContent = article.description;
    card.appendChild(desc);

    const tags = document.createElement("div");
    tags.className = "tags";
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.textContent = "#" + keyword;
    tags.appendChild(tag);
    card.appendChild(tags);

    return card;
  }

  submitButton.addEventListener("click", summarize);
  keywordInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") summarize();
  });
  quickChips.addEventListener("click", (e) => {
    const kw = e.target.dataset.kw;
    if (!kw) return;
    keywordInput.value = kw;
    summarize();
  });
})();
