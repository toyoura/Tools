import * as vscode from "vscode";
import { ChildProcess, spawn } from "child_process";
import * as path from "path";
import { Chunk, pickChunkForLine } from "./pick";

let server: ChildProcess | undefined; // only set when *we* started it
let log: vscode.OutputChannel;
let extRoot = ""; // set in activate(); server.py is bundled under py/

// .tex and .txt go through the same parser: it already strips LaTeX, and a
// plain text file just becomes paragraphs.
const READABLE = new Set(["markdown", "latex", "plaintext", "tex"]);

function cfg() {
  const c = vscode.workspace.getConfiguration("mdreader");
  const fallback = path.join(extRoot, "py", "server.py");
  return {
    python: c.get<string>("pythonPath", "python"),
    serverPath: c.get<string>("serverPath", "") || fallback,
    port: c.get<number>("port", 8765),
    voice: c.get<string>("voice", "auto"),
    voiceJa: c.get<string>("voiceJa", "ja-JP-NanamiNeural"),
    voiceEn: c.get<string>("voiceEn", "en-US-AriaNeural"),
    voiceLocales: c.get<string>("voiceLocales", "ja-JP,en-US,en-GB"),
    speed: c.get<number>("speed", 1.4),
    moveCursor: c.get<boolean>("moveCursor", true),
  };
}

const base = () => `http://127.0.0.1:${cfg().port}`;

async function isUp(): Promise<boolean> {
  try {
    const r = await fetch(base() + "/api/pending", {
      signal: AbortSignal.timeout(800),
    });
    return r.ok;
  } catch {
    return false;
  }
}

async function ensureServer(): Promise<boolean> {
  if (await isUp()) {
    return true;
  }
  const { python, serverPath, port } = cfg();
  log.appendLine(`起動: ${python} ${serverPath} --port ${port}`);
  try {
    server = spawn(python, [serverPath, "--port", String(port), "--no-browser"], {
      cwd: path.dirname(serverPath),
      windowsHide: true,
    });
  } catch (e) {
    vscode.window.showErrorMessage(`MdReader: Python を起動できません (${e})`);
    return false;
  }
  server.stdout?.on("data", (d) => log.append(String(d)));
  server.stderr?.on("data", (d) => log.append(String(d)));
  server.on("exit", (code) => {
    log.appendLine(`サーバ終了 (code ${code})`);
    server = undefined;
  });

  const deadline = Date.now() + 25000;
  while (Date.now() < deadline) {
    if (await isUp()) {
      return true;
    }
    if (!server) {
      break; // died on startup
    }
    await new Promise((r) => setTimeout(r, 300));
  }
  vscode.window.showErrorMessage(
    "MdReader: 読み上げサーバが起動しませんでした。出力パネルの MdReader を確認してください。"
  );
  log.show(true);
  return false;
}

async function parseText(text: string): Promise<Chunk[]> {
  const r = await fetch(base() + "/api/parse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!r.ok) {
    throw new Error(await r.text());
  }
  const body = (await r.json()) as { chunks: Chunk[] };
  return body.chunks;
}

class Panel implements vscode.WebviewViewProvider {
  private view?: vscode.WebviewView;
  private ready = false;
  private chunks: Chunk[] = [];
  private cur = 0;
  private docUri?: vscode.Uri;
  private lastEdit = 0;
  private reparseTimer?: NodeJS.Timeout;
  private engineTimer?: NodeJS.Timeout;
  private voicesSent = false;

  constructor(private readonly ext: vscode.Uri) {}

