// Everything that talks to Thunderbird: reading the message being replied to,
// finding past sent mail to imitate, and putting the draft into the body.

const ORIGINAL_LIMIT = 12000;
const SAMPLE_LIMIT = 1500;
const DAY = 24 * 60 * 60 * 1000;

/**
 * Collect what the prompt needs for one compose tab.
 * @returns {Promise<{details, identity, original, samples, sampleSource}>}
 */
export async function loadContext(tabId, maxSamples) {
  const details = await browser.compose.getComposeDetails(tabId);

  let identity = null;
  if (details.identityId) {
    try {
      identity = await browser.identities.get(details.identityId);
    } catch {
      // identity lookup is only used for the writer's name
    }
  }

  // relatedMessageId is set for replies and forwards. A reopened draft has
  // none, and then the quoted text in the body is all we have.
  let original = null;
  if (details.relatedMessageId) {
    const h = await browser.messages.get(details.relatedMessageId);
    original = {
      author: h.author,
      to: h.recipients || [],
      cc: h.ccList || [],
      date: h.date,
      subject: h.subject,
      body: clip(await messageText(h.id), ORIGINAL_LIMIT),
    };
  } else {
    original = {
      author: "", to: [], cc: [], date: null,
      subject: details.subject || "",
      body: clip(
        details.isPlainText ? details.plainTextBody || "" : await toPlain(details.body || ""),
        ORIGINAL_LIMIT
      ),
    };
  }

  const recipients = addressesOf(details.to);
  const { samples, source } = await findSamples(identity, recipients, maxSamples);

  return { details, identity, original, samples, sampleSource: source };
}

/** Plain text of a stored message, preferring the text/plain part. */
export async function messageText(messageId) {
  const parts = await browser.messages.listInlineTextParts(messageId);
  const plain = parts.filter((p) => p.contentType === "text/plain");
  if (plain.length) return plain.map((p) => p.content).join("\n\n");
  const html = parts.filter((p) => p.contentType === "text/html");
  if (html.length) return toPlain(html.map((p) => p.content).join("\n"));
  return "";
}

async function toPlain(html) {
  return browser.messengerUtilities.convertToPlainText(html);
}

// "Hanako Yamada <yamada@example.jp>" -> "yamada@example.jp". Contact and mailing-list
// entries (objects) are skipped.
export function addressesOf(list) {
  return (list || [])
    .filter((r) => typeof r === "string")
    .map((r) => {
      const m = r.match(/<([^>]+)>/);
      return (m ? m[1] : r).trim().toLowerCase();
    })
    .filter((a) => a.includes("@"));
}

// ---------------------------------------------------------------------------
// Style samples from the Sent folder

async function findSamples(identity, recipients, maxSamples) {
  if (maxSamples <= 0) return { samples: [], source: "none" };

  const folderIds = await sentFolderIds(identity && identity.accountId);
  if (!folderIds.length) return { samples: [], source: "none" };

  // Mail I sent to the same person in the last year, newest first.
  let headers = [];
  let source = "recipient";
  const yearAgo = new Date(Date.now() - 365 * DAY);
  for (const addr of recipients.slice(0, 3)) {
    for (const folderId of folderIds) {
      headers.push(...(await queryAll({ folderId, recipients: addr, fromDate: yearAgo })));
    }
    if (headers.length >= maxSamples) break;
  }

  // Nobody I have written to before: fall back to my most recent mail.
  if (!headers.length) {
    source = "recent";
    const twoWeeksAgo = new Date(Date.now() - 14 * DAY);
    for (const folderId of folderIds) {
      headers.push(...(await queryAll({ folderId, fromDate: twoWeeksAgo })));
    }
  }

  const seen = new Set();
  headers = headers
    .filter((h) => !seen.has(h.id) && seen.add(h.id))
    .sort((a, b) => new Date(b.date) - new Date(a.date));

  const samples = [];
  for (const h of headers) {
    if (samples.length >= maxSamples) break;
    const body = clip(cleanSample(await messageText(h.id)), SAMPLE_LIMIT);
    if (body) samples.push({ date: h.date, subject: h.subject, to: h.recipients || [], body });
  }
  return { samples, source: samples.length ? source : "none" };
}

