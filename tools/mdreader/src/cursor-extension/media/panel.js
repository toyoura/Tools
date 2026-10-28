// Runs inside the sidebar webview. It owns the <audio> element, because the
// extension host has no way to play sound.
(function () {
  const vscode = acquireVsCodeApi();
  const ORIGIN = window.MDREADER_ORIGIN;
  const $ = (s) => document.querySelector(s);

  const S = {
    chunks: [], cur: 0, playing: false, speed: 1.4,
    voice: "auto", voiceJa: "ja-JP-NanamiNeural", voiceEn: "en-US-AriaNeural",
  };
  const audio = new Audio();
  audio.preload = "auto";

  // A Japanese manuscript still has English captions and abstracts. In auto mode
  // each sentence picks the voice for the script it is written in.
  const JA_CHARS = /[぀-ヿ㐀-鿿豈-﫿ｦ-ﾟ]/;
  function voiceFor(text) {
    if (S.voice !== "auto") return S.voice;
    return JA_CHARS.test(text) ? S.voiceJa : S.voiceEn;
  }

  const url = (c) =>
    ORIGIN + "/api/tts?text=" + encodeURIComponent(c.say) +
    "&voice=" + encodeURIComponent(voiceFor(c.say));

  function speakableCount() {
    return S.chunks.filter((c) => c.say).length;
  }
  function nextSpeakable(from) {
    for (let i = from; i < S.chunks.length; i++) if (S.chunks[i].say) return i;
    return -1;
  }
  function prevSpeakable(from) {
    for (let i = from; i >= 0; i--) if (S.chunks[i].say) return i;
    return -1;
  }

  function lineLabel(c) {
    if (!c) return "";
    return c.end && c.end !== c.line ? c.line + "–" + c.end + " 行目" : c.line + " 行目";
  }

  function paint() {
    const total = speakableCount();
    const done = S.chunks.filter((c) => c.say && c.i < S.cur).length;
    const cc = S.chunks[S.cur];
    // Line first: it is what you act on in the editor. The sentence count is
    // only progress, so it stays secondary.
    $("#pos").textContent = total
      ? lineLabel(cc) + "　" + (done + 1) + " / " + total + " 文"
      : "";
    const c = S.chunks[S.cur];
    $("#now").textContent = c ? c.text : "";
    const n = nextSpeakable(S.cur + 1);
    $("#next-up").textContent = n >= 0 ? S.chunks[n].text : "";
    $("#play").textContent = S.playing ? "❚❚ 一時停止" : "▶ 再生";
  }

  // The webview origin is vscode-webview://, so every call to the server is
  // cross-origin. no-cors gives an opaque response we never read, but it still
  // warms the HTTP cache that <audio> reads from a moment later.
  function prefetch(i) {
    let k = i;
    for (let n = 0; n < 2; n++) {
      k = nextSpeakable(k + 1);
      if (k < 0) break;
      fetch(url(S.chunks[k]), { mode: "no-cors", cache: "force-cache" }).catch(() => {});
    }
  }

  function play(i) {
    const j = nextSpeakable(i);
    if (j < 0) {
      stop();
      return;
    }
    S.cur = j;
    S.playing = true;
    audio.src = url(S.chunks[j]);
    audio.playbackRate = S.speed;
    audio.play().catch((e) => {
      stop();
      $("#err").textContent = "再生できません: " + e.message;
    });
    vscode.postMessage({ type: "chunk", i: j });
    paint();
    prefetch(j);
  }

  function stop() {
    S.playing = false;
    audio.pause();
    paint();
  }

  audio.onended = () => {
    if (!S.playing) return;
    const j = nextSpeakable(S.cur + 1);
    if (j < 0) {
      stop();
      return;
    }
    play(j);
  };
  audio.onerror = () => {
    if (S.playing) {
      stop();
      $("#err").textContent = "音声の取得に失敗しました (ネットワーク?)";
    }
  };

  function step(dir) {
    const j = dir > 0 ? nextSpeakable(S.cur + 1) : prevSpeakable(S.cur - 1);
    if (j < 0) return;
    if (S.playing) {
      play(j);
    } else {
      S.cur = j;
      vscode.postMessage({ type: "chunk", i: j });
      paint();
    }
  }

  $("#play").onclick = () => (S.playing ? stop() : play(S.cur));
  $("#next").onclick = () => step(1);
  $("#prev").onclick = () => step(-1);
  $("#voice").onchange = (e) => {
    S.voice = e.target.value;
    vscode.postMessage({ type: "setting", key: "voice", value: S.voice });
    // remember an explicit pick as that language's default for auto mode
    if (S.voice.startsWith("ja-")) {
      S.voiceJa = S.voice;
      vscode.postMessage({ type: "setting", key: "voiceJa", value: S.voice });
    }
    if (S.voice.startsWith("en-")) {
      S.voiceEn = S.voice;
      vscode.postMessage({ type: "setting", key: "voiceEn", value: S.voice });
    }
    if (S.playing) play(S.cur);
  };
  $("#speed").onchange = (e) => {
    S.speed = +e.target.value;
    audio.playbackRate = S.speed;
    vscode.postMessage({ type: "setting", key: "speed", value: S.speed });
  };

  window.addEventListener("message", (ev) => {
    const m = ev.data;
    if (m.type === "doc") {
      S.chunks = m.chunks;
      $("#err").textContent = "";
      if (!m.keep) {
        S.cur = m.cur;
        stop();
      } else {
        // an edit landed: keep the audio going, just adopt the new list
        S.cur = m.cur;
      }
      paint();
    } else if (m.type === "config") {
      S.voice = m.voice;
      S.voiceJa = m.voiceJa || S.voiceJa;
      S.voiceEn = m.voiceEn || S.voiceEn;
      S.speed = m.speed;
      const sel = $("#voice");
      sel.value = [...sel.options].some((o) => o.value === m.voice) ? m.voice : "auto";
      $("#speed").value = String(m.speed);
      audio.playbackRate = m.speed;
    } else if (m.type === "voices") {
      const sel = $("#voice");
      [...sel.querySelectorAll("optgroup")].forEach((g) => g.remove());
      const groups = {};
      for (const v of m.voices) (groups[v.locale] = groups[v.locale] || []).push(v);
      for (const locale of Object.keys(groups)) {
        const g = document.createElement("optgroup");
        g.label = locale;
        for (const v of groups[locale]) {
          const o = document.createElement("option");
          o.value = v.name;
          o.textContent =
            v.label + " (" + (v.gender === "Female" ? "女性" : "男性") + ")" +
            (v.multilingual ? " 多言語" : "");
          g.appendChild(o);
        }
        sel.appendChild(g);
      }
      sel.value = m.voices.some((v) => v.name === S.voice) ? S.voice : "auto";
    } else if (m.type === "engine") {
      const el = $("#engine");
      if (m.last === "sapi") {
        el.textContent =
          "⚠ SAPI (オフライン音声) で読んでいます" +
          (m.cooldown_sec ? " — " + m.cooldown_sec + " 秒後に edge-tts を再試行" : "");
        el.title = m.last_error || "";
      } else {
        el.textContent = "";
        el.title = "";
      }
    } else if (m.type === "error") {
      $("#err").textContent = m.message;
    } else if (m.type === "cmd") {
      if (m.cmd === "playPause") S.playing ? stop() : play(S.cur);
      else if (m.cmd === "next") step(1);
      else if (m.cmd === "prev") step(-1);
      else if (m.cmd === "stop") stop();
      else if (m.cmd === "playAt") play(m.i);
    }
  });

  vscode.postMessage({ type: "ready" });
})();