  resolveWebviewView(view: vscode.WebviewView) {
    this.view = view;
    view.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.joinPath(this.ext, "media")],
    };
    view.webview.html = this.html(view.webview);
    view.webview.onDidReceiveMessage((m) => this.onMessage(m));
    view.onDidDispose(() => {
      this.view = undefined;
      this.ready = false;
      this.voicesSent = false;
      clearInterval(this.engineTimer);
      this.engineTimer = undefined;
    });
    this.engineTimer = setInterval(() => {
      void this.pollEngine();
      void this.sendVoices(); // no-op once the list has been delivered
    }, 5000);
    void this.syncActiveEditor();
  }

  private post(msg: unknown) {
    void this.view?.webview.postMessage(msg);
  }

  private html(w: vscode.Webview): string {
    const nonce = Math.random().toString(36).slice(2) + Date.now().toString(36);
    const js = w.asWebviewUri(vscode.Uri.joinPath(this.ext, "media", "panel.js"));
    const css = w.asWebviewUri(vscode.Uri.joinPath(this.ext, "media", "panel.css"));
    const origin = base();
    return `<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none';
  style-src ${w.cspSource}; script-src 'nonce-${nonce}';
  connect-src ${origin}; media-src ${origin};">
<link rel="stylesheet" href="${css}">
</head>
<body>
  <div class="bar">
    <button id="prev" title="前の文 (Ctrl+Alt+[)">◀</button>
    <button id="play" class="primary">▶ 再生</button>
    <button id="next" title="次の文 (Ctrl+Alt+])">▶</button>
  </div>
  <div class="bar">
    <select id="voice" title="話者。自動は文ごとに日本語と英語を切り替える">
      <option value="auto">自動 (日本語 / 英語)</option>
    </select>
    <select id="speed">
      <option value="0.8">0.8x</option><option value="1">1.0x</option>
      <option value="1.2">1.2x</option><option value="1.4">1.4x</option>
      <option value="1.6">1.6x</option><option value="1.8">1.8x</option>
      <option value="2">2.0x</option>
    </select>
  </div>
  <div id="pos"></div>
  <div id="now">Markdown を開いて再生してください</div>
  <div id="next-up"></div>
  <div id="engine"></div>
  <div id="err"></div>
  <script nonce="${nonce}">window.MDREADER_ORIGIN = ${JSON.stringify(origin)};</script>
  <script nonce="${nonce}" src="${js}"></script>
</body>
</html>`;
  }

  /** The webview cannot read JSON from the server (cross-origin), so the
   * voice list is fetched here and posted in. */
  private async sendVoices() {
    if (!this.view || this.voicesSent) {
      return;
    }
    // The panel becomes ready long before python is listening, so waiting here
    // is what keeps the menu from staying empty on a cold start.
    if (!(await ensureServer())) {
      return;
    }
    try {
      const r = await fetch(
        base() + "/api/voices?locales=" + encodeURIComponent(cfg().voiceLocales),
        { signal: AbortSignal.timeout(8000) }
      );
      if (r.ok) {
        this.post({ type: "voices", voices: await r.json() });
        this.voicesSent = true;
      }
    } catch {
      // not up yet; the engine poll retries until the list arrives
    }
  }

  /** Tell the panel when playback has dropped to the offline SAPI voice. */
  private async pollEngine() {
    if (!this.view) {
      return;
    }
    try {
      const r = await fetch(base() + "/api/engine", { signal: AbortSignal.timeout(1500) });
      if (r.ok) {
        this.post({ type: "engine", ...((await r.json()) as object) });
      }
    } catch {
      // server not up yet; nothing to report
    }
  }

  /* ---------- document tracking ---------- */

  async syncActiveEditor() {
    const ed = vscode.window.activeTextEditor;
    if (!ed || !READABLE.has(ed.document.languageId)) {
      return;
    }
    if (!(await ensureServer())) {
      return;
    }
    const same = this.docUri?.toString() === ed.document.uri.toString();
    this.docUri = ed.document.uri;
    try {
      const chunks = await parseText(ed.document.getText());
      this.setChunks(chunks, same);
      this.post({
        type: "doc",
        chunks: this.chunks,
        cur: this.cur,
        name: path.basename(ed.document.fileName),
        keep: same,
      });
      const c = cfg();
      this.post({
        type: "config",
        voice: c.voice,
        voiceJa: c.voiceJa,
        voiceEn: c.voiceEn,
        speed: c.speed,
      });
    } catch (e) {
      this.post({ type: "error", message: String(e) });
    }
  }

  /** Keep reading the same sentence across an edit, the way the browser build does. */
  private setChunks(next: Chunk[], keepPosition: boolean) {
    const before = this.chunks[this.cur];
    this.chunks = next;
    if (!keepPosition || !before) {
      this.cur = next.find((c) => c.say)?.i ?? 0;
      return;
    }
    const hit = next.find((c) => c.say && c.text === before.text);
    if (hit) {
      this.cur = hit.i;
      return;
    }
    let best: Chunk | undefined;
    for (const c of next) {
      if (c.say && c.line <= before.line) {
        best = c;
      }
    }
    this.cur = best?.i ?? next.find((c) => c.say)?.i ?? 0;
  }

  onDocEdited(e: vscode.TextDocumentChangeEvent) {
    if (e.document.uri.toString() !== this.docUri?.toString()) {
      return;
    }
    this.lastEdit = Date.now();
    clearTimeout(this.reparseTimer);
    this.reparseTimer = setTimeout(() => void this.syncActiveEditor(), 600);
  }

  /* ---------- webview -> extension ---------- */

  private onMessage(m: any) {
    switch (m.type) {
      case "ready":
        this.ready = true;
        void this.syncActiveEditor();
        void this.pollEngine();
        void this.sendVoices();
        break;
      case "chunk":
        this.cur = m.i;
        this.revealChunk(m.i);
        break;
      case "setting":
        void vscode.workspace
          .getConfiguration("mdreader")
          .update(m.key, m.value, vscode.ConfigurationTarget.Global);
        break;
      case "error":
        vscode.window.showWarningMessage(`MdReader: ${m.message}`);
        break;
    }
  }

  /** Put the editor caret on the sentence being read. */
  private revealChunk(i: number) {
    if (!cfg().moveCursor) {
      return;
    }
    // Do not yank the caret away while the user is typing a fix.
    if (Date.now() - this.lastEdit < 5000) {
      return;
    }
    const c = this.chunks[i];
    const ed = vscode.window.activeTextEditor;
    if (!c || !ed || ed.document.uri.toString() !== this.docUri?.toString()) {
      return;
    }
    const line = Math.min(Math.max(0, c.line - 1), ed.document.lineCount - 1);
    const pos = new vscode.Position(line, 0);
    ed.selection = new vscode.Selection(pos, pos);
    ed.revealRange(
      new vscode.Range(pos, pos),
      vscode.TextEditorRevealType.InCenterIfOutsideViewport
    );
  }

  /* ---------- commands ---------- */

  /**
   * The panel owns the audio element, so nothing can play until it exists and
   * has been handed a parsed document. A command fired before the sidebar was
   * ever opened has to wait for both.
   */
  private async ensureReady(): Promise<boolean> {
    if (!this.view) {
      await vscode.commands.executeCommand("mdreader.panel.focus");
      for (let i = 0; i < 50 && !this.ready; i++) {
        await new Promise((r) => setTimeout(r, 100));
      }
    }
    const uri = vscode.window.activeTextEditor?.document.uri.toString();
    if (!this.chunks.length || (uri && uri !== this.docUri?.toString())) {
      await this.syncActiveEditor();
    }
    return !!this.view && this.chunks.length > 0;
  }

  async playPause() {
    if (await this.ensureReady()) {
      this.post({ type: "cmd", cmd: "playPause" });
    }
  }
  next() {
    this.post({ type: "cmd", cmd: "next" });
  }
  prev() {
    this.post({ type: "cmd", cmd: "prev" });
  }
  stop() {
    this.post({ type: "cmd", cmd: "stop" });
  }

  /** Start reading at the sentence the caret sits on (or the one just before). */
  async readFromCursor() {
    const ed = vscode.window.activeTextEditor;
    if (!ed) {
      return;
    }
    const line = ed.selection.active.line + 1;
    if (!(await this.ensureReady())) {
      return;
    }
    const target = pickChunkForLine(this.chunks, line);
    if (target) {
      this.post({ type: "cmd", cmd: "playAt", i: target.i });
    } else {
      vscode.window.showInformationMessage("MdReader: 読み上げる文がありません");
    }
  }
}