async function sentFolderIds(accountId) {
  try {
    const folders = await browser.folders.query({
      specialUse: ["sent"],
      ...(accountId && { accountId }),
    });
    if (folders.length) return folders.map((f) => f.id);
  } catch {
    // fall through to walking the folder tree
  }

  const ids = [];
  const accounts = accountId
    ? [await browser.accounts.get(accountId, true)]
    : await browser.accounts.list(true);
  const walk = (folders) => {
    for (const f of folders || []) {
      if ((f.specialUse || []).includes("sent") || f.type === "sent") ids.push(f.id);
      walk(f.subFolders);
    }
  };
  for (const a of accounts) if (a) walk(a.rootFolder ? [a.rootFolder] : a.folders);
  return ids;
}

async function queryAll(queryInfo, limit = 400) {
  let page = await browser.messages.query(queryInfo);
  const out = [...page.messages];
  while (page.id && out.length < limit) {
    page = await browser.messages.continueList(page.id);
    out.push(...page.messages);
  }
  if (page.id && browser.messages.abortList) browser.messages.abortList(page.id);
  return out;
}

// Keep only what I wrote: drop the quoted original and the signature block.
const CUT_LINE = [
  /^\s*>/,
  /^-- ?$/,
  /wrote:\s*$/i,
  /(のメッセージ|書きました|書き込みました)[:：]?\s*$/,
  /^-{2,}\s*(Original Message|Forwarded message|元のメッセージ|転送)/i,
  /^(From|差出人|送信者)\s*[:：]/,
];

export function cleanSample(text) {
  const lines = (text || "").replace(/\r\n/g, "\n").split("\n");
  const cut = lines.findIndex((l) => CUT_LINE.some((re) => re.test(l)));
  return (cut >= 0 ? lines.slice(0, cut) : lines).join("\n").trim();
}

function clip(text, limit) {
  return text.length > limit ? text.slice(0, limit) + "\n…(以下省略)" : text;
}

// ---------------------------------------------------------------------------
// Putting the draft into the compose body

const DRAFT_CLASS = "reply-llm-draft";

/**
 * New compose details with the draft placed above the quote. Inserting again
 * replaces the previous draft instead of stacking a second one.
 *
 * @param {object} details current compose details
 * @param {string} draft plain text
 * @param {string} [previous] the plain-text draft inserted last time
 */
export function withDraft(details, draft, previous) {
  if (details.isPlainText) {
    return { plainTextBody: insertIntoPlain(details.plainTextBody || "", draft, previous) };
  }
  return { body: insertIntoHtml(details.body || "", draft) };
}

export function insertIntoPlain(text, draft, previous) {
  let rest = text.replace(/\r\n/g, "\n");
  if (previous && rest.includes(previous)) rest = rest.replace(previous, "");
  rest = rest.replace(/^(?:[ \t]*\n)+/, "");
  return rest ? `${draft}\n\n${rest}` : `${draft}\n`;
}

export function insertIntoHtml(html, draft) {
  const doc = new DOMParser().parseFromString(html, "text/html");
  const body = doc.body;

  for (const old of body.querySelectorAll(`div.${DRAFT_CLASS}`)) old.remove();

  const div = doc.createElement("div");
  div.className = DRAFT_CLASS;
  draft.split("\n").forEach((line, i) => {
    if (i) div.append(doc.createElement("br"));
    div.append(line);
  });

  // The reply goes above whichever comes first: signature, attribution line
  // or the quote itself.
  let target = body.querySelector(".moz-signature, .moz-cite-prefix, blockquote[type='cite']");
  while (target && target.parentNode !== body) target = target.parentNode;

  // Thunderbird opens a reply with empty lines at the top for the cursor.
  while (body.firstChild && body.firstChild !== target && isBlank(body.firstChild)) {
    body.firstChild.remove();
  }

  body.insertBefore(div, target);
  if (target) body.insertBefore(doc.createElement("br"), target);

  return "<!DOCTYPE html>\n" + doc.documentElement.outerHTML;
}

function isBlank(node) {
  if (node.nodeType === Node.TEXT_NODE) return !node.textContent.trim();
  if (node.nodeType !== Node.ELEMENT_NODE) return true;
  if (node.tagName === "BR") return true;
  return ["P", "DIV"].includes(node.tagName) && !node.textContent.trim() && !node.querySelector("img");
}
