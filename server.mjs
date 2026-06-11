import { createReadStream, readFileSync } from "node:fs";
import { access, appendFile, mkdir, stat } from "node:fs/promises";
import { execFile } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const publicDir = path.join(__dirname, "public");
const execFileAsync = promisify(execFile);

loadEnvFile(path.join(__dirname, ".env.local"));
loadEnvFile(path.join(__dirname, ".env"));
const port = Number(process.env.PORT || 3000);
const workbookPath =
  process.env.OFFICIAL_WORKBOOK_PATH ||
  "D:\\Manicure\\命题三美甲评测数据（对外版）.xlsx";
const workbookExtractorScript = path.join(
  __dirname,
  "scripts",
  "extract_official_samples.py",
);
const opsStrategyRulesPath = path.join(
  __dirname,
  "analysis",
  "ops_strategy_v1",
  "ops_strategy_rules_v1.json",
);
const tryonQualityReportPath = path.join(
  __dirname,
  "analysis",
  "tryon_quality_v1",
  "tryon_quality_report.json",
);
const mockStylePopularityPath = path.join(
  __dirname,
  "data",
  "mock_style_popularity.json",
);
const opsDailyReportPath = path.join(
  __dirname,
  "analysis",
  "ops_daily_report_v1",
  "ops_daily_report.json",
);
const apiCallLogPath = path.resolve(
  __dirname,
  process.env.API_CALL_LOG_PATH || "logs/api-calls.jsonl",
);

const mimeTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
};

function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
  res.end(JSON.stringify(payload));
}

function loadEnvFile(filePath) {
  try {
    const source = readFileSync(filePath, "utf8");
    for (const rawLine of source.split(/\r?\n/)) {
      const line = rawLine.trim();
      if (!line || line.startsWith("#")) {
        continue;
      }

      const separator = line.indexOf("=");
      if (separator === -1) {
        continue;
      }

      const key = line.slice(0, separator).trim();
      const value = line.slice(separator + 1).trim().replace(/^['"]|['"]$/g, "");
      if (!(key in process.env)) {
        process.env[key] = value;
      }
    }
  } catch {
    // Ignore missing env files so the app still works with shell env vars.
  }
}

function buildTryOnPrompt(customPrompt) {
  const basePrompt = [
    "You are editing a manicure try-on image.",
    "Image 1 is the original hand photo and must remain the visual base.",
    "Image 2 is the manicure style reference.",
    "Image 3 is a rough placement guide created by the product UI.",
    "Create a photorealistic manicure try-on result that keeps the exact hand pose, skin tone, lighting, and background from image 1.",
    "Apply only the nail color, pattern, finish, and decorative details inspired by image 2.",
    "Use image 3 only as a spatial hint for nail placement, scale, and orientation.",
    "Do not change finger anatomy, hand shape, jewelry, or camera angle.",
    "Keep nail edges clean, realistic, and aligned with visible nail beds.",
  ].join(" ");

  return customPrompt?.trim()
    ? `${basePrompt} Additional user preference: ${customPrompt.trim()}`
    : basePrompt;
}

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => {
      try {
        const raw = Buffer.concat(chunks).toString("utf8");
        resolve(raw ? JSON.parse(raw) : {});
      } catch (error) {
        reject(error);
      }
    });
    req.on("error", reject);
  });
}

function getMimeExtension(mimeType) {
  const cleaned = mimeType.split(";")[0].trim().toLowerCase();
  switch (cleaned) {
    case "image/jpeg":
      return "jpg";
    case "image/png":
      return "png";
    case "image/webp":
      return "webp";
    default:
      return "png";
  }
}

function getPythonCommand() {
  return (
    process.env.OFFICIAL_SAMPLES_PYTHON ||
    process.env.PYTHON ||
    "python"
  );
}

let officialSamplesCache = null;
let opsStrategyRulesCache = null;
let tryonQualityCache = null;
let stylePopularityCache = null;

function parseJsonFile(filePath) {
  return JSON.parse(readFileSync(filePath, "utf8"));
}

async function loadOfficialSamples() {
  if (officialSamplesCache) {
    return officialSamplesCache;
  }

  const { stdout } = await execFileAsync(
    getPythonCommand(),
    [workbookExtractorScript, workbookPath],
    {
      cwd: __dirname,
      maxBuffer: 8 * 1024 * 1024,
    },
  );

  officialSamplesCache = JSON.parse(stdout);
  return officialSamplesCache;
}

function loadOpsStrategyRules() {
  if (opsStrategyRulesCache) {
    return opsStrategyRulesCache;
  }

  opsStrategyRulesCache = parseJsonFile(opsStrategyRulesPath);
  return opsStrategyRulesCache;
}

function loadTryonQualityByStyleId() {
  if (tryonQualityCache) {
    return tryonQualityCache;
  }

  const report = parseJsonFile(tryonQualityReportPath);
  const qualityMap = new Map();
  for (const record of report.records || []) {
    if (record.styleId == null) {
      continue;
    }
    const styleId = `style_${String(record.styleId).padStart(2, "0")}`;
    qualityMap.set(styleId, {
      decision: record.decision,
      score: record.score,
      warnings: record.warnings || [],
      reasons: record.reasons || [],
    });
  }

  tryonQualityCache = qualityMap;
  return tryonQualityCache;
}

