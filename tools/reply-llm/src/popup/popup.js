import { streamText, ApiError } from "../lib/api.js";
import { loadSettings, activeApi } from "../lib/settings.js";
import { loadContext, withDraft } from "../lib/mail.js";
import { POLICIES, buildSystem, buildUser, formatDate } from "../lib/prompts.js";

const $ = (id) => document.getElementById(id);
const el = Object.fromEntries(
  ["model", "openOptions", "srcFrom", "srcSubject", "srcDate", "srcSamples",
   "policy", "memo", "generate", "stop", "status", "draft", "insert", "copy"]
    .map((id) => [id, $(id)])
);

for (const p of POLICIES) el.policy.add(new Option(p.label, p.value));

el.openOptions.addEventListener("click", (e) => {
  e.preventDefault();
  browser.runtime.openOptionsPage();
});

const settings = await loadSettings();
const api = activeApi(settings);
el.model.textContent = `${api.label} / ${api.model}`;

// The popup belongs to the compose window it was opened from.
const [tab] = await browser.tabs.query({ active: true, currentWindow: true });

// The popup closes whenever it loses focus, so the policy, memo and draft are
// kept per compose tab and restored on reopen.
const store = browser.storage.session || browser.storage.local;
const stateKey = `compose-${tab.id}`;
const state = Object.assign(
  { policy: "", memo: "", draft: "", inserted: "" },
  (await store.get(stateKey))[stateKey]
);
el.policy.value = state.policy;
el.memo.value = state.memo;
el.draft.value = state.draft;

function saveState(patch = {}) {
  Object.assign(state, patch, {
    policy: el.policy.value,
    memo: el.memo.value,
    draft: el.draft.value,
  });
  return store.set({ [stateKey]: state });
}
el.policy.addEventListener("change", () => saveState());
el.memo.addEventListener("input", () => saveState());
el.draft.addEventListener("input", () => {
  saveState();
  updateButtons();
});

let ctx = null;
let controller = null;

function say(message, isError = false) {
  el.status.textContent = message;
  el.status.className = isError ? "error" : "muted";
}

function updateButtons() {
  const busy = !!controller;
  el.generate.disabled = busy || !ctx;
  el.generate.hidden = busy;
  el.stop.hidden = !busy;
  el.insert.disabled = busy || !el.draft.value.trim();
  el.copy.disabled = !el.draft.value.trim();
}

// ---------------------------------------------------------------------------
// Load the message being replied to

try {
  ctx = await loadContext(tab.id, Number(settings.samples) || 0);
  const o = ctx.original;
  el.srcFrom.textContent = o.author || "(返信元なし。本文の引用部分を使います)";
  el.srcSubject.textContent = o.subject;
  el.srcDate.textContent = formatDate(o.date);
  el.srcSamples.textContent = ctx.samples.length
    ? `${ctx.samples.length}通 (${ctx.sampleSource === "recipient" ? "同じ相手に送ったメール" : "最近送ったメール"})`
    : "なし";
  say(api.apiKey ? "" : "設定で API キーを入れてください。", !api.apiKey);
} catch (e) {
  el.srcFrom.textContent = "読み込めませんでした";
  say(String((e && e.message) || e), true);
}
updateButtons();

// ---------------------------------------------------------------------------
// Generate

el.generate.addEventListener("click", generate);
for (const input of [el.memo, el.draft]) {
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.ctrlKey && !el.generate.disabled) {
      e.preventDefault();
      generate();
    }
  });
}
el.stop.addEventListener("click", () => controller && controller.abort());

async function generate() {
  if (!api.apiKey) return say("設定で API キーを入れてください。", true);

  controller = new AbortController();
  el.draft.value = "";
  updateButtons();
  say("書いています…");

  let text = "";
  try {
    const stream = streamText({
      provider: api.provider,
      apiKey: api.apiKey,
      model: api.model,
      effort: api.effort,
      system: buildSystem(settings.extraReply),
      user: buildUser(ctx, el.policy.value, el.memo.value),
      signal: controller.signal,
    });
    let result;
    while (!(result = await stream.next()).done) {
      text += result.value;
      el.draft.value = text;
      el.draft.scrollTop = el.draft.scrollHeight;
    }
    el.draft.value = text.trim();
    const stop = result.value && result.value.stopReason;
    if (stop === "max_tokens") say("途中で打ち切られました。", true);
    else if (stop === "refusal") say("モデルが応答を拒否しました。", true);
    else say("書けました。直してから挿入できます。");
  } catch (e) {
    if (e && e.name === "AbortError") say("止めました。");
    else say(e instanceof ApiError ? e.message : String((e && e.message) || e), true);
  } finally {
    controller = null;
    await saveState();
    updateButtons();
  }
}

// ---------------------------------------------------------------------------
// Insert / copy

el.insert.addEventListener("click", async () => {
  const draft = el.draft.value.trim();
  try {
    // Read the body again: it may have been edited since the popup opened.
    const details = await browser.compose.getComposeDetails(tab.id);
    await browser.compose.setComposeDetails(tab.id, withDraft(details, draft, state.inserted));
    await saveState({ inserted: draft });
    say("本文に挿入しました。");
  } catch (e) {
    say(String((e && e.message) || e), true);
  }
});

el.copy.addEventListener("click", async () => {
  await navigator.clipboard.writeText(el.draft.value.trim());
  say("コピーしました。");
});
