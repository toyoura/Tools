// Settings shared by the popup and the options page. Field names follow
// Kotoba so the two extensions read the same way, but Thunderbird keeps its
// own storage: the API key has to be entered once here as well.

import { providerOf } from "./api.js";

export const FIELDS = [
  "provider", "openaiKey", "openaiModel", "claudeKey", "claudeModel",
  "effort", "samples", "extraReply",
];

export function defaultFor(field) {
  if (field === "provider") return "openai";
  if (field === "effort") return "medium";
  if (field === "samples") return "3";
  return "";
}

export async function loadSettings() {
  const stored = await browser.storage.local.get(
    Object.fromEntries(FIELDS.map((f) => [f, ""]))
  );
  for (const f of FIELDS) if (!stored[f]) stored[f] = defaultFor(f);
  return stored;
}

// The key and model for whichever provider is selected.
export function activeApi(settings) {
  const provider = settings.provider;
  const p = providerOf(provider);
  const claude = provider === "claude";
  return {
    provider,
    label: p.label,
    apiKey: claude ? settings.claudeKey : settings.openaiKey,
    model: (claude ? settings.claudeModel : settings.openaiModel) || p.defaultModel,
    effort: settings.effort,
  };
}