function loadStylePopularityById() {
  if (stylePopularityCache) {
    return stylePopularityCache;
  }

  const payload = parseJsonFile(mockStylePopularityPath);
  stylePopularityCache = new Map(
    (payload.styles || []).map((style) => [style.style_id, style]),
  );
  return stylePopularityCache;
}

function normalizeString(value) {
  return typeof value === "string" ? value.trim().toLowerCase() : "";
}

function uniqueStrings(values) {
  return [...new Set(values.filter(Boolean))];
}

function mapStylesById(rules) {
  const styleMap = new Map();
  const buckets = [
    ...Object.values(rules.persona_rules || {}),
    ...Object.values(rules.occasion_rules || {}),
    ...(rules.trend_clusters || []),
  ];

  for (const bucket of buckets) {
    for (const style of bucket.recommended_styles || bucket.styles || []) {
      styleMap.set(style.style_id, style);
    }
  }

  return styleMap;
}

function collectClusterStyleIds(cluster) {
  return new Set((cluster?.styles || []).map((style) => style.style_id));
}

function getBudgetPricePreference(campaignContext = {}, userSegment = {}) {
  const budgetLevel = normalizeString(campaignContext.budget_level);
  const priceSensitivity = normalizeString(userSegment.price_sensitivity);

  if (budgetLevel === "low" || priceSensitivity === "high") {
    return "mid";
  }

  if (budgetLevel === "high" && priceSensitivity !== "high") {
    return "premium";
  }

  return "";
}

function scoreStyle({
  style,
  personaRule,
  occasionRule,
  preferredColors,
  preferredCategories,
  preferredPriceBand,
  priorityClusterStyleIds,
}) {
  let score = 50;
  const reasons = [];

  if (personaRule?.recommended_styles?.some((item) => item.style_id === style.style_id)) {
    score += 18;
    reasons.push("matches persona recommendations");
  }

  if (occasionRule?.recommended_styles?.some((item) => item.style_id === style.style_id)) {
    score += 18;
    reasons.push("fits the target occasion");
  }

  if (preferredColors.includes(style.primary_color)) {
    score += 10;
    reasons.push(`aligns with preferred color ${style.primary_color}`);
  }

  if (preferredCategories.includes(style.style_category)) {
    score += 10;
    reasons.push(`matches preferred style ${style.style_category}`);
  }

  if (preferredPriceBand && style.price_band === preferredPriceBand) {
    score += 6;
    reasons.push(`fits the ${preferredPriceBand}-price expectation`);
  }

  if (priorityClusterStyleIds.has(style.style_id)) {
    score += 12;
    reasons.push("belongs to a priority trend cluster");
  }

  if (
    personaRule?.preferred_occasions?.includes(style.occasion) &&
    occasionRule?.hero_categories?.includes(style.style_category)
  ) {
    score += 8;
    reasons.push("has strong persona-occasion consistency");
  }

  return {
    score: Math.min(99, score),
    reasons,
  };
}

function colorFitsSkinTone(color, skinTone) {
  const tone = normalizeString(skinTone);
  const normalizedColor = normalizeString(color);
  const fitMap = {
    fair: ["pink", "nude", "red", "black", "gray"],
    warm: ["nude", "gold", "green", "red", "orange", "brown"],
    medium: ["nude", "green", "pink", "gray", "silver", "black"],
    deep: ["gold", "white", "red", "black", "green", "silver"],
  };
  return (fitMap[tone] || []).includes(normalizedColor);
}

function styleFitsHandShape(style, handShape, nailLengthPreference) {
  const shape = normalizeString(handShape);
  const lengthPreference = normalizeString(nailLengthPreference);
  const length = normalizeString(style.length);
  const category = normalizeString(style.style_category);
  const nailShape = normalizeString(style.shape);

  if (shape === "short-wide") {
    return (
      ["short", "medium"].includes(length) ||
      ["round", "squoval"].includes(nailShape) ||
      ["minimal", "daily"].includes(category)
    );
  }

  if (shape === "slender") {
    return ["medium", "long"].includes(length) || ["almond"].includes(nailShape);
  }

  if (shape === "small") {
    return ["short", "medium"].includes(length) || ["minimal", "sweet"].includes(category);
  }

  if (shape === "long") {
    return ["medium", "long"].includes(length) || ["luxury", "cool-girl"].includes(category);
  }

  return lengthPreference ? length === lengthPreference : true;
}

function getQualityAdjustment(quality) {
  if (!quality) {
    return {
      score: 0,
      reason: "暂无试戴质检记录",
      risk: "该款式尚未进入官方配对质检集，建议生成后再进入主推位。",
    };
  }

  if (quality.decision === "pass") {
    return {
      score: 8,
      reason: "试戴质检通过",
      risk: "",
    };
  }

  if (quality.decision === "review") {
    return {
      score: -12,
      reason: "试戴质检建议复查",
      risk: "该款式试戴图进入 review 队列，推荐前建议重新生成或人工确认。",
    };
  }

  return {
    score: -30,
    reason: "试戴质检未通过",
    risk: "该款式暂不建议进入用户推荐池。",
  };
}

