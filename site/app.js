(() => {
  "use strict";

  const demoData = window.DEMO_DATA;
  if (!demoData || !Array.isArray(demoData.scenarios)) {
    throw new Error("固定回答データを読み込めませんでした");
  }

  const SHINDO_COLOR_7 = "#9C27B0";
  const SHINDO_COLOR_6 = "#E53935";
  const SHINDO_COLOR_5 = "#FB8C00";
  const SHINDO_COLOR_OTHER = "#FDD835";
  const REASONING_DELAY_MS = 1500;

  const messages = document.getElementById("messages");
  const quickReplySlot = document.getElementById("quick-reply-slot");
  const chatForm = document.getElementById("chat-form");
  const messageInput = document.getElementById("message-input");
  const sendButton = document.getElementById("send-button");
  const formStatus = document.getElementById("form-status");
  const mapStatus = document.getElementById("map-status");

  const selectedScenarioKeys = new Set();
  const askedFollowUps = new Map();
  const markerByScenarioKey = new Map();
  let currentScenario = null;
  let processing = false;

  const map = L.map("map", { zoomControl: true }).setView([37.1, 137.3], 8);
  const tileLayer = L.tileLayer(
    "https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png",
    {
      attribution: "地図: 国土地理院（淡色地図）",
      maxZoom: 18,
    },
  ).addTo(map);
  const markerLayer = L.layerGroup().addTo(map);

  tileLayer.on("tileerror", () => {
    mapStatus.hidden = false;
    mapStatus.textContent = "地図背景を取得できません。補償額マーカーは引き続き表示できます。";
  });
  tileLayer.on("load", () => {
    mapStatus.hidden = true;
  });

  function colorForShindo(shindoClass) {
    if (shindoClass === "7") return SHINDO_COLOR_7;
    if (typeof shindoClass === "string" && shindoClass.startsWith("6")) {
      return SHINDO_COLOR_6;
    }
    if (typeof shindoClass === "string" && shindoClass.startsWith("5")) {
      return SHINDO_COLOR_5;
    }
    return SHINDO_COLOR_OTHER;
  }

  function radiusForPayout(payoutYen) {
    return 10 + Math.sqrt(Math.max(0, payoutYen || 0)) / 150;
  }

  function renderLegend() {
    const entries = [
      [SHINDO_COLOR_7, "7"],
      [SHINDO_COLOR_6, "6弱・6強"],
      [SHINDO_COLOR_5, "5弱・5強"],
      [SHINDO_COLOR_OTHER, "4以下・不明"],
    ];
    const legend = document.getElementById("legend");
    const title = document.createElement("strong");
    title.textContent = "凡例";
    const size = document.createElement("div");
    size.textContent = "円の大きさ: 補償額（大きいほど高額）";
    const colors = document.createElement("div");
    colors.append("円の色（震度）: ");
    entries.forEach(([color, label], index) => {
      const swatch = document.createElement("span");
      swatch.className = "legend-swatch";
      swatch.style.color = color;
      swatch.textContent = "■";
      colors.append(swatch, label);
      if (index < entries.length - 1) colors.append(" ");
    });
    legend.replaceChildren(title, size, colors);
  }

  function normalizeMessage(message) {
    return message.trim().replace(/\s+/g, " ");
  }

  function appendUserMessage(text) {
    const element = document.createElement("div");
    element.className = "msg msg-user";
    element.textContent = text;
    messages.append(element);
    scrollMessages();
  }

  function appendAssistantText(text) {
    const element = document.createElement("div");
    element.className = "msg msg-assistant";
    element.textContent = text;
    messages.append(element);
    scrollMessages();
  }

  function appendAssistantHtml(html) {
    const element = document.createElement("div");
    element.className = "msg msg-assistant";
    // 固定回答はビルド時に生成した信頼済みHTMLだけを使用する。
    element.innerHTML = html;
    messages.append(element);
    renderMath(element);
    scrollMessages();
  }

  function renderMath(root) {
    if (!window.renderMathInElement) return;
    renderMathInElement(root, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "\\[", right: "\\]", display: true },
        { left: "$", right: "$", display: false },
        { left: "\\(", right: "\\)", display: false },
      ],
      throwOnError: false,
    });
    fitDisplayMath(root);
  }

  function fitDisplayMath(root) {
    root.querySelectorAll(".katex-display").forEach((display) => {
      const formula = display.querySelector(":scope > .katex");
      if (!formula) return;
      formula.style.fontSize = "";
      if (formula.scrollWidth <= display.clientWidth) return;
      const fittedSize = Math.max(
        0.72,
        0.95 * display.clientWidth / formula.scrollWidth * 0.98,
      );
      formula.style.fontSize = `${fittedSize}em`;
    });
  }

  function scrollMessages() {
    requestAnimationFrame(() => {
      messages.scrollTop = messages.scrollHeight;
    });
  }

  function wait(milliseconds) {
    return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
  }

  function setBusy(busy) {
    processing = busy;
    messageInput.disabled = busy;
    sendButton.disabled = busy;
    formStatus.classList.toggle("visible", busy);
    quickReplySlot.querySelectorAll("button").forEach((button) => {
      button.disabled = busy;
    });
  }

  function createProgressCard(scenario) {
    const card = document.createElement("div");
    card.className = "msg msg-assistant progress-card";
    const title = document.createElement("p");
    title.className = "progress-title";
    title.textContent = "補償額を算定しています";
    const list = document.createElement("ol");
    list.className = "progress-list";
    const definitions = [
      ["住所確認", scenario.address],
      ["震度照合", `震度${scenario.intensity.shindo_class}`],
      ["被害分析", scenario.damage_summary],
      ["補償額算定", `${scenario.payout.payout_yen.toLocaleString("ja-JP")}円`],
    ];
    const steps = definitions.map(([label, result]) => {
      const item = document.createElement("li");
      item.className = "progress-step";
      const labelElement = document.createElement("span");
      labelElement.className = "progress-label";
      labelElement.textContent = label;
      const resultElement = document.createElement("span");
      resultElement.className = "progress-result";
      item.append(labelElement, resultElement);
      list.append(item);
      return { item, resultElement, result };
    });
    card.append(title, list);
    messages.append(card);
    scrollMessages();
    return steps;
  }

  async function runProgress(scenario) {
    const steps = createProgressCard(scenario);
    for (const step of steps) {
      step.item.classList.add("active");
      await wait(demoData.progress_delay_ms);
      step.item.classList.remove("active");
      step.item.classList.add("done");
      step.resultElement.textContent = step.result;
      scrollMessages();
    }
  }

  function addScenarioMarker(scenario) {
    const existing = markerByScenarioKey.get(scenario.key);
    if (existing) markerLayer.removeLayer(existing);

    const color = colorForShindo(scenario.intensity.shindo_class);
    const marker = L.circleMarker(
      [scenario.query.lat, scenario.query.lon],
      {
        radius: radiusForPayout(scenario.payout.payout_yen),
        color,
        fillColor: color,
        fillOpacity: 0.65,
        weight: 2,
      },
    );
    const popup = document.createElement("div");
    const address = document.createElement("strong");
    address.textContent = scenario.address;
    const result = document.createElement("div");
    result.textContent =
      `補償額 ${scenario.payout.payout_yen_formatted}（震度${scenario.intensity.shindo_class}）`;
    popup.append(address, result);
    marker.bindPopup(popup).addTo(markerLayer);
    markerByScenarioKey.set(scenario.key, marker);
    map.panTo([scenario.query.lat, scenario.query.lon]);
    marker.openPopup();
  }

  function scenarioForMessage(message) {
    const normalized = normalizeMessage(message);
    return demoData.scenarios.find((scenario) => {
      const payoutPrompt = normalizeMessage(scenario.turns.payout.prompt);
      const address = normalizeMessage(scenario.address);
      return normalized === payoutPrompt || normalized === address || normalized.includes(address);
    });
  }

  function followUpKindForMessage(message) {
    if (!currentScenario) return null;
    const normalized = normalizeMessage(message);
    return ["reason", "math", "photo"].find(
      (kind) => normalizeMessage(currentScenario.turns[kind].prompt) === normalized,
    ) || null;
  }

  async function handleScenario(scenario, message) {
    appendUserMessage(message);
    setBusy(true);
    await runProgress(scenario);
    currentScenario = scenario;
    selectedScenarioKeys.add(scenario.key);
    askedFollowUps.set(scenario.key, new Set());
    appendAssistantHtml(scenario.turns.payout.answer_html);
    addScenarioMarker(scenario);
    setBusy(false);
    renderQuickReplies();
    messageInput.focus();
  }

  async function handleFollowUp(kind, message) {
    appendUserMessage(message);
    setBusy(true);
    const delay = kind === "reason" || kind === "math"
      ? REASONING_DELAY_MS
      : Math.min(700, demoData.progress_delay_ms);
    await wait(delay);
    appendAssistantHtml(currentScenario.turns[kind].answer_html);
    askedFollowUps.get(currentScenario.key).add(kind);
    setBusy(false);
    renderQuickReplies();
    messageInput.focus();
  }

  async function handleUnsupported(message) {
    appendUserMessage(message);
    setBusy(true);
    await wait(300);
    appendAssistantText(demoData.unsupported_message);
    setBusy(false);
    renderQuickReplies();
    messageInput.focus();
  }

  async function handleMessage(rawMessage) {
    if (processing) return;
    const message = rawMessage.trim();
    if (!message) return;
    const scenario = scenarioForMessage(message);
    if (scenario) {
      await handleScenario(scenario, message);
      return;
    }
    const followUpKind = followUpKindForMessage(message);
    if (followUpKind) {
      await handleFollowUp(followUpKind, message);
      return;
    }
    await handleUnsupported(message);
  }

  function quickReplies() {
    const remaining = demoData.scenarios
      .filter((scenario) => !selectedScenarioKeys.has(scenario.key))
      .map((scenario) => ({
        label: scenario.label,
        message: scenario.turns.payout.prompt,
      }));
    if (!currentScenario) return remaining;

    const asked = askedFollowUps.get(currentScenario.key) || new Set();
    if (asked.has("photo")) return remaining;
    if (asked.has("math")) {
      return [
        ...remaining,
        {
          label: currentScenario.turns.photo.prompt,
          message: currentScenario.turns.photo.prompt,
        },
      ];
    }
    if (asked.has("reason")) {
      return ["math", "photo"].map((kind) => ({
        label: currentScenario.turns[kind].prompt,
        message: currentScenario.turns[kind].prompt,
      }));
    }
    return [
      {
        label: currentScenario.turns.reason.prompt,
        message: currentScenario.turns.reason.prompt,
      },
      ...remaining,
    ];
  }

  function renderQuickReplies() {
    const buttons = quickReplies().map((reply) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "preset-btn";
      button.textContent = reply.label;
      button.disabled = processing;
      button.addEventListener("click", () => {
        messageInput.value = reply.message;
        messageInput.focus();
      });
      return button;
    });
    quickReplySlot.replaceChildren(...buttons);
  }

  chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = messageInput.value;
    await handleMessage(message);
    messageInput.value = "";
  });
  window.addEventListener("resize", () => {
    map.invalidateSize();
    fitDisplayMath(document);
  });

  renderLegend();
  renderQuickReplies();
  window.setTimeout(() => map.invalidateSize(), 0);
})();
