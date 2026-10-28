// Minimal streaming client for Claude and OpenAI.
//
// This is raw HTTP on purpose: an unpacked MV3 extension has no bundler, and
// MV3's CSP forbids loading a vendor SDK from a CDN.
//
// Both providers stream server-sent events whose data lines are single-line
// JSON carrying a "type" field, so one parser covers both. The per-provider
// differences are confined to the PROVIDERS table below.

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// stopReason is normalised to: "end_turn" | "max_tokens" | "refusal" | null
export const PROVIDERS = {
  openai: {
    label: "OpenAI",
    endpoint: "https://api.openai.com/v1/responses",
    defaultModel: "gpt-5.6-terra",
    keyHint: "sk-...",
    keysUrl: "https://platform.openai.com/api-keys",

    headers: (apiKey) => ({
      "content-type": "application/json",
      authorization: `Bearer ${apiKey}`,
    }),

    body: ({ model, system, user, effort, schema }) => ({
      model,
      instructions: system,
      input: user,
      stream: true,
      reasoning: { effort },
      // Reasoning tokens count against this cap, so it is set well above the
      // length of any translation we expect back.
      max_output_tokens: 32000,
      ...(schema && {
        text: {
          format: { type: "json_schema", name: schema.name, schema: schema.schema, strict: true },
        },
      }),
    }),

    delta: (ev) => (ev.type === "response.output_text.delta" ? ev.delta : null),

    terminal(ev) {
      if (ev.type === "response.completed") return "end_turn";
      if (ev.type === "response.incomplete") {
        const reason = ev.response && ev.response.incomplete_details && ev.response.incomplete_details.reason;
        return reason === "content_filter" ? "refusal" : "max_tokens";
      }
      return null;
    },

    failure(ev) {
      if (ev.type === "error") return ev.message || (ev.error && ev.error.message) || "不明なエラー";
      if (ev.type === "response.failed") {
        const err = ev.response && ev.response.error;
        return (err && err.message) || "生成に失敗しました。";
      }
      return null;
    },
  },

  claude: {
    label: "Claude",
    endpoint: "https://api.anthropic.com/v1/messages",
    defaultModel: "claude-opus-5",
    keyHint: "sk-ant-...",
    keysUrl: "https://console.anthropic.com/settings/keys",

    headers: (apiKey) => ({
      "content-type": "application/json",
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
      // Lets the API retry on another model inside the same call when this one
      // declines, instead of returning nothing.
      "anthropic-beta": "server-side-fallback-2026-07-01",
      // Required for requests that carry a browser Origin header.
      "anthropic-dangerous-direct-browser-access": "true",
    }),

    body: ({ model, system, user, effort, schema }) => ({
      model,
      max_tokens: 16000,
      stream: true,
      system,
      messages: [{ role: "user", content: user }],
      output_config: schema
        ? { effort, format: { type: "json_schema", schema: schema.schema } }
        : { effort },
      fallbacks: "default",
    }),

    // Thinking blocks arrive as thinking_delta; only text_delta is output.
    delta: (ev) =>
      ev.type === "content_block_delta" && ev.delta && ev.delta.type === "text_delta"
        ? ev.delta.text
        : null,

    terminal: (ev) =>
      ev.type === "message_delta" && ev.delta && ev.delta.stop_reason
        ? ev.delta.stop_reason
        : null,

    failure: (ev) =>
      ev.type === "error" ? (ev.error && ev.error.message) || "不明なエラー" : null,
  },
};

export function providerOf(name) {
  return PROVIDERS[name] || PROVIDERS.openai;
}

/**
 * Stream one completion. Yields text fragments as they arrive and returns the
 * normalised stop reason.
 *
 * @param {object} opts
 * @param {"openai"|"claude"} opts.provider
 * @param {string} opts.apiKey
 * @param {string} [opts.model]
 * @param {string} opts.system
 * @param {string} opts.user
 * @param {"low"|"medium"|"high"} [opts.effort]
 * @param {{name: string, schema: object}} [opts.schema] constrain the output to this JSON schema
 * @param {AbortSignal} [opts.signal]
 * @returns {AsyncGenerator<string, {stopReason: string|null}, void>}
 */
export async function* streamText({ provider, apiKey, model, system, user, effort = "medium", schema, signal }) {
  const p = providerOf(provider);

  let res;
  try {
    res = await fetch(p.endpoint, {
      method: "POST",
      signal,
      headers: p.headers(apiKey),
      body: JSON.stringify(p.body({ model: model || p.defaultModel, system, user, effort, schema })),
    });
  } catch (e) {
    if (e && e.name === "AbortError") throw e;
    throw new ApiError(`${p.label} に接続できません。ネットワークを確認してください。`, 0);
  }

  if (!res.ok) throw new ApiError(await describeError(res, p), res.status);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let stopReason = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep;
    while ((sep = buffer.indexOf("\n\n")) >= 0) {
      const rawEvent = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);

      for (const line of rawEvent.split("\n")) {
        if (!line.startsWith("data:")) continue;
        const payload = line.slice(5).trim();
        if (!payload || payload === "[DONE]") continue;

        let ev;
        try {
          ev = JSON.parse(payload);
        } catch {
          continue;
        }

        const failure = p.failure(ev);
        if (failure) throw new ApiError(failure, res.status);

        const text = p.delta(ev);
        if (text) yield text;

        const stop = p.terminal(ev);
        if (stop) stopReason = stop;
      }
    }
  }

  return { stopReason };
}

async function describeError(res, p) {
  let detail = "";
  try {
    const data = await res.json();
    detail = (data && data.error && data.error.message) || "";
  } catch {
    // non-JSON body
  }

  switch (res.status) {
    case 401:
      return `${p.label} の APIキーが無効です。設定を確認してください。`;
    case 403:
      return `このAPIキーではこのモデルを使えません。${detail ? " " + detail : ""}`;
    case 404:
      return `モデル名が見つかりません。設定のモデル欄を確認してください。${detail ? " " + detail : ""}`;
    case 429:
      return "レート制限に達しました。少し待って再実行してください。";
    case 500:
    case 502:
    case 503:
    case 529:
      return `${p.label} 側が混雑しています。少し待って再実行してください。`;
    default:
      return detail || `APIエラー (HTTP ${res.status})`;
  }
}