function buildUserRecommendationScore({
  style,
  popularity,
  quality,
  profile,
}) {
  let score = 20;
  const reasons = [];
  const risks = [];
  const hotnessScore = Number(popularity?.hotness_score || 50);

  score += hotnessScore * 0.25;
  reasons.push(`近期热度 ${Math.round(hotnessScore)}/100`);

  if (normalizeString(profile.occasion) === normalizeString(style.occasion)) {
    score += 16;
    reasons.push(`适合${profile.occasion}场景`);
  }

  if (normalizeString(profile.stylePreference) === normalizeString(style.style_category)) {
    score += 14;
    reasons.push(`符合${profile.stylePreference}风格偏好`);
  }

  if (colorFitsSkinTone(style.primary_color, profile.skinTone)) {
    score += 10;
    reasons.push(`主色 ${style.primary_color} 与${profile.skinTone}肤色适配`);
  }

  if (styleFitsHandShape(style, profile.handShape, profile.nailLengthPreference)) {
    score += 8;
    reasons.push(`适合${profile.handShape}手型或${profile.nailLengthPreference}甲长偏好`);
  }

  if (normalizeString(profile.budget) === normalizeString(style.price_band)) {
    score += 6;
    reasons.push(`符合${profile.budget}预算带`);
  }

  const qualityAdjustment = getQualityAdjustment(quality);
  score += qualityAdjustment.score;
  reasons.push(qualityAdjustment.reason);
  if (qualityAdjustment.risk) {
    risks.push(qualityAdjustment.risk);
  }

  return {
    score: Math.max(0, Math.min(99, Math.round(score))),
    reasons,
    risks,
  };
}

function buildCampaignMessage({
  occasion,
  persona,
  topStyles,
  occasionRule,
  targetStage,
}) {
  const topColors = uniqueStrings(topStyles.map((style) => style.primary_color)).slice(0, 2);
  const headlineMap = {
    dating: "约会氛围感美甲，一试就更心动",
    party: "高吸睛派对美甲，先试戴再种草",
    wedding: "婚礼高质感美甲，提前锁定安心感",
    commute: "通勤也精致，美甲风格轻松试出来",
    daily: "日常耐看款，先看上手再决定",
    festival: "节日氛围款，一键试戴更容易出片",
  };
  const ctaMap = {
    try_on: "立即试戴",
    save: "先收藏灵感",
    purchase: "查看款式",
  };

  const headline = headlineMap[occasion] || "热门美甲风格推荐";
  const subheadlineParts = [];

  if (topColors.length) {
    subheadlineParts.push(`优先突出${topColors.join("、")}色调`);
  }
  if (occasionRule?.campaign_angle) {
    subheadlineParts.push(occasionRule.campaign_angle);
  }
  if (persona) {
    subheadlineParts.push(`更适合${persona}人群快速完成试戴决策`);
  }

  return {
    headline,
    subheadline: subheadlineParts.join("；"),
    cta: ctaMap[targetStage] || ctaMap.try_on,
  };
}

function buildOperatorActions({
  requestBody,
  topStyles,
  occasionRule,
  topCluster,
}) {
  const styleIds = topStyles.map((style) => style.style_id);
  const actions = [];

  if (styleIds.length) {
    actions.push(`将 ${styleIds.slice(0, 2).join("、")} 放入首屏推荐位，优先承接试戴流量。`);
  }

  if (occasionRule?.hero_colors?.length) {
    actions.push(`Banner 视觉主色建议围绕 ${occasionRule.hero_colors.slice(0, 3).join("、")} 组织。`);
  }

  actions.push(
    requestBody?.campaign_context?.target_conversion_stage === "try_on"
      ? "投放话术优先强调“先试戴再决定”，不要一开始就硬推下单。"
      : "在推荐卡中补充“上手效果”和“适合场景”，帮助用户更快转化。"
  );

  if (topCluster?.cluster_name) {
    actions.push(`可同步建立 ${topCluster.cluster_name} 专题位，放大当前趋势感知。`);
  }

  return actions.slice(0, 4);
}

function buildRiskNotes({
  requestBody,
  topStyles,
  personaRule,
  occasionRule,
}) {
  const notes = [];
  const candidateStyles = requestBody?.inventory_context?.candidate_styles || [];
  const preferredCategories = new Set(personaRule?.preferred_style_categories || []);
  const preferredColors = new Set([
    ...(personaRule?.preferred_colors || []),
    ...(requestBody?.user_segment?.preferred_colors || []),
  ]);

  for (const style of topStyles) {
    if (!preferredCategories.has(style.style_category)) {
      notes.push(`${style.style_id} 风格更偏 ${style.style_category}，与目标人群主偏好并非完全一致。`);
      break;
    }
  }

  for (const styleId of candidateStyles) {
    const isOccasionMatch = occasionRule?.recommended_styles?.some((item) => item.style_id === styleId);
    if (!isOccasionMatch) {
      notes.push(`${styleId} 不属于本次主场景强匹配款，建议放到次级流量位观察表现。`);
      break;
    }
  }

  for (const style of topStyles) {
    if (!preferredColors.has(style.primary_color)) {
      notes.push(`${style.style_id} 主色 ${style.primary_color} 与当前偏好色不完全一致，建议减少首图曝光。`);
      break;
    }
  }

  return uniqueStrings(notes).slice(0, 3);
}

