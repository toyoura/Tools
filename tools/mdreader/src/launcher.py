"""Open a Markdown file in MdReader, starting the server only if it is not up yet.

Called by MdReader.bat, which is the drag-and-drop target:

    MdReader.bat  C:\\path\\to\\paper.md

If MdReader is already running it hands the file to the page that is already
open (no second browser tab). Otherwise it starts the server minimised and
opens the browser.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
PORT = int(os.environ.get("MDREADER_PORT", "8765"))
BASE = f"http://127.0.0.1:{PORT}"
TEXT_EXT = {".md", ".markdown", ".mdx", ".txt", ".tex", ".latex"}

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def is_up() -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def start_server() -> None:
    """Launch server.py in its own minimised console so it survives this process."""
    args = [sys.executable, str(HERE / "server.py"), "--port", str(PORT), "--no-browser"]
    kwargs = {"cwd": str(HERE)}
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 7  # SW_SHOWMINNOACTIVE
        kwargs["startupinfo"] = si
        kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
    subprocess.Popen(args, **kwargs)


def wait_up(timeout: float = 25.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if is_up():
            return True
        time.sleep(0.25)
    return False


def focus(path: str) -> bool:
    """Ask a page that is already open to switch to this file. True if one answered."""
    req = urllib.request.Request(
        BASE + "/api/focus",
        data=json.dumps({"path": path}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return bool(json.load(r).get("viewer"))
    except urllib.error.HTTPError as e:
        print(f"サーバがファイルを開けません: {e.read().decode('utf-8', 'replace')}")
        return False
    except Exception as e:
        print(f"サーバに接続できません: {e}")
        return False


def main() -> int:
    paths = [Path(a).resolve() for a in sys.argv[1:] if a.strip()]
    if len(paths) > 1:
        print(f"複数のファイルが渡されました。最初の 1 つを開きます: {paths[0].name}")
    target = paths[0] if paths else None

    if target is not None:
        if not target.is_file():
            print(f"ファイルが見つかりません: {target}")
            return 1
        if target.suffix.lower() not in TEXT_EXT:
            print(f"対応していない拡張子です: {target.suffix}  ({', '.join(sorted(TEXT_EXT))})")
            return 1

    running = is_up()
    if not running:
        print(f"MdReader を起動しています (port {PORT}) ...")
        start_server()
        if not wait_up():
            print("サーバが起動しませんでした。最小化されたコンソールのエラーを確認してください。")
            return 1

    if target is None:
        webbrowser.open(BASE + "/")
        return 0

    if running and focus(str(target)):
        print(f"開いているタブに切り替えました: {target.name}")
        return 0

    webbrowser.open(BASE + "/?path=" + quote(str(target)))
    print(f"開きました: {target}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # keep the console readable when the .bat pauses
        print(f"エラー: {e}")
        sys.exit(1)
