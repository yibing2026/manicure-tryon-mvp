const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");

const elements = {
  handFile: document.getElementById("handFile"),
  styleFile: document.getElementById("styleFile"),
  handUrl: document.getElementById("handUrl"),
  styleUrl: document.getElementById("styleUrl"),
  loadHandUrl: document.getElementById("loadHandUrl"),
  loadStyleUrl: document.getElementById("loadStyleUrl"),
  resetLayout: document.getElementById("resetLayout"),
  autoSpread: document.getElementById("autoSpread"),
  opacity: document.getElementById("opacity"),
  shine: document.getElementById("shine"),
  feather: document.getElementById("feather"),
  nailSelect: document.getElementById("nailSelect"),
  offsetX: document.getElementById("offsetX"),
  offsetY: document.getElementById("offsetY"),
  widthScale: document.getElementById("widthScale"),
  heightScale: document.getElementById("heightScale"),
  rotation: document.getElementById("rotation"),
  download: document.getElementById("download"),
  status: document.getElementById("status"),
  provider: document.getElementById("provider"),
  customPrompt: document.getElementById("customPrompt"),
  generateTryOn: document.getElementById("generateTryOn"),
  generatedImage: document.getElementById("generatedImage"),
  generatedEmpty: document.getElementById("generatedEmpty"),
  generationMeta: document.getElementById("generationMeta"),
  officialHandSelect: document.getElementById("officialHandSelect"),
  officialStyleSelect: document.getElementById("officialStyleSelect"),
  loadOfficialPair: document.getElementById("loadOfficialPair"),
  refreshOfficialSamples: document.getElementById("refreshOfficialSamples"),
  officialSampleMeta: document.getElementById("officialSampleMeta"),
  skinTone: document.getElementById("skinTone"),
  handShape: document.getElementById("handShape"),
  userOccasion: document.getElementById("userOccasion"),
  userStylePreference: document.getElementById("userStylePreference"),
  nailLengthPreference: document.getElementById("nailLengthPreference"),
  userBudget: document.getElementById("userBudget"),
  getRecommendations: document.getElementById("getRecommendations"),
  recommendationMeta: document.getElementById("recommendationMeta"),
  recommendationsList: document.getElementById("recommendationsList"),
};

const nailNames = ["拇指", "食指", "中指", "无名指", "小指"];
const baseLayout = [
  { x: 0.18, y: 0.68, w: 0.18, h: 0.24, rotation: -24 },
  { x: 0.33, y: 0.45, w: 0.14, h: 0.21, rotation: -10 },
  { x: 0.48, y: 0.37, w: 0.14, h: 0.23, rotation: -2 },
  { x: 0.62, y: 0.4, w: 0.14, h: 0.21, rotation: 7 },
  { x: 0.76, y: 0.54, w: 0.12, h: 0.18, rotation: 20 },
];

const state = {
  handImage: null,
  styleImage: null,
  handSource: "",
  styleSource: "",
  activeNail: 0,
  overlayOpacity: 0.84,
  shineStrength: 0.26,
  feather: 6,
  nails: createNails(1, 1),
  generatedImageUrl: "",
  officialSamples: {
    handSamples: [],
    styleSamples: [],
  },
  recommendations: [],
};

function createNails(width, height) {
  return baseLayout.map((item) => ({
    x: item.x * width,
    y: item.y * height,
    w: item.w * width,
    h: item.h * height,
    rotation: item.rotation,
  }));
}

function setStatus(message) {
  elements.status.textContent = message;
}

function populateNailSelect() {
  elements.nailSelect.innerHTML = nailNames
    .map(
      (name, index) =>
        `<option value="${index}">${index + 1}. ${name}</option>`,
    )
    .join("");
}

function syncControlsFromState() {
  const nail = state.nails[state.activeNail];
  const base = createNails(canvas.width, canvas.height)[state.activeNail];

  elements.nailSelect.value = String(state.activeNail);
  elements.offsetX.value = String(Math.round(nail.x - base.x));
  elements.offsetY.value = String(Math.round(nail.y - base.y));
  elements.widthScale.value = String(Math.round((nail.w / base.w) * 100));
  elements.heightScale.value = String(Math.round((nail.h / base.h) * 100));
  elements.rotation.value = String(Math.round(nail.rotation));
}

function updateNailFromControls() {
  const idx = Number(elements.nailSelect.value);
  state.activeNail = idx;

  const base = createNails(canvas.width, canvas.height)[idx];
  state.nails[idx] = {
    x: base.x + Number(elements.offsetX.value),
    y: base.y + Number(elements.offsetY.value),
    w: base.w * (Number(elements.widthScale.value) / 100),
    h: base.h * (Number(elements.heightScale.value) / 100),
    rotation: Number(elements.rotation.value),
  };

  drawScene();
}