async function handleOpsCopilotDemo(req, res) {
  try {
    const body = await readJsonBody(req);
    const rules = loadOpsStrategyRules();
    const persona = body?.user_segment?.persona;
    const occasion = body?.user_segment?.occasion;
    const personaRule = rules.persona_rules?.[persona] || null;
    const occasionRule = rules.occasion_rules?.[occasion] || null;
    const allStyles = mapStylesById(rules);
    const candidateStyles =
      body?.inventory_context?.candidate_styles?.length
        ? body.inventory_context.candidate_styles
        : uniqueStrings([
            ...(personaRule?.recommended_styles?.map((item) => item.style_id) || []),
            ...(occasionRule?.recommended_styles?.map((item) => item.style_id) || []),
          ]);

    const priorityClusters = body?.inventory_context?.priority_clusters || [];
    const clusterObjects = (rules.trend_clusters || []).filter((cluster) =>
      priorityClusters.includes(cluster.cluster_name),
    );
    const priorityClusterStyleIds = new Set(
      clusterObjects.flatMap((cluster) => [...collectClusterStyleIds(cluster)]),
    );

    const preferredColors = uniqueStrings([
      ...(body?.user_segment?.preferred_colors || []),
      ...(personaRule?.preferred_colors || []),
    ]);
    const preferredCategories = uniqueStrings([
      ...(body?.user_segment?.style_preference || []),
      ...(personaRule?.preferred_style_categories || []),
    ]);
    const preferredPriceBand = getBudgetPricePreference(
      body?.campaign_context,
      body?.user_segment,
    );

    const scoredStyles = candidateStyles
      .map((styleId) => allStyles.get(styleId))
      .filter(Boolean)
      .map((style) => {
        const result = scoreStyle({
          style,
          personaRule,
          occasionRule,
          preferredColors,
          preferredCategories,
          preferredPriceBand,
          priorityClusterStyleIds,
        });

        return {
          style,
          fit_score: result.score,
          reason: result.reasons.join("; "),
        };
      })
      .sort((left, right) => right.fit_score - left.fit_score);

    const recommended = scoredStyles.slice(0, 3);
    const topStyles = recommended.map((item) => item.style);
    const topCluster = clusterObjects[0] || null;

    sendJson(res, 200, {
      recommended_styles: recommended.map((item) => ({
        style_id: item.style.style_id,
        reason: item.reason || "Matches the current operator objective.",
        fit_score: item.fit_score,
      })),
      campaign_message: buildCampaignMessage({
        occasion,
        persona,
        topStyles,
        occasionRule,
        targetStage: body?.campaign_context?.target_conversion_stage,
      }),
      operator_actions: buildOperatorActions({
        requestBody: body,
        topStyles,
        occasionRule,
        topCluster,
      }),
      risk_notes: buildRiskNotes({
        requestBody: body,
        topStyles,
        personaRule,
        occasionRule,
      }),
      strategy_summary: [
        personaRule?.strategy_hint,
        occasionRule?.campaign_angle,
        body?.strategy_context?.operator_goal
          ? `Current operator goal: ${body.strategy_context.operator_goal}.`
          : "",
      ]
        .filter(Boolean)
        .join(" "),
    });
  } catch (error) {
    sendJson(res, 500, {
      error: error instanceof Error ? error.message : "Ops copilot demo failed",
    });
  }
}

