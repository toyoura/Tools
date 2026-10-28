// caret 行 -> 読み始める文 の対応を確認する。読み上げサーバが動いている必要がある。
//   node scripts/pick.test.js <markdown ファイル> [port]
//
// 文書の全行について、次の 2 つを確かめる。
//   1. その行を範囲に含む文があるなら、選ばれるのは「最初の」その文であること
//      (段落の先頭の文を飛ばして途中から読み始めない)
//   2. 含む文がないなら、選ばれるのは直前の文であること (caret より後ろへ飛ばない)
const path = require("path");
const fs = require("fs");
const { pickChunkForLine } = require(path.join(__dirname, "..", "out", "pick.js"));

const file = process.argv[2];
const port = process.argv[3] || "8765";
if (!file) {
  console.error("usage: node scripts/pick.test.js <markdown ファイル> [port]");
  process.exit(2);
}
const md = fs.readFileSync(file, "utf8");

(async () => {
  const r = await fetch(`http://127.0.0.1:${port}/api/parse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: md }),
  });
  if (!r.ok) {
    console.error("サーバ応答:", r.status, await r.text());
    process.exit(1);
  }
  const { chunks } = await r.json();
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const spoken = chunks.filter((c) => c.say);
  console.log(`${path.basename(file)}: ${lines.length} 行, ${spoken.length} 文`);

  let bad = 0;
  for (let ln = 1; ln <= lines.length; ln++) {
    const got = pickChunkForLine(chunks, ln);
    if (!got) {
      continue;
    }
    const covering = spoken.filter((c) => c.line <= ln && (c.end ?? c.line) >= ln);
    if (covering.length) {
      if (got.i !== covering[0].i) {
        if (++bad <= 5) {
          console.log(`  L${ln}: 先頭の文でない -> i=${got.i} (期待 i=${covering[0].i})`);
        }
      }
    } else if (got.line > ln) {
      if (++bad <= 5) {
        console.log(`  L${ln}: caret より後ろの文 -> L${got.line}`);
      }
    }
  }

  // 引数で行を渡すと、その行で何が読まれるかを表示する
  for (const ln of (process.argv.slice(4) || []).map(Number).filter(Boolean)) {
    const c = pickChunkForLine(chunks, ln);
    console.log(`\n  caret L${ln}`);
    console.log(`    src : ${(lines[ln - 1] || "").trim().slice(0, 56)}`);
    console.log(`    読む: L${c.line}-${c.end} ${c.text.slice(0, 56)}`);
  }

  console.log(bad === 0 ? "\n判定: 全行で期待どおり" : `\n判定: ${bad} 行がおかしい`);
  process.exit(bad === 0 ? 0 : 1);
})();
