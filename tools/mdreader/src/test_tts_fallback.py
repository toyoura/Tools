"""edge-tts と SAPI の切り替えを確認する。サーバの起動は不要。

    python test_tts_fallback.py

edge-tts の呼び出しだけを差し替えて障害を模擬し、SAPI に落ちること、
クールダウン中は再試行しないこと、キャッシュ済みの mp3 は使い続けることを見る。
"""
import asyncio, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import server
from fastapi import HTTPException

T1 = "フォールバックの確認その一です。"
T2 = "フォールバックの確認その二です。"

def run(**kw):
    return asyncio.run(server.tts(**kw))

# 1. normal edge path
r = run(text=T1, engine="auto")
print("1 auto(edge ok)   :", r.media_type, r.headers.get("x-mdreader-engine"), r.path.name)
assert r.media_type == "audio/mpeg" and r.headers["x-mdreader-engine"] == "edge"

# 2. explicitly forced SAPI
r = run(text=T1, engine="sapi")
print("2 engine=sapi     :", r.media_type, r.headers.get("x-mdreader-engine"), r.path.name)
assert r.media_type == "audio/wav" and r.headers["x-mdreader-engine"] == "sapi"

# 3. edge goes down -> auto falls back to SAPI
async def boom(*a, **k):
    raise RuntimeError("simulated outage")
server._synth_edge = boom
t0 = time.time()
r = run(text=T2, engine="auto")
print("3 auto(edge down) :", r.media_type, r.headers.get("x-mdreader-engine"), f"{time.time()-t0:.1f}s")
assert r.media_type == "audio/wav" and r.headers["x-mdreader-engine"] == "sapi"

# 4. cooldown: the next sentence must not retry edge (so it must be fast)
t0 = time.time()
r = run(text="三つ目の文です。", engine="auto")
dt = time.time() - t0
print("4 cooldown active :", r.headers.get("x-mdreader-engine"), f"{dt:.1f}s",
      "cooldown_sec =", server.engine_state()["cooldown_sec"])
assert r.headers["x-mdreader-engine"] == "sapi"
assert server.engine_state()["edge_ok"] is False

# 5. a sentence already cached from edge is still served as mp3 during cooldown
r = run(text=T1, engine="auto")
print("5 cached edge hit :", r.media_type, r.headers.get("x-mdreader-engine"))
assert r.media_type == "audio/mpeg" and r.headers["x-mdreader-engine"] == "edge"

# 6. engine=edge must not silently downgrade
try:
    run(text="エッジ固定の文です。", engine="edge")
    print("6 engine=edge     : FAILED (例外が出るべき)"); sys.exit(1)
except HTTPException as e:
    print("6 engine=edge     :", e.status_code, str(e.detail)[:50])
    assert e.status_code == 502

print("\n判定: すべて期待どおり")