async function handleUserStyleRecommendations(req, res) {
  try {
    const body = await readJsonBody(req);
    const profile = {
      skinTone: normalizeString(body.skinTone) || "medium",
      handShape: normalizeString(body.handShape) || "short-wide",
      nailLengthPreference: normalizeString(body.nailLengthPreference) || "short",
      occasion: normalizeString(body.occasion) || "daily",
      stylePreference: normalizeString(body.stylePreference) || "daily",
      budget: normalizeString(body.budget) || "mid",
    };
    const topN = Math.max(1, Math.min(10, Number(body.topN || 5)));
    const rules = loadOpsStrategyRules();
    const allStyles = [...mapStylesById(rules).values()];
    const popularityById = loadStylePopularityById();
    const qualityById = loadTryonQualityByStyleId();
    const samples = await loadOfficialSamples();

    const styleSamplesById = new Map(
      (samples.styleSamples || []).map((sample) => [
        `style_${String(sample.id).padStart(2, "0")}`,
        sample,
      ]),
    );

    const recommendations = allStyles
      .map((style) => {
        const popularity = popularityById.get(style.style_id) || null;
        const quality = qualityById.get(style.style_id) || null;
        const scored = buildUserRecommendationScore({
          style,
          popularity,
          quality,
          profile,
        });
        const sample = styleSamplesById.get(style.style_id) || null;

        return {
          style_id: style.style_id,
          style_sample_id: sample?.id || null,
          score: scored.score,
          reasons: scored.reasons,
          risks: scored.risks,
          style_image_url:
            sample?.enhancedStyleUrl || sample?.originalStyleUrl || "",
          style_profile: {
            primary_color: style.primary_color,
            style_category: style.style_category,
            occasion: style.occasion,
            target_persona: style.target_persona,
            price_band: style.price_band,
            trend_keywords: style.trend_keywords,
          },
          popularity: popularity
            ? {
                hotness_score: popularity.hotness_score,
                views: popularity.views,
                tryons: popularity.tryons,
                favorites: popularity.favorites,
                bookings: popularity.bookings,
                recent_growth: popularity.recent_growth,
              }
            : null,
          tryon_quality: quality || {
            decision: "unknown",
            score: null,
            warnings: ["quality_not_available"],
            reasons: [],
          },
        };
      })
      .sort((left, right) => right.score - left.score)
      .slice(0, topN);

    sendJson(res, 200, {
      source_note:
        "Recommendations use official style labels, mock popularity signals, and local try-on quality reports. Mock popularity should be replaced with real user behavior data later.",
      profile,
      recommendations,
      scoring_weights: {
        mock_hotness: "25%",
        occasion_match: "16 points",
        style_preference: "14 points",
        skin_tone_fit: "10 points",
        hand_shape_fit: "8 points",
        budget_fit: "6 points",
        tryon_quality: "+8 / -12 / -30 points",
      },
    });
  } catch (error) {
    sendJson(res, 500, {
      error:
        error instanceof Error
          ? error.message
          : "User style recommendation failed",
    });
  }
}

async function handleOpsDailyReport(req, res) {
  try {
    sendJson(res, 200, parseJsonFile(opsDailyReportPath));
  } catch (error) {
    sendJson(res, 500, {
      error:
        error instanceof Error
          ? `Failed to load ops daily report: ${error.message}`
          : "Failed to load ops daily report",
    });
  }
}

