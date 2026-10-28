// Fake Thunderbird API and a fake OpenAI stream for test/mock.html.
// All names and addresses below are fictional.

const ORIGINAL = {
  id: 101,
  author: "Hanako Yamada <yamada@example.ac.jp>",
  recipients: ["Taro Suzuki <suzuki@example.ac.jp>", "佐藤一郎 <sato@example.ac.jp>"],
  ccList: [],
  date: new Date("2026-10-08T10:43:59+09:00"),
  subject: "お願い：卒業研究発表会の審査員",
  text: `鈴木先生，佐藤先生

山田です．お世話になっています．

2月12日(木)の卒業研究発表会で，午後の部の審査員を
お願いできますでしょうか．

以上，よろしくお願いします．

山田 花子

--
Hanako Yamada <yamada@example.ac.jp>`,
};

const SENT = [
  {
    id: 201,
    recipients: ["Hanako Yamada <yamada@example.ac.jp>"],
    date: new Date("2026-08-30T13:45:47+09:00"),
    subject: "Re: お願い：学科紹介パンフレットの原稿",
    text: `山田先生、


鈴木です。

ご依頼いただいていた原稿を、添付してお送りします。

内容のご確認のほど、何卒よろしくお願いいたします。

--
鈴木 太郎

On 2026/08/28 9:00, Hanako Yamada wrote:
> 鈴木先生
> 原稿をお願いします．`,
  },
];

const COMPOSE_HTML = `<!DOCTYPE html><html><head><meta http-equiv="content-type" content="text/html; charset=UTF-8"></head><body><p><br></p><div class="moz-cite-prefix">On 2026/10/08 10:43, Hanako Yamada wrote:<br></div><blockquote type="cite" cite="mid:abc@example.ac.jp"><pre class="moz-quote-pre" wrap="">${ORIGINAL.text}</pre></blockquote><br><pre class="moz-signature" cols="72">--
鈴木 太郎</pre></body></html>`;

const COMPOSE_PLAIN = `

On 2026/10/08 10:43, Hanako Yamada wrote:
> 鈴木先生，佐藤先生
> 山田です．

--
鈴木 太郎`;

const REPLY = `山田先生、

鈴木です。

2月12日(木)の卒業研究発表会、午後の部の審査員の件、承知しました。
お引き受けいたします。

どうぞよろしくお願いいたします。

鈴木`;

export function installMocks({ plain, onSet, onPrompt }) {
  const compose = {
    identityId: "id1",
    type: "reply",
    relatedMessageId: ORIGINAL.id,
    to: ["Hanako Yamada <yamada@example.ac.jp>"],
    cc: [],
    subject: "Re: お願い：卒業研究発表会の審査員",
    isPlainText: plain,
    body: COMPOSE_HTML,
    plainTextBody: COMPOSE_PLAIN,
  };
  const all = [ORIGINAL, ...SENT];
  const session = {};

  window.browser = {
    tabs: { query: async () => [{ id: 7 }] },
    runtime: { openOptionsPage: () => alert("openOptionsPage") },
    storage: {
      local: { get: async (d) => ({ ...d }), set: async () => {} },
      session: {
        get: async (k) => ({ [k]: session[k] }),
        set: async (o) => Object.assign(session, structuredClone(o)),
      },
    },
    compose: {
      getComposeDetails: async () => ({ ...compose }),
      setComposeDetails: async (_tab, d) => {
        Object.assign(compose, d);
        onSet(d);
      },
    },
    identities: { get: async () => ({ accountId: "acc1", name: "Taro Suzuki", email: "suzuki@example.ac.jp" }) },
    folders: { query: async () => [{ id: "acc1://Sent" }] },
    messages: {
      get: async (id) => all.find((m) => m.id === id),
      listInlineTextParts: async (id) => [{ contentType: "text/plain", content: all.find((m) => m.id === id).text }],
      query: async (q) => ({
        id: null,
        messages: SENT.filter((m) => !q.recipients || m.recipients.join(",").includes(q.recipients)),
      }),
      continueList: async () => ({ id: null, messages: [] }),
    },
    messengerUtilities: { convertToPlainText: async (h) => h.replace(/<[^>]+>/g, "") },
  };

  // Settings come back empty from the fake storage; give the popup a key.
  const realGet = window.browser.storage.local.get;
  window.browser.storage.local.get = async (d) => ({ ...(await realGet(d)), openaiKey: "sk-test" });

  window.fetch = ((realFetch) => async (url, init) => {
    if (!String(url).startsWith("https://api.")) return realFetch(url, init);
    onPrompt(JSON.parse(init.body).input);
    const enc = new TextEncoder();
    const chunks = REPLY.match(/[\s\S]{1,6}/g);
    const stream = new ReadableStream({
      async start(c) {
        for (const delta of chunks) {
          c.enqueue(enc.encode(`data: ${JSON.stringify({ type: "response.output_text.delta", delta })}\n\n`));
          await new Promise((r) => setTimeout(r, 15));
        }
        c.enqueue(enc.encode(`data: ${JSON.stringify({ type: "response.completed" })}\n\n`));
        c.close();
      },
    });
    return new Response(stream, { status: 200 });
  })(window.fetch);
}
