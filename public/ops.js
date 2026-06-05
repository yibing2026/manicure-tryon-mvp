const $ = (id) => document.getElementById(id);

const elements = {
  form: $("opsForm"),
  runCopilot: $("runCopilot"),
  loadDailyReport: $("loadDailyReport"),
  resetPreset: $("resetPreset"),
  scenarioTag: $("scenarioTag"),
  objective: $("objective"),
  channel: $("channel"),
  budgetLevel: $("budgetLevel"),
  targetStage: $("targetStage"),
  persona: $("persona"),
  occasion: $("occasion"),
  preferredColors: $("preferredColors"),
  stylePreference: $("stylePreference"),
  priceSensitivity: $("priceSensitivity"),
  candidateStyles: $("candidateStyles"),
  priorityCluster: $("priorityCluster"),
  operatorGoal: $("operatorGoal"),
  statusDot: $("statusDot"),
  runStatus: $("runStatus"),
  recommendedStyles: $("recommendedStyles"),
  recommendationCount: $("recommendationCount"),
  headline: $("headline"),
  subheadline: $("subheadline"),
  ctaPreview: $("ctaPreview"),
  operatorActions: $("operatorActions"),
  riskNotes: $("riskNotes"),
  strategySummary: $("strategySummary"),
  rawResponse: $("rawResponse"),
  dailyReportDate: $("dailyReportDate"),
  readyCount: $("readyCount"),
  reviewCount: $("reviewCount"),
  failCount: $("failCount"),
  dailyHotStyles: $("dailyHotStyles"),
  dailyActions: $("dailyActions"),
  dailyRisks: $("dailyRisks"),
};

const presets = {
  dating: {
    objective: "promote dating-week manicure selections",
    channel: "homepage_banner",
    budgetLevel: "medium",
    targetStage: "try_on",
    persona: "young-professional",
    occasion: "dating",
    preferredColors: "pink, nude",
    stylePreference: "elegant, sweet",
    priceSensitivity: "mid",
    candidateStyles: "style_02, style_10, style_13, style_23, style_25",
    priorityCluster: "",
    operatorGoal: "Increase try-on rate first, then lift saves.",
  },
  party: {
    objective: "boost premium party styles for weekend traffic",
    channel: "recommendation_row",
    budgetLevel: "high",
    targetStage: "try_on",
    persona: "fashion-lover",
    occasion: "party",
    preferredColors: "black, nude, red",
    stylePreference: "cool-girl, luxury",
    priceSensitivity: "low",
    candidateStyles: "style_03, style_07, style_08, style_09, style_12, style_20, style_22, style_24",
    priorityCluster: "premium_party_gloss",
    operatorGoal: "Win high-attention homepage slots and increase style saves.",
  },
  wedding: {
    objective: "build bridal manicure topic recommendations",
    channel: "topic_page",
    budgetLevel: "high",
    targetStage: "purchase",
    persona: "bridal-user",
    occasion: "wedding",
    preferredColors: "nude, white",
    stylePreference: "elegant, luxury",
    priceSensitivity: "low",
    candidateStyles: "style_06, style_11, style_13, style_14, style_17, style_19",
    priorityCluster: "bridal_elegant_clean",
    operatorGoal: "Promote premium bridal bundles and reduce decision hesitation.",
  },
  festival: {
    objective: "increase festival-style saves among younger users",
    channel: "push_notification",
    budgetLevel: "medium",
    targetStage: "save",
    persona: "student",
    occasion: "festival",
    preferredColors: "pink, nude, red",
    stylePreference: "sweet, daily",
    priceSensitivity: "high",
    candidateStyles: "style_05, style_15, style_16, style_18, style_25",
    priorityCluster: "cute_youth_festival",
    operatorGoal: "Use playful styles to lift saves before pushing purchases.",
  },
};

let activePreset = "dating";

function splitList(value) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function setStatus(message, mode = "") {
  elements.runStatus.textContent = message;
  elements.statusDot.className = `status-dot ${mode}`.trim();
}

function applyPreset(name) {
  const preset = presets[name];
  if (!preset) {
    return;
  }

  activePreset = name;
  document.querySelectorAll(".preset").forEach((button) => {
    button.classList.toggle("active", button.dataset.preset === name);
  });

  for (const [key, value] of Object.entries(preset)) {
    if (elements[key]) {
      elements[key].value = value;
    }
  }

  elements.scenarioTag.textContent = preset.channel;
}

