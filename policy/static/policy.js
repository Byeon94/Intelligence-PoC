(function () {
  const ORG_BADGES = {
    FSC: "금융위",
    BOK: "한은",
    MOEF: "재경부",
    FSS: "금감원",
    KRX: "거래소",
    KSD: "예탁원",
    KOFIA: "금투협",
    CAPMKT: "자본시장법",
    DIGIASSET: "디지털자산기본법",
    KCMI: "자본연",
    KIF: "금융연",
  };

  const CATEGORY_META = {
    authority: { list: "pl-authority", status: "pl-authority-status" },
    affiliate: { list: "pl-affiliate", status: "pl-affiliate-status" },
    assembly: { list: "pl-assembly", status: "pl-assembly-status" },
    research: { list: "pl-research", status: "pl-research-status" },
  };

  function buildItem(update) {
    const item = document.createElement("div");
    item.className = "policy-item";

    const head = document.createElement("div");
    head.className = "pi-head";

    const badge = document.createElement("span");
    badge.className = "org-badge";
    badge.textContent = ORG_BADGES[update.org_code] || update.org_name;
    head.appendChild(badge);

    const date = document.createElement("span");
    date.className = "pi-date";
    date.textContent = update.published_label || "";
    head.appendChild(date);

    item.appendChild(head);

    const title = document.createElement("div");
    title.className = "pi-title";
    if (update.source_url) {
      const link = document.createElement("a");
      link.href = update.source_url;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = update.title;
      title.appendChild(link);
    } else {
      title.textContent = update.title;
    }
    item.appendChild(title);

    if (update.summary) {
      const summary = document.createElement("div");
      summary.className = "pi-summary";
      summary.textContent = update.summary;
      item.appendChild(summary);
    }

    const tags = document.createElement("div");
    tags.className = "tags";
    for (const t of update.tags || []) {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = t;
      tags.appendChild(tag);
    }
    const sourceTag = document.createElement("span");
    sourceTag.className = "tag source-tag";
    sourceTag.textContent = "출처 " + update.source_label;
    tags.appendChild(sourceTag);
    item.appendChild(tags);

    return item;
  }

  async function loadPolicyUpdates() {
    const cats = {};
    for (const [category, meta] of Object.entries(CATEGORY_META)) {
      cats[category] = {
        list: document.getElementById(meta.list),
        status: document.getElementById(meta.status),
      };
    }
    if (Object.values(cats).some((c) => !c.list || !c.status)) return;

    for (const c of Object.values(cats)) {
      c.status.textContent = "정책 동향을 불러오는 중입니다...";
      c.list.innerHTML = "";
    }

    try {
      const res = await fetch("/api/widgets/policy/updates");
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "정책 동향을 가져오지 못했습니다.");

      for (const update of data.updates) {
        const target = cats[update.category];
        if (target) target.list.appendChild(buildItem(update));
      }

      const doneMessage = data.cached
        ? "오늘 수집한 결과를 보여드려요 (하루 1회 갱신)."
        : "방금 새로 수집했습니다.";

      for (const c of Object.values(cats)) {
        if (c.list.children.length === 0) {
          c.list.innerHTML = '<div class="page-note">표시할 항목이 없습니다.</div>';
        }
        c.status.textContent = doneMessage;
      }
    } catch (err) {
      for (const c of Object.values(cats)) c.status.textContent = err.message;
    }
  }

  loadPolicyUpdates();
})();