async function imageSourceToAsset(source, fallbackName) {
  if (!source || typeof source !== "string") {
    throw new Error(`Missing image source for ${fallbackName}`);
  }

  if (source.startsWith("data:")) {
    const match = source.match(/^data:(image\/[a-zA-Z0-9.+-]+);base64,(.+)$/);
    if (!match) {
      throw new Error(`Unsupported data URL for ${fallbackName}`);
    }

    const [, mimeType, base64Payload] = match;
    return {
      type: "data-url",
      mimeType,
      buffer: Buffer.from(base64Payload, "base64"),
      source,
      filename: `${fallbackName}.${getMimeExtension(mimeType)}`,
    };
  }

  let parsed;
  try {
    parsed = new URL(source);
  } catch {
    throw new Error(`Invalid image source for ${fallbackName}`);
  }

  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error(`Only HTTP(S) URLs or data URLs are supported for ${fallbackName}`);
  }

  const response = await fetch(parsed, {
    headers: {
      "User-Agent": "manicure-tryon-mvp/0.2",
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch ${fallbackName}: ${response.status}`);
  }

  const mimeType = response.headers.get("content-type") || "image/png";
  const buffer = Buffer.from(await response.arrayBuffer());
  return {
    type: "url",
    mimeType,
    buffer,
    source,
    filename: `${fallbackName}.${getMimeExtension(mimeType)}`,
  };
}

function outputToDataUrl(base64Payload, mimeType = "image/png") {
  return `data:${mimeType};base64,${base64Payload}`;
}

function previewText(value, maxLength = 320) {
  if (value == null) {
    return "";
  }
  const text =
    typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
}

function hashText(value) {
  return createHash("sha256").update(String(value || "")).digest("hex");
}

function summarizeImageSource(source) {
  const text = typeof source === "string" ? source : "";
  if (!text) {
    return {
      kind: "missing",
      length: 0,
      sha256: hashText(""),
    };
  }

  if (text.startsWith("data:")) {
    const [header = "", payload = ""] = text.split(",", 2);
    return {
      kind: "data-url",
      mimeType: header.match(/^data:([^;]+)/)?.[1] || "unknown",
      length: text.length,
      payloadLength: payload.length,
      sha256: hashText(text),
    };
  }

  try {
    const url = new URL(text);
    return {
      kind: "url",
      host: url.host,
      pathname: url.pathname,
      length: text.length,
      sha256: hashText(text),
    };
  } catch {
    return {
      kind: "inline-or-local",
      length: text.length,
      sha256: hashText(text),
    };
  }
}

function summarizeAsset(asset) {
  return {
    inputType: asset.type,
    mimeType: asset.mimeType,
    bytes: asset.buffer.length,
    filename: asset.filename,
    sourceKind: summarizeImageSource(asset.source).kind,
  };
}

function getTryOnModelName(provider) {
  if (provider === "mock") {
    return "mock-tryon-v1";
  }

  if (provider === "doubao") {
    const config = getDoubaoModelConfig();
    return `${config.model}${config.version ? `@${config.version}` : ""}`;
  }

  return process.env.OPENAI_IMAGE_MODEL || "gpt-image-1";
}

async function appendApiCallLog(entry) {
  const payload = {
    schemaVersion: 1,
    timestamp: new Date().toISOString(),
    ...entry,
  };

  try {
    await mkdir(path.dirname(apiCallLogPath), { recursive: true });
    await appendFile(apiCallLogPath, `${JSON.stringify(payload)}\n`, "utf8");
  } catch (error) {
    console.warn(
      "Failed to write API call log:",
      error instanceof Error ? error.message : error,
    );
  }
}

function buildHttpError(prefix, response, payload) {
  const detail =
    payload?.error?.message ||
    payload?.error?.code ||
    payload?.message ||
    payload?.msg ||
    previewText(payload);
  return new Error(`${prefix} (${response.status}): ${detail}`);
}

async function callOpenAiTryOn({ prompt, handAsset, styleAsset, guideAsset }) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    throw new Error("OPENAI_API_KEY is not configured");
  }

  const form = new FormData();
  form.append("model", process.env.OPENAI_IMAGE_MODEL || "gpt-image-1");
  form.append("prompt", prompt);
  form.append("size", process.env.OPENAI_IMAGE_SIZE || "1536x1024");
  form.append("quality", process.env.OPENAI_IMAGE_QUALITY || "medium");
  form.append("output_format", process.env.OPENAI_IMAGE_OUTPUT_FORMAT || "png");

  for (const asset of [handAsset, styleAsset, guideAsset]) {
    form.append(
      "image",
      new Blob([asset.buffer], { type: asset.mimeType }),
      asset.filename,
    );
  }

  const response = await fetch("https://api.openai.com/v1/images/edits", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
    },
    body: form,
  });

  const payload = await response.json();
  if (!response.ok) {
    const message = payload?.error?.message || "OpenAI image edit failed";
    throw new Error(message);
  }

  const first = payload?.data?.[0];
  if (!first) {
    throw new Error("OpenAI did not return an image");
  }

  if (first.b64_json) {
    return {
      imageDataUrl: outputToDataUrl(
        first.b64_json,
        `image/${process.env.OPENAI_IMAGE_OUTPUT_FORMAT || "png"}`,
      ),
      raw: payload,
      model: process.env.OPENAI_IMAGE_MODEL || "gpt-image-1",
    };
  }

  if (first.url) {
    const imageResponse = await fetch(first.url);
    const mimeType = imageResponse.headers.get("content-type") || "image/png";
    const buffer = Buffer.from(await imageResponse.arrayBuffer());
    return {
      imageDataUrl: outputToDataUrl(buffer.toString("base64"), mimeType),
      raw: payload,
      model: process.env.OPENAI_IMAGE_MODEL || "gpt-image-1",
    };
  }

  throw new Error("OpenAI response did not include b64_json or url");
}

async function callMockTryOn({ handAsset, guideAsset }) {
  const outputAsset = guideAsset?.buffer?.length ? guideAsset : handAsset;
  return {
    imageDataUrl: outputToDataUrl(outputAsset.buffer.toString("base64"), outputAsset.mimeType),
    raw: {
      usage: {
        note: "mock provider does not call external image generation APIs",
      },
    },
    model: "mock-tryon-v1",
    requestBodyPreview: {
      mode: "copy-guide-or-hand",
      source: outputAsset === guideAsset ? "guideImage" : "handImage",
    },
  };
}

function getDoubaoImageInput(asset) {
  // Public URLs are the safest input format. For local uploads we pass base64 data URLs.
  return asset.source;
}

function getDoubaoModelConfig() {
  return {
    model: process.env.DOUBAO_IMAGE_MODEL || "doubao-seedream-4.0",
    version: process.env.DOUBAO_IMAGE_VERSION || "250828",
    endpoint:
      process.env.DOUBAO_IMAGE_ENDPOINT ||
      "https://ark.cn-beijing.volces.com/api/v3/images/generations",
    size: process.env.DOUBAO_IMAGE_SIZE || "2K",
    responseFormat: process.env.DOUBAO_IMAGE_RESPONSE_FORMAT || "url",
    watermark: process.env.DOUBAO_IMAGE_WATERMARK === "true",
    optimizePromptMode: process.env.DOUBAO_OPTIMIZE_PROMPT_MODE || "",
    useLegacyImageField: process.env.DOUBAO_USE_LEGACY_IMAGE_FIELD === "true",
  };
}

function buildDoubaoRequestBody({
  prompt,
  handAsset,
  styleAsset,
  guideAsset,
  config,
}) {
  const referenceImages = [
    getDoubaoImageInput(handAsset),
    getDoubaoImageInput(styleAsset),
    getDoubaoImageInput(guideAsset),
  ];

  const body = {
    model: config.model,
    prompt,
    size: config.size,
    response_format: config.responseFormat,
    watermark: config.watermark,
  };

  if (config.version) {
    body.version = config.version;
  }

  if (config.optimizePromptMode) {
    body.optimize_prompt_options = {
      mode: config.optimizePromptMode,
    };
  }

  if (config.useLegacyImageField) {
    body.image = referenceImages;
  } else {
    body.reference_images = referenceImages;
  }

  return body;
}

async function callDoubaoTryOn({ prompt, handAsset, styleAsset, guideAsset }) {
  const apiKey = process.env.ARK_API_KEY || process.env.DOUBAO_API_KEY;
  if (!apiKey) {
    throw new Error("ARK_API_KEY or DOUBAO_API_KEY is not configured");
  }

  const config = getDoubaoModelConfig();
  const requestBody = buildDoubaoRequestBody({
    prompt,
    handAsset,
    styleAsset,
    guideAsset,
    config,
  });

  const response = await fetch(
    config.endpoint,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(requestBody),
    },
  );

  const payload = await response.json();
  if (!response.ok) {
    throw buildHttpError("Doubao image generation failed", response, payload);
  }

  const first = payload?.data?.[0];
  if (!first) {
    throw new Error("Doubao did not return an image");
  }

  if (first.b64_json) {
    return {
      imageDataUrl: outputToDataUrl(first.b64_json, "image/png"),
      raw: payload,
      model: `${config.model}${config.version ? `@${config.version}` : ""}`,
      requestBodyPreview: {
        model: requestBody.model,
        version: requestBody.version || null,
        size: requestBody.size,
        response_format: requestBody.response_format,
        reference_images_count:
          requestBody.reference_images?.length || requestBody.image?.length || 0,
        field_used: requestBody.reference_images ? "reference_images" : "image",
      },
    };
  }

  if (first.url) {
    const imageResponse = await fetch(first.url);
    const mimeType = imageResponse.headers.get("content-type") || "image/png";
    const buffer = Buffer.from(await imageResponse.arrayBuffer());
    return {
      imageDataUrl: outputToDataUrl(buffer.toString("base64"), mimeType),
      raw: payload,
      model: `${config.model}${config.version ? `@${config.version}` : ""}`,
      requestBodyPreview: {
        model: requestBody.model,
        version: requestBody.version || null,
        size: requestBody.size,
        response_format: requestBody.response_format,
        reference_images_count:
          requestBody.reference_images?.length || requestBody.image?.length || 0,
        field_used: requestBody.reference_images ? "reference_images" : "image",
      },
    };
  }

  throw new Error("Doubao response did not include b64_json or url");
}

async function handleTryOnGeneration(req, res) {
  const requestId = randomUUID();
  const startedAt = Date.now();
  let logEntry = {
    requestId,
    route: "/api/generate-tryon",
    method: req.method,
  };

  try {
    const body = await readJsonBody(req);
    const provider =
      body.provider === "doubao"
        ? "doubao"
        : body.provider === "mock"
          ? "mock"
          : "openai";
    const prompt = buildTryOnPrompt(body.prompt);

    logEntry = {
      ...logEntry,
      provider,
      requestedModel: getTryOnModelName(provider),
      prompt: {
        hasCustomPrompt: Boolean(body.prompt?.trim()),
        sha256: hashText(prompt),
        preview: previewText(prompt, 260),
      },
      retry: {
        attempt:
          typeof body.retryAttempt === "number" ? body.retryAttempt : null,
        preset:
          typeof body.retryPreset === "string" ? body.retryPreset : null,
      },
      inputSources: {
        handImage: summarizeImageSource(body.handImage),
        styleImage: summarizeImageSource(body.styleImage),
        guideImage: summarizeImageSource(body.guideImage),
      },
    };

    const handAsset = await imageSourceToAsset(body.handImage, "hand-image");
    const styleAsset = await imageSourceToAsset(body.styleImage, "style-image");
    const guideAsset = await imageSourceToAsset(body.guideImage, "guide-image");

    logEntry.inputAssets = {
      handImage: summarizeAsset(handAsset),
      styleImage: summarizeAsset(styleAsset),
      guideImage: summarizeAsset(guideAsset),
    };

    const result =
      provider === "doubao"
        ? await callDoubaoTryOn({ prompt, handAsset, styleAsset, guideAsset })
        : provider === "mock"
          ? await callMockTryOn({ handAsset, guideAsset })
          : await callOpenAiTryOn({ prompt, handAsset, styleAsset, guideAsset });

    await appendApiCallLog({
      ...logEntry,
      status: "success",
      durationMs: Date.now() - startedAt,
      response: {
        model: result.model,
        hasImageDataUrl: Boolean(result.imageDataUrl),
        imageDataUrlLength: result.imageDataUrl?.length || 0,
        usage: result.raw?.usage || null,
        providerDebug: result.requestBodyPreview || null,
      },
    });

    sendJson(res, 200, {
      requestId,
      provider,
      model: result.model,
      promptUsed: prompt,
      imageDataUrl: result.imageDataUrl,
      usage: result.raw?.usage || null,
      providerDebug: result.requestBodyPreview || null,
    });
  } catch (error) {
    await appendApiCallLog({
      ...logEntry,
      status: "error",
      durationMs: Date.now() - startedAt,
      error: {
        message: error instanceof Error ? error.message : "Generation failed",
      },
    });

    sendJson(res, 500, {
      requestId,
      error: error instanceof Error ? error.message : "Generation failed",
    });
  }
}

async function handleOfficialSamples(reqUrl, res) {
  try {
    const samples = await loadOfficialSamples();
    const handIndex = Number(reqUrl.searchParams.get("handIndex") || 0);
    const styleIndex = Number(reqUrl.searchParams.get("styleIndex") || 0);

    const selectedHand = samples.handSamples[handIndex] || null;
    const selectedStyle = samples.styleSamples[styleIndex] || null;

    sendJson(res, 200, {
      workbookPath: samples.workbookPath,
      counts: samples.counts,
      handSamples: samples.handSamples,
      styleSamples: samples.styleSamples,
      selectedPair:
        selectedHand && selectedStyle
          ? {
              hand: selectedHand,
              style: selectedStyle,
            }
          : null,
    });
  } catch (error) {
    sendJson(res, 500, {
      error:
        error instanceof Error
          ? `Failed to load official workbook samples: ${error.message}`
          : "Failed to load official workbook samples",
    });
  }
}

async function serveStaticFile(res, pathname) {
  const requestedPath = pathname === "/" ? "/index.html" : pathname;
  const safePath = path.normalize(requestedPath).replace(/^(\.\.[/\\])+/, "");
  const filePath = path.join(publicDir, safePath);

  try {
    await access(filePath);
    const fileStats = await stat(filePath);
    if (!fileStats.isFile()) {
      sendJson(res, 404, { error: "Not found" });
      return;
    }

    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, {
      "Content-Type": mimeTypes[ext] || "application/octet-stream",
      "Cache-Control": ext === ".html" ? "no-store" : "public, max-age=300",
    });
    createReadStream(filePath).pipe(res);
  } catch {
    sendJson(res, 404, { error: "Not found" });
  }
}

async function proxyImage(reqUrl, res) {
  const imageUrl = reqUrl.searchParams.get("url");
  if (!imageUrl) {
    sendJson(res, 400, { error: "Missing url parameter" });
    return;
  }

  let parsed;
  try {
    parsed = new URL(imageUrl);
  } catch {
    sendJson(res, 400, { error: "Invalid image URL" });
    return;
  }

  if (!["http:", "https:"].includes(parsed.protocol)) {
    sendJson(res, 400, { error: "Only HTTP(S) URLs are supported" });
    return;
  }

  try {
    const upstream = await fetch(parsed, {
      headers: {
        "User-Agent": "manicure-tryon-mvp/0.1",
      },
    });

    if (!upstream.ok || !upstream.body) {
      sendJson(res, upstream.status || 502, {
        error: "Failed to fetch remote image",
      });
      return;
    }

    res.writeHead(200, {
      "Access-Control-Allow-Origin": "*",
      "Cache-Control": "public, max-age=300",
      "Content-Type":
        upstream.headers.get("content-type") || "application/octet-stream",
    });

    upstream.body.pipeTo(
      new WritableStream({
        write(chunk) {
          return new Promise((resolve, reject) => {
            res.write(Buffer.from(chunk), (error) => {
              if (error) {
                reject(error);
                return;
              }
              resolve();
            });
          });
        },
        close() {
          res.end();
        },
        abort(error) {
          res.destroy(error);
        },
      }),
    ).catch((error) => {
      if (!res.headersSent) {
        sendJson(res, 502, { error: error.message });
        return;
      }
      res.destroy(error);
    });
  } catch (error) {
    sendJson(res, 502, { error: error.message });
  }
}

const server = http.createServer(async (req, res) => {
  if (!req.url) {
    sendJson(res, 400, { error: "Invalid request" });
    return;
  }

  const reqUrl = new URL(req.url, `http://${req.headers.host}`);

  if (reqUrl.pathname === "/proxy-image") {
    await proxyImage(reqUrl, res);
    return;
  }

  if (req.method === "POST" && reqUrl.pathname === "/api/generate-tryon") {
    await handleTryOnGeneration(req, res);
    return;
  }

  if (req.method === "GET" && reqUrl.pathname === "/api/official-samples") {
    await handleOfficialSamples(reqUrl, res);
    return;
  }

  if (req.method === "POST" && reqUrl.pathname === "/api/ops-copilot-demo") {
    await handleOpsCopilotDemo(req, res);
    return;
  }

  if (req.method === "POST" && reqUrl.pathname === "/api/user-style-recommendations") {
    await handleUserStyleRecommendations(req, res);
    return;
  }

  if (req.method === "GET" && reqUrl.pathname === "/api/ops-daily-report") {
    await handleOpsDailyReport(req, res);
    return;
  }

  await serveStaticFile(res, reqUrl.pathname);
});

server.listen(port, () => {
  console.log(`Manicure try-on MVP running at http://localhost:${port}`);
});
