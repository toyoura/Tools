"""音声一覧が取れないときに空にならないことを確かめる。サーバ起動は不要。"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import server

# 1. 通常
v = asyncio.run(server.voices())
print("1 通常          :", len(v), "件", [x["name"] for x in v[:3]])
assert len(v) > 5

# 2. 一覧の取得が失敗する場合 (オフライン相当)
async def boom():
    raise RuntimeError("simulated offline")

server.edge_tts.list_voices = boom
server._voice_cache["at"] = 0.0
server._voice_cache["voices"] = []
v = asyncio.run(server.voices())
langs = sorted({x["locale"] for x in v})
print("2 取得失敗      :", len(v), "件", langs)
assert len(v) >= 6, "空の一覧を返してはいけない"
assert any(x["locale"] == "ja-JP" for x in v) and any(x["lang"] == "en" for x in v)

# 3. ロケール指定が効くか
v = asyncio.run(server.voices(locales="ja-JP"))
print("3 ja-JP のみ    :", len(v), "件", [x["name"] for x in v])
assert all(x["locale"] == "ja-JP" for x in v)

print()
print("判定: すべて期待どおり")
