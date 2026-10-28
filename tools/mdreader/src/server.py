"""MdReader - read a Markdown file aloud in Japanese while you edit it in Cursor.

    python server.py path/to/note.md

Opens a local page that speaks the file with edge-tts (ja-JP Nanami / Keita),
highlights the sentence being read, reloads when the file changes on disk, and
jumps Cursor to the corresponding line on click.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import quote

import edge_tts
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mdparse import parse  # noqa: E402

HERE = Path(__file__).resolve().parent
CACHE = Path(tempfile.gettempdir()) / "mdreader_cache"
CACHE.mkdir(exist_ok=True)
TEXT_EXT = {".md", ".markdown", ".mdx", ".txt", ".tex", ".latex"}

app = FastAPI(title="MdReader")
_tts_lock = asyncio.Semaphore(4)

# A second drop onto MdReader.bat hands the file to the page that is already open
# instead of piling up browser tabs.  The page polls /api/pending; the launcher
# posts to /api/focus and uses "viewer" to decide whether to open a browser.
_pending = {"seq": 0, "path": None}
_last_poll = 0.0

# edge-tts is the default engine; SAPI is the offline safety net. See /api/tts.
EDGE_COOLDOWN = 120.0
_tts_state: dict = {"last": None, "cooldown_until": 0.0, "last_error": ""}

SAPI_PS = r"""param([string]$TextFile, [string]$OutFile, [string]$Lang = 'ja')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$text = [System.IO.File]::ReadAllText($TextFile, [System.Text.Encoding]::UTF8)
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$installed = $s.GetInstalledVoices()
$pick = $installed | Where-Object { $_.VoiceInfo.Culture.Name -like ($Lang + '*') } | Select-Object -First 1
if (-not $pick) { $pick = $installed | Select-Object -First 1 }
if ($pick) { $s.SelectVoice($pick.VoiceInfo.Name) }
$s.SetOutputToWaveFile($OutFile)
$s.Speak($text)
$s.Dispose()
"""


def _resolve(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve()


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="replace")


@app.get("/")
def index():
    return FileResponse(HERE / "static" / "index.html")


@app.get("/api/doc")
def doc(path: str):
    p = _resolve(path)
    if not p.is_file():
        raise HTTPException(404, f"file not found: {p}")
    if p.suffix.lower() not in TEXT_EXT:
        raise HTTPException(400, f"unsupported file type: {p.suffix}")
    return {
        "path": str(p),
        "name": p.name,
        "dir": str(p.parent),
        "mtime": p.stat().st_mtime,
        "chunks": parse(_read(p)),
    }


class ParseReq(BaseModel):
    text: str


@app.post("/api/parse")
def parse_text(req: ParseReq):
    """Parse a buffer the client already holds (the Cursor extension sends the
    editor contents, so unsaved edits are read aloud too)."""
    return {"chunks": parse(req.text)}


@app.get("/api/stat")
def stat(path: str):
    p = _resolve(path)
    if not p.is_file():
        raise HTTPException(404, "file not found")
    return {"mtime": p.stat().st_mtime, "size": p.stat().st_size}


@app.get("/api/ls")
def ls(dir: str):
    d = _resolve(dir)
    if not d.is_dir():
        raise HTTPException(404, f"directory not found: {d}")
    dirs, files = [], []
    try:
        for e in sorted(d.iterdir(), key=lambda x: x.name.lower()):
            if e.name.startswith("."):
                continue
            try:
                if e.is_dir():
                    dirs.append({"name": e.name, "path": str(e), "dir": True})
                elif e.suffix.lower() in TEXT_EXT:
                    files.append({"name": e.name, "path": str(e), "dir": False})
            except OSError:
                continue
    except PermissionError:
        raise HTTPException(403, "permission denied")
    parent = str(d.parent) if d.parent != d else None
    return {"dir": str(d), "parent": parent, "entries": dirs + files}


def _ready(f: Path) -> bool:
    return f.exists() and f.stat().st_size > 0


def _audio(f: Path, media_type: str, engine: str) -> FileResponse:
    _tts_state["last"] = engine
    return FileResponse(
        f,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=604800", "X-MdReader-Engine": engine},
    )


@app.get("/api/tts")
async def tts(text: str, voice: str = "ja-JP-NanamiNeural", rate: str = "+0%",
              pitch: str = "+0Hz", engine: str = "auto"):
    """Synthesise one sentence.

    edge-tts is an unofficial client of the Edge read-aloud endpoint, so it can
    stop working without notice (offline, rate limited, Microsoft changes the
    protocol). When it fails we fall back to Windows SAPI, which is offline and
    always available but noticeably more robotic. A cooldown keeps every later
    sentence from paying the edge-tts retry delay while it is down.
    """
    text = text.strip()
    if not text:
        raise HTTPException(400, "empty text")
    engine = (os.environ.get("MDREADER_TTS") or engine or "auto").strip().lower()
    if engine not in ("auto", "edge", "sapi"):
        raise HTTPException(400, f"unknown engine: {engine}")

    edge_file = CACHE / (
        hashlib.sha1(f"{voice}|{rate}|{pitch}|{text}".encode("utf-8")).hexdigest() + ".mp3"
    )
    lang = (voice.split("-")[0] or "ja").lower()
    sapi_file = CACHE / (
        hashlib.sha1(f"sapi|{lang}|{text}".encode("utf-8")).hexdigest() + ".wav"
    )

    if engine != "sapi":
        if _ready(edge_file):
            return _audio(edge_file, "audio/mpeg", "edge")
        if time.time() >= _tts_state["cooldown_until"]:
            try:
                async with _tts_lock:
                    if not _ready(edge_file):
                        data = await _synth_edge(text, voice, rate, pitch)
                        tmp = edge_file.with_suffix(".part")
                        tmp.write_bytes(data)
                        os.replace(tmp, edge_file)
                _tts_state["cooldown_until"] = 0.0
                return _audio(edge_file, "audio/mpeg", "edge")
            except Exception as e:
                _tts_state["cooldown_until"] = time.time() + EDGE_COOLDOWN
                _tts_state["last_error"] = str(e)[:300]
                print(f"[tts] edge-tts 失敗、{EDGE_COOLDOWN:.0f} 秒 SAPI に切り替えます: {e}")

    if engine == "edge":
        raise HTTPException(502, f"edge-tts に接続できません: {_tts_state['last_error']}")
    if not _sapi_available():
        raise HTTPException(502, "edge-tts に接続できず、SAPI も使えません (Windows 以外)")

    if not _ready(sapi_file):
        async with _tts_lock:
            if not _ready(sapi_file):
                try:
                    await asyncio.to_thread(_synth_sapi, text, sapi_file, lang)
                except Exception as e:
                    raise HTTPException(502, f"SAPI 合成に失敗しました: {e}")
    return _audio(sapi_file, "audio/wav", "sapi")


@app.get("/api/engine")
def engine_state():
    """Which engine the last sentence came from, so the UI can say so."""
    left = max(0.0, _tts_state["cooldown_until"] - time.time())
    return {
        "last": _tts_state["last"],
        "edge_ok": left == 0.0,
        "cooldown_sec": round(left),
        "sapi_available": _sapi_available(),
        "last_error": _tts_state["last_error"],
    }


async def _synth_edge(text: str, voice: str, rate: str, pitch: str) -> bytes:
    last: Exception | None = None
    for attempt in range(3):
        try:
            comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
            buf = bytearray()
            async for ch in comm.stream():
                if ch["type"] == "audio":
                    buf += ch["data"]
            if buf:
                return bytes(buf)
            last = RuntimeError("empty audio")
        except Exception as e:  # network hiccup -> retry
            last = e
        await asyncio.sleep(0.6 * (attempt + 1))
    raise RuntimeError(str(last))


def _sapi_available() -> bool:
    return os.name == "nt"


def _sapi_script() -> Path:
    # Rewrite whenever the content differs: the cache directory outlives the
    # process, so "write only if missing" silently keeps an outdated script.
    p = CACHE / "sapi.ps1"
    try:
        if p.read_text(encoding="utf-8") == SAPI_PS:
            return p
    except OSError:
        pass
    p.write_text(SAPI_PS, encoding="utf-8")
    return p


def _synth_sapi(text: str, out: Path, lang: str = "ja") -> None:
    """Blocking; call through asyncio.to_thread. Writes a 22 kHz mono WAV.

    lang is the language part of the requested edge-tts voice, so an English
    sentence keeps an English voice when we fall back to SAPI."""
    stem = out.with_suffix("")
    txt = Path(str(stem) + ".txt")
    tmp = Path(str(stem) + ".part.wav")
    txt.write_text(text, encoding="utf-8")
    try:
        r = subprocess.run(
            [
                shutil.which("powershell") or "powershell",
                "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(_sapi_script()),
                "-TextFile", str(txt), "-OutFile", str(tmp), "-Lang", lang,
            ],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0 or not _ready(tmp):
            raise RuntimeError((r.stderr or r.stdout or "no output").strip()[:300])
        os.replace(tmp, out)
    finally:
        txt.unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)


@app.get("/api/pending")
def pending():
    """Polled by the open page; doubles as the 'a viewer is alive' heartbeat."""
    global _last_poll
    _last_poll = time.time()
    return _pending


class FocusReq(BaseModel):
    path: str


@app.post("/api/focus")
def focus(req: FocusReq):
    p = _resolve(req.path)
    if not p.is_file():
        raise HTTPException(404, f"file not found: {p}")
    _pending["path"] = str(p)
    _pending["seq"] += 1
    return {"ok": True, "path": str(p), "viewer": time.time() - _last_poll < 6.0}


class OpenReq(BaseModel):
    path: str
    line: int = 1


@app.post("/api/open")
def open_in_editor(req: OpenReq):
    p = _resolve(req.path)
    exe = os.environ.get("MDREADER_EDITOR") or shutil.which("cursor") or shutil.which("code")
    if not exe:
        raise HTTPException(500, "cursor / code コマンドが見つかりません")
    cmd = f'"{exe}" -g "{p}:{max(1, req.line)}:1"'
    subprocess.Popen(cmd, shell=True)
    return {"ok": True, "cmd": cmd}


_voice_cache: dict = {"at": 0.0, "voices": []}

# Used when the voice list cannot be fetched (offline, or Microsoft unreachable).
# Returning something is better than an error: the SAPI fallback still speaks,
# and the UI must not end up with an empty voice menu.
VOICE_FALLBACK = [
    {"ShortName": "ja-JP-NanamiNeural", "Gender": "Female", "Locale": "ja-JP"},
    {"ShortName": "ja-JP-KeitaNeural", "Gender": "Male", "Locale": "ja-JP"},
    {"ShortName": "en-US-AriaNeural", "Gender": "Female", "Locale": "en-US"},
    {"ShortName": "en-US-GuyNeural", "Gender": "Male", "Locale": "en-US"},
    {"ShortName": "en-US-AvaMultilingualNeural", "Gender": "Female", "Locale": "en-US"},
    {"ShortName": "en-US-AndrewMultilingualNeural", "Gender": "Male", "Locale": "en-US"},
    {"ShortName": "en-GB-SoniaNeural", "Gender": "Female", "Locale": "en-GB"},
    {"ShortName": "en-GB-RyanNeural", "Gender": "Male", "Locale": "en-GB"},
]


@app.get("/api/voices")
async def voices(locales: str = "ja-JP,en-US,en-GB"):
    """Voices the UI can offer, grouped by locale. Cached for an hour: the list
    only changes when Microsoft adds voices, and it must not block playback."""
    wanted = tuple(p.strip() for p in locales.split(",") if p.strip())
    if time.time() - _voice_cache["at"] > 3600 or not _voice_cache["voices"]:
        try:
            _voice_cache["voices"] = await edge_tts.list_voices()
            _voice_cache["at"] = time.time()
        except Exception as e:
            print(f"[voices] 一覧を取得できないため組み込みの一覧を返します: {e}")
            _voice_cache["voices"] = VOICE_FALLBACK
            _voice_cache["at"] = 0.0  # retry on the next request
    out = [
        {
            "name": v["ShortName"],
            "gender": v["Gender"],
            "locale": v["Locale"],
            "lang": v["Locale"].split("-")[0],
            "label": v["ShortName"].split("-")[-1].replace("Neural", ""),
            "multilingual": "Multilingual" in v["ShortName"],
        }
        for v in _voice_cache["voices"]
        if not wanted or v["Locale"].startswith(wanted)
    ]
    def rank(v):
        # keep the order the caller asked for: ja-JP first, then en-US, then en-GB
        for k, w in enumerate(wanted):
            if v["locale"].startswith(w):
                return k
        return len(wanted)

    out.sort(key=lambda v: (rank(v), v["locale"], v["name"]))
    return out


def main():
    ap = argparse.ArgumentParser(description="Markdown 読み上げビューア")
    ap.add_argument("path", nargs="?", help="開く Markdown ファイル")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()

    url = f"http://127.0.0.1:{a.port}/"
    if a.path:
        url += "?path=" + quote(str(_resolve(a.path)))
    if not a.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"MdReader: {url}")
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