export async function activate(context: vscode.ExtensionContext) {
  extRoot = context.extensionPath;
  log = vscode.window.createOutputChannel("MdReader");
  const panel = new Panel(context.extensionUri);

  context.subscriptions.push(
    log,
    vscode.window.registerWebviewViewProvider("mdreader.panel", panel, {
      webviewOptions: { retainContextWhenHidden: true },
    }),
    vscode.window.onDidChangeActiveTextEditor(() => void panel.syncActiveEditor()),
    vscode.workspace.onDidChangeTextDocument((e) => panel.onDocEdited(e)),
    vscode.commands.registerCommand("mdreader.playPause", () => void panel.playPause()),
    vscode.commands.registerCommand("mdreader.next", () => panel.next()),
    vscode.commands.registerCommand("mdreader.prev", () => panel.prev()),
    vscode.commands.registerCommand("mdreader.stop", () => panel.stop()),
    vscode.commands.registerCommand("mdreader.readFromCursor", () => void panel.readFromCursor()),
    vscode.commands.registerCommand("mdreader.restartServer", async () => {
      server?.kill();
      server = undefined;
      await new Promise((r) => setTimeout(r, 500));
      if (await ensureServer()) {
        vscode.window.showInformationMessage("MdReader: サーバを再起動しました");
        void panel.syncActiveEditor();
      }
    })
  );
}

export function deactivate() {
  server?.kill();
  server = undefined;
}
