import { streamText, ApiError, providerOf } from "../lib/api.js";
import { FIELDS, loadSettings } from "../lib/settings.js";

const el = Object.fromEntries(
  [...FIELDS, "save", "test", "status", "block-openai", "block-claude"]
    .map((id) => [id, document.getElementById(id)])
);

const stored = await loadSettings();
for (const f of FIELDS) el[f].value = stored[f];
showBlocks();

function showBlocks() {
  el["block-openai"].hidden = el.provider.value !== "openai";
  el["block-claude"].hidden = el.provider.value !== "claude";
}

el.provider.addEventListener("change", showBlocks);

for (const button of document.querySelectorAll("[data-reveal]")) {
  button.addEventListener("click", () => {
    const input = el[button.dataset.reveal];
    const shown = input.type === "text";
    input.type = shown ? "password" : "text";
    button.textContent = shown ? "表示" : "隠す";
  });
}

el.save.addEventListener("click", async () => {
  await browser.storage.local.set(
    Object.fromEntries(FIELDS.map((f) => [f, el[f].value.trim()]))
  );
  say("保存しました。");
});

el.test.addEventListener("click", async () => {
  const provider = el.provider.value;
  const p = providerOf(provider);
  const apiKey = (provider === "claude" ? el.claudeKey : el.openaiKey).value.trim();
  const model = (provider === "claude" ? el.claudeModel : el.openaiModel).value.trim() || p.defaultModel;

  if (!apiKey) return say("APIキーを入力してください。", true);

  say(`${p.label} / ${model} に接続中…`);
  try {
    let out = "";
    for await (const chunk of streamText({
      provider,
      apiKey,
      model,
      system: "ひとことだけ答える。",
      user: "ping",
      effort: "low",
    })) {
      out += chunk;
    }
    say(`接続できました (${model})。応答: ${out.trim().slice(0, 40)}`);
  } catch (e) {
    say(e instanceof ApiError ? e.message : String((e && e.message) || e), true);
  }
});

function say(message, isError = false) {
  el.status.textContent = message;
  el.status.style.color = isError ? "#7a2e2e" : "";
}