function fitCanvasToImage(image) {
  const maxWidth = 900;
  const maxHeight = 1200;
  const ratio = Math.min(maxWidth / image.width, maxHeight / image.height, 1);
  canvas.width = Math.round(image.width * ratio);
  canvas.height = Math.round(image.height * ratio);
  state.nails = createNails(canvas.width, canvas.height);
  syncControlsFromState();
}

async function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("文件读取失败"));
    reader.readAsDataURL(file);
  });
}

async function loadImage(source) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("图片加载失败"));
    image.src = source;
  });
}

async function loadRemoteViaProxy(url) {
  const proxiedUrl = `/proxy-image?url=${encodeURIComponent(url)}`;
  return loadImage(proxiedUrl);
}

function drawPlaceholder() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#fbf5ee";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  ctx.fillStyle = "#8f786b";
  ctx.font = "600 28px Segoe UI";
  ctx.fillText("上传手图后开始试戴预览", 52, 72);
  ctx.font = "18px Segoe UI";
  ctx.fillStyle = "#a18d81";
  ctx.fillText("继续添加款式图，再微调每个甲面的位置。", 52, 106);

  state.nails.forEach((nail, index) => {
    ctx.save();
    ctx.translate(nail.x, nail.y);
    ctx.rotate((nail.rotation * Math.PI) / 180);
    ctx.strokeStyle = index === state.activeNail ? "#c55c3b" : "#cbb5a8";
    ctx.lineWidth = index === state.activeNail ? 4 : 2;
    ctx.setLineDash([10, 8]);
    ctx.beginPath();
    ctx.ellipse(0, 0, nail.w / 2, nail.h / 2, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  });
}