function buildRequestPayload() {
  const priorityCluster = elements.priorityCluster.value.trim();

  return {
    campaign_context: {
      date: new Date().toISOString().slice(0, 10),
      objective: elements.objective.value.trim(),
      channel: elements.channel.value,
      budget_level: elements.budgetLevel.value,
      target_conversion_stage: elements.targetStage.value,
    },
    user_segment: {
      persona: elements.persona.value,
      occasion: elements.occasion.value,
      preferred_colors: splitList(elements.preferredColors.value),
      price_sensitivity: elements.priceSensitivity.value,
      style_preference: splitList(elements.stylePreference.value),
    },
    inventory_context: {
      candidate_styles: splitList(elements.candidateStyles.value),
      priority_clusters: priorityCluster ? [priorityCluster] : [],
      inventory_notes: "Generated from the local operations demo page.",
    },
    strategy_context: {
      operator_goal: elements.operatorGoal.value.trim(),
    },
  };
}

function renderList(container, items, tagName = "li") {
  container.innerHTML = "";

  if (!items?.length) {
    const empty = document.createElement(tagName);
    empty.textContent = "暂无";
    container.appendChild(empty);
    return;
  }

  for (const item of items) {
    const node = document.createElement(tagName);
    node.textContent = item;
    container.appendChild(node);
  }
}

function renderDailyReport(report) {
  const qualityGate = report.quality_gate || {};
  const trendInsights = report.trend_insights || {};

  elements.dailyReportDate.textContent = report.date || "daily report";
  elements.readyCount.textContent = qualityGate.ready_count ?? "-";
  elements.reviewCount.textContent = qualityGate.review_count ?? "-";
  elements.failCount.textContent = qualityGate.fail_count ?? "-";

  renderList(
    elements.dailyHotStyles,
    (trendInsights.hot_styles || []).slice(0, 5).map((style) =>
      `${style.style_id} · 热度 ${style.hotness_score} · ${style.occasion}/${style.style_category}`,
    ),
    "li",
  );
  renderList(elements.dailyActions, report.operator_actions || [], "li");
  renderList(elements.dailyRisks, report.risk_notes || [], "li");
}

function renderRecommendations(styles) {
  elements.recommendedStyles.innerHTML = "";
  elements.recommendedStyles.classList.toggle("empty", !styles?.length);
  elements.recommendationCount.textContent = `${styles?.length || 0} styles`;

  if (!styles?.length) {
    const empty = document.createElement("p");
    empty.textContent = "当前条件下没有返回推荐款式。";
    elements.recommendedStyles.appendChild(empty);
    return;
  }

  for (const style of styles) {
    const card = document.createElement("article");
    card.className = "style-card";
    card.innerHTML = `
      <header>
        <strong>${style.style_id}</strong>
        <span class="score">${style.fit_score}</span>
      </header>
      <p>${style.reason}</p>
    `;
    elements.recommendedStyles.appendChild(card);
  }
}

function renderResult(result) {
  renderRecommendations(result.recommended_styles || []);

  const message = result.campaign_message || {};
  elements.headline.textContent = message.headline || "暂无文案";
  elements.subheadline.textContent = message.subheadline || "暂无副标题。";
  elements.ctaPreview.textContent = message.cta || "CTA";

  renderList(elements.operatorActions, result.operator_actions || [], "li");
  renderList(elements.riskNotes, result.risk_notes || [], "li");
  elements.strategySummary.textContent = result.strategy_summary || "暂无摘要。";
  elements.rawResponse.textContent = JSON.stringify(result, null, 2);
}

async function runCopilot() {
  const payload = buildRequestPayload();

  setStatus("正在生成运营策略...", "running");
  elements.runCopilot.disabled = true;

  try {
    const response = await fetch("/api/ops-copilot-demo", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.error || "接口调用失败");
    }

    renderResult(result);
    setStatus("策略已生成", "ready");
  } catch (error) {
    setStatus(error.message || "策略生成失败", "error");
  } finally {
    elements.runCopilot.disabled = false;
  }
}

async function loadDailyReport() {
  setStatus("正在加载运营日报...", "running");
  elements.loadDailyReport.disabled = true;

  try {
    const response = await fetch("/api/ops-daily-report");
    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.error || "运营日报加载失败");
    }

    renderDailyReport(result);
    setStatus("运营日报已生成", "ready");
  } catch (error) {
    setStatus(error.message || "运营日报加载失败", "error");
  } finally {
    elements.loadDailyReport.disabled = false;
  }
}

document.querySelectorAll(".preset").forEach((button) => {
  button.addEventListener("click", () => {
    applyPreset(button.dataset.preset);
  });
});

elements.resetPreset.addEventListener("click", () => {
  applyPreset(activePreset);
  setStatus("已重置当前场景");
});

elements.runCopilot.addEventListener("click", runCopilot);
elements.loadDailyReport.addEventListener("click", loadDailyReport);
elements.channel.addEventListener("change", () => {
  elements.scenarioTag.textContent = elements.channel.value;
});

applyPreset(activePreset);
loadDailyReport();