function drawNailTexture(nail) {
  ctx.save();
  ctx.translate(nail.x, nail.y);
  ctx.rotate((nail.rotation * Math.PI) / 180);
  ctx.filter = `blur(${state.feather}px)`;
  ctx.beginPath();
  ctx.ellipse(0, 0, nail.w / 2, nail.h / 2, 0, 0, Math.PI * 2);
  ctx.clip();

  if (state.styleImage) {
    ctx.globalAlpha = state.overlayOpacity;
    const sourceRatio = state.styleImage.width / state.styleImage.height;
    const targetRatio = nail.w / nail.h;
    let drawWidth = nail.w;
    let drawHeight = nail.h;
    let drawX = -nail.w / 2;
    let drawY = -nail.h / 2;

    // Cover the nail region with the style image to preserve texture continuity.
    if (sourceRatio > targetRatio) {
      drawHeight = nail.h;
      drawWidth = drawHeight * sourceRatio;
      drawX = -drawWidth / 2;
    } else {
      drawWidth = nail.w;
      drawHeight = drawWidth / sourceRatio;
      drawY = -drawHeight / 2;
    }

    ctx.drawImage(state.styleImage, drawX, drawY, drawWidth, drawHeight);
  } else {
    ctx.globalAlpha = state.overlayOpacity;
    ctx.fillStyle = "rgba(197, 92, 59, 0.78)";
    ctx.fill();
  }

  ctx.filter = "none";
  ctx.globalAlpha = state.shineStrength;
  ctx.fillStyle = "#ffffff";
  ctx.beginPath();
  ctx.ellipse(-nail.w * 0.1, -nail.h * 0.18, nail.w * 0.13, nail.h * 0.3, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function drawSelectionRing(nail) {
  ctx.save();
  ctx.translate(nail.x, nail.y);
  ctx.rotate((nail.rotation * Math.PI) / 180);
  ctx.strokeStyle = "#fff8f3";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.ellipse(0, 0, nail.w / 2 + 6, nail.h / 2 + 6, 0, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();
}

function drawScene() {
  if (!state.handImage) {
    drawPlaceholder();
    return;
  }

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(state.handImage, 0, 0, canvas.width, canvas.height);

  state.nails.forEach((nail) => drawNailTexture(nail));
  drawSelectionRing(state.nails[state.activeNail]);
}

function selectNailFromPoint(x, y) {
  let nextIndex = state.activeNail;
  let bestScore = Number.POSITIVE_INFINITY;

  state.nails.forEach((nail, index) => {
    const distance = Math.hypot(x - nail.x, y - nail.y);
    const score = distance / Math.max(nail.w, nail.h);
    if (score < bestScore && score < 1.15) {
      bestScore = score;
      nextIndex = index;
    }
  });

  state.activeNail = nextIndex;
  syncControlsFromState();
  drawScene();
}

async function handleFileUpload(input, key, successText) {
  const file = input.files?.[0];
  if (!file) {
    return;
  }

  try {
    const source = await readFileAsDataUrl(file);
    const image = await loadImage(source);
    state[key] = image;
    if (key === "handImage") {
      state.handSource = source;
    }
    if (key === "styleImage") {
      state.styleSource = source;
    }

    if (key === "handImage") {
      fitCanvasToImage(image);
    }

    drawScene();
    setStatus(successText);
  } catch (error) {
    setStatus(`加载失败：${error.message}`);
  }
}

async function handleUrlLoad(field, key, successText) {
  const url = field.value.trim();
  if (!url) {
    setStatus("请先输入图片 URL。");
    return;
  }

  setStatus("正在加载远程图片...");

  try {
    const image = await loadRemoteViaProxy(url);
    state[key] = image;
    if (key === "handImage") {
      state.handSource = url;
    }
    if (key === "styleImage") {
      state.styleSource = url;
    }

    if (key === "handImage") {
      fitCanvasToImage(image);
    }

    drawScene();
    setStatus(successText);
  } catch (error) {
    setStatus(`远程图片加载失败：${error.message}`);
  }
}

async function loadImagesIntoState(handSource, styleSource, successText) {
  setStatus("正在加载样例图片...");

  try {
    const [handImage, styleImage] = await Promise.all([
      loadRemoteViaProxy(handSource),
      loadRemoteViaProxy(styleSource),
    ]);

    state.handImage = handImage;
    state.styleImage = styleImage;
    state.handSource = handSource;
    state.styleSource = styleSource;

    fitCanvasToImage(handImage);
    drawScene();
    setStatus(successText);
  } catch (error) {
    setStatus(`样例加载失败：${error.message}`);
  }
}

function resetLayout() {
  state.nails = createNails(canvas.width, canvas.height);
  syncControlsFromState();
  drawScene();
  setStatus("已重置甲面布局。");
}

function autoSpread() {
  state.nails = state.nails.map((nail, index) => ({
    ...nail,
    x: nail.x + (index - 2) * 8,
    y: nail.y - Math.abs(index - 2) * 6,
    w: nail.w * 1.04,
  }));
  syncControlsFromState();
  drawScene();
  setStatus("已展开甲面间距，适合更张开的手势。");
}

function downloadPreview() {
  const link = document.createElement("a");
  link.href = canvas.toDataURL("image/png");
  link.download = "manicure-tryon-preview.png";
  link.click();
}

function updateGeneratedPreview(imageUrl, metaText) {
  state.generatedImageUrl = imageUrl;
  if (imageUrl) {
    elements.generatedImage.src = imageUrl;
    elements.generatedImage.hidden = false;
    elements.generatedEmpty.hidden = true;
  } else {
    elements.generatedImage.hidden = true;
    elements.generatedEmpty.hidden = false;
  }
  elements.generationMeta.textContent = metaText;
}

function formatProviderDebug(debugInfo) {
  if (!debugInfo) {
    return "";
  }
  const parts = [
    debugInfo.model ? `model=${debugInfo.model}` : "",
    debugInfo.version ? `version=${debugInfo.version}` : "",
    debugInfo.field_used ? `field=${debugInfo.field_used}` : "",
    debugInfo.reference_images_count != null
      ? `refs=${debugInfo.reference_images_count}`
      : "",
  ].filter(Boolean);
  return parts.length ? ` (${parts.join(", ")})` : "";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function populateOfficialSelects() {
  const handOptions = state.officialSamples.handSamples
    .map(
      (sample, index) =>
        `<option value="${index}">手图 ${String(sample.id).padStart(2, "0")}</option>`,
    )
    .join("");
  const styleOptions = state.officialSamples.styleSamples
    .map(
      (sample, index) =>
        `<option value="${index}">款式 ${String(sample.id).padStart(2, "0")}</option>`,
    )
    .join("");

  elements.officialHandSelect.innerHTML =
    handOptions || '<option value="">无可用手图样例</option>';
  elements.officialStyleSelect.innerHTML =
    styleOptions || '<option value="">无可用款式样例</option>';
}

function renderRecommendations(recommendations) {
  state.recommendations = recommendations;
  if (!recommendations.length) {
    elements.recommendationsList.innerHTML =
      '<p class="status">暂无推荐结果，请调整画像后重试。</p>';
    return;
  }

  elements.recommendationsList.innerHTML = recommendations
    .map((item, index) => {
      const reasons = (item.reasons || []).slice(0, 3);
      const risks = item.risks || [];
      return `
        <article class="recommendation-card">
          <div class="recommendation-rank">Top ${index + 1}</div>
          <div>
            <h3>${escapeHtml(item.style_id)} · ${escapeHtml(item.style_profile?.style_category || "style")}</h3>
            <p class="recommendation-score">推荐分 ${item.score} / 99 · 热度 ${item.popularity?.hotness_score ?? "mock"}</p>
          </div>
          ${item.style_image_url ? `<img src="/proxy-image?url=${encodeURIComponent(item.style_image_url)}" alt="${escapeHtml(item.style_id)} 款式图" />` : ""}
          <ul>
            ${reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}
          </ul>
          ${risks.length ? `<p class="recommendation-risk">${escapeHtml(risks[0])}</p>` : ""}
          <button class="secondary load-recommendation" data-style-id="${escapeHtml(item.style_id)}">
            加载该款式试戴
          </button>
        </article>
      `;
    })
    .join("");
}

async function fetchUserRecommendations() {
  elements.getRecommendations.disabled = true;
  elements.recommendationMeta.textContent = "正在根据用户画像生成推荐...";

  const payload = {
    skinTone: elements.skinTone.value,
    handShape: elements.handShape.value,
    occasion: elements.userOccasion.value,
    stylePreference: elements.userStylePreference.value,
    nailLengthPreference: elements.nailLengthPreference.value,
    budget: elements.userBudget.value,
    topN: 5,
  };

  try {
    const response = await fetch("/api/user-style-recommendations", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.error || "推荐失败");
    }

    renderRecommendations(result.recommendations || []);
    elements.recommendationMeta.textContent =
      "已生成推荐：依据官方款式标签、mock 热度、肤色/手型适配和试戴质检结果。";
  } catch (error) {
    elements.recommendationMeta.textContent = `推荐失败：${error.message}`;
  } finally {
    elements.getRecommendations.disabled = false;
  }
}

async function loadRecommendedStyle(styleId) {
  const recommendation = state.recommendations.find((item) => item.style_id === styleId);
  if (!recommendation?.style_image_url) {
    setStatus("推荐款式缺少可加载的款式图 URL。");
    return;
  }

  setStatus(`正在加载推荐款式 ${styleId}...`);

  try {
    const styleImage = await loadRemoteViaProxy(recommendation.style_image_url);
    state.styleImage = styleImage;
    state.styleSource = recommendation.style_image_url;

    if (!state.handImage) {
      const handIndex = Number(elements.officialHandSelect.value || 0);
      const handSample = state.officialSamples.handSamples[handIndex];
      if (!handSample?.handUrl) {
        setStatus("请先上传或加载一张手图，再使用推荐款式试戴。");
        return;
      }
      const handImage = await loadRemoteViaProxy(handSample.handUrl);
      state.handImage = handImage;
      state.handSource = handSample.handUrl;
      fitCanvasToImage(handImage);
    }

    drawScene();
    setStatus(`已加载推荐款式 ${styleId}，可以继续微调或生成正式试戴图。`);
  } catch (error) {
    setStatus(`推荐款式加载失败：${error.message}`);
  }
}

function syncStyleSelectToHandSelection() {
  const handIndex = Number(elements.officialHandSelect.value);
  const handSample = state.officialSamples.handSamples[handIndex];
  if (!handSample?.linkedEnhancedStyleUrl) {
    return;
  }

  const matchedIndex = state.officialSamples.styleSamples.findIndex(
    (sample) => sample.enhancedStyleUrl === handSample.linkedEnhancedStyleUrl,
  );

  if (matchedIndex >= 0) {
    elements.officialStyleSelect.value = String(matchedIndex);
  }
}

async function fetchOfficialSamples() {
  elements.refreshOfficialSamples.disabled = true;
  elements.loadOfficialPair.disabled = true;
  elements.officialSampleMeta.textContent = "正在读取官方评测表...";

  try {
    const response = await fetch("/api/official-samples");
    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.error || "读取官方样例失败");
    }

    state.officialSamples = {
      handSamples: result.handSamples || [],
      styleSamples: result.styleSamples || [],
    };
    populateOfficialSelects();
    syncStyleSelectToHandSelection();
    elements.officialSampleMeta.textContent =
      `已读取官方样例：${result.counts.handSamples} 张手图，${result.counts.styleSamples} 张款式图。`;
  } catch (error) {
    elements.officialSampleMeta.textContent = `官方样例读取失败：${error.message}`;
  } finally {
    elements.refreshOfficialSamples.disabled = false;
    elements.loadOfficialPair.disabled = false;
  }
}

async function loadOfficialPair() {
  const handIndex = Number(elements.officialHandSelect.value);
  const styleIndex = Number(elements.officialStyleSelect.value);
  const handSample = state.officialSamples.handSamples[handIndex];
  const styleSample = state.officialSamples.styleSamples[styleIndex];

  if (!handSample || !styleSample) {
    setStatus("请先选择有效的官方样例。");
    return;
  }

  await loadImagesIntoState(
    handSample.handUrl,
    styleSample.enhancedStyleUrl,
    `已加载官方样例：手图 ${handSample.id} + 款式 ${styleSample.id}。`,
  );
}

async function generateTryOn() {
  if (!state.handSource || !state.styleSource) {
    setStatus("请先准备手图和款式图，再发起正式生成。");
    return;
  }

  const payload = {
    provider: elements.provider.value,
    handImage: state.handSource,
    styleImage: state.styleSource,
    guideImage: canvas.toDataURL("image/png"),
    prompt: elements.customPrompt.value.trim(),
  };

  elements.generateTryOn.disabled = true;
  setStatus("正在调用图像生成接口，请稍等...");
  elements.generationMeta.textContent = "生成中...";

  try {
    const response = await fetch("/api/generate-tryon", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    const result = await response.json();

    if (!response.ok) {
      const error = new Error(result.error || "生成失败");
      error.requestId = result.requestId;
      throw error;
    }

    updateGeneratedPreview(
      result.imageDataUrl,
      `已通过 ${result.provider} / ${result.model} 生成正式试戴图。请求 ID：${result.requestId || "未返回"}。${formatProviderDebug(result.providerDebug)}`,
    );
    setStatus("正式试戴图生成完成。");
  } catch (error) {
    updateGeneratedPreview("", `正式试戴图生成失败。${error.requestId ? `请求 ID：${error.requestId}。` : ""}`);
    setStatus(`接口调用失败：${error.message}`);
  } finally {
    elements.generateTryOn.disabled = false;
  }
}

function bindEvents() {
  populateNailSelect();
  syncControlsFromState();
  drawPlaceholder();

  elements.handFile.addEventListener("change", () =>
    handleFileUpload(elements.handFile, "handImage", "手图加载完成。"),
  );
  elements.styleFile.addEventListener("change", () =>
    handleFileUpload(elements.styleFile, "styleImage", "款式图加载完成。"),
  );
  elements.loadHandUrl.addEventListener("click", () =>
    handleUrlLoad(elements.handUrl, "handImage", "手图 URL 加载完成。"),
  );
  elements.loadStyleUrl.addEventListener("click", () =>
    handleUrlLoad(elements.styleUrl, "styleImage", "款式图 URL 加载完成。"),
  );

  elements.resetLayout.addEventListener("click", resetLayout);
  elements.autoSpread.addEventListener("click", autoSpread);
  elements.download.addEventListener("click", downloadPreview);
  elements.generateTryOn.addEventListener("click", generateTryOn);
  elements.loadOfficialPair.addEventListener("click", loadOfficialPair);
  elements.refreshOfficialSamples.addEventListener("click", fetchOfficialSamples);
  elements.officialHandSelect.addEventListener("change", syncStyleSelectToHandSelection);
  elements.getRecommendations.addEventListener("click", fetchUserRecommendations);
  elements.recommendationsList.addEventListener("click", (event) => {
    const button = event.target.closest(".load-recommendation");
    if (!button) {
      return;
    }
    loadRecommendedStyle(button.dataset.styleId);
  });

  elements.opacity.addEventListener("input", () => {
    state.overlayOpacity = Number(elements.opacity.value) / 100;
    drawScene();
  });
  elements.shine.addEventListener("input", () => {
    state.shineStrength = Number(elements.shine.value) / 100;
    drawScene();
  });
  elements.feather.addEventListener("input", () => {
    state.feather = Number(elements.feather.value);
    drawScene();
  });

  [
    elements.nailSelect,
    elements.offsetX,
    elements.offsetY,
    elements.widthScale,
    elements.heightScale,
    elements.rotation,
  ].forEach((element) => {
    element.addEventListener("input", updateNailFromControls);
  });

  canvas.addEventListener("click", (event) => {
    const rect = canvas.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * canvas.width;
    const y = ((event.clientY - rect.top) / rect.height) * canvas.height;
    selectNailFromPoint(x, y);
  });

  fetchOfficialSamples();
}

bindEvents();
