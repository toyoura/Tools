# -*- coding: utf-8 -*-
"""既存 docx を土台に、本文段落の文字だけを md 由来の内容へ差し替える。

再ビルド(md2docx)と違い、docx 側の手調整を保つ。図を Word で位置・サイズ調整した後に
本文だけ直したいときに使う。

Usage:
    set PYTHONUTF8=1
    python patch_body.py <target.docx> <reference.docx>   # dry-run
    python patch_body.py <target.docx> <reference.docx> --apply

reference.docx は md2docx.py で md から作った出力(output: を一時名に変えてビルドする)。

保つもの: 図(<w:drawing>)を含む段落、頁調整用の空段落、段落書式(pPr)、見出しの網掛け・改頁。
変えるもの: 本文段落のラン(文字と太字)のみ。

注意: 文字列比較なので「書体だけの変更」は検出しない。書体を変えるときは md2docx で
再ビルドするか、rFonts を直接置換すること。"""
import io, re, sys, difflib, zipfile, shutil, pathlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
DRY = "--apply" not in sys.argv

REAL = pathlib.Path(sys.argv[1])
REF  = pathlib.Path(sys.argv[2])
PARA = re.compile(r"<w:p[ >].*?</w:p>", re.S)
WT   = re.compile(r"<w:t(?: [^>]*)?>(.*?)</w:t>", re.S)   # <w:tabs> を拾わない

def load(p):
    x = zipfile.ZipFile(p).read("word/document.xml").decode("utf-8")
    ps = [(m.start(), m.end(), m.group(0)) for m in PARA.finditer(x)]
    return x, ps

def text(seg):
    t = "".join(WT.findall(seg))
    return t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")

def norm(seg):
    if "<w:drawing>" in seg: return "\x00IMG"
    return re.sub(r"\s|\*", "", text(seg))

rx, rp = load(REAL)
fx, fp = load(REF)

# 空段落を除外し、元の添字を持ったまま並べる
ri = [i for i,(_,_,s) in enumerate(rp) if norm(s)]
fi = [i for i,(_,_,s) in enumerate(fp) if norm(s)]
rn = [norm(rp[i][2]) for i in ri]
fn = [norm(fp[i][2]) for i in fi]
print("中身のある段落: 現行 %d / md由来 %d  (空段落 %d / %d は対象外)"
      % (len(ri), len(fi), len(rp)-len(ri), len(fp)-len(fi)))
print()

sm = difflib.SequenceMatcher(None, rn, fn, autojunk=False)
edits = []
for tag, i1, i2, j1, j2 in sm.get_opcodes():
    if tag == "equal": continue
    if any(rn[k] == "\x00IMG" for k in range(i1,i2)) or \
       any(fn[k] == "\x00IMG" for k in range(j1,j2)):
        print("!! 図の段落が差分に入りました。中止します。"); sys.exit(1)
    print("=== %s  現行[%d:%d] → md[%d:%d]" % (tag,i1,i2,j1,j2))
    for k in range(i1,i2): print("  - " + rn[k][:78])
    for k in range(j1,j2): print("  + " + fn[k][:78])
    print()
    n = min(i2-i1, j2-j1)
    for d in range(n):
        s, e, seg = rp[ri[i1+d]]
        m  = re.search(r"<w:pPr>.*?</w:pPr>", seg, re.S)
        fseg = fp[fi[j1+d]][2]
        fm = re.search(r"<w:pPr>.*?</w:pPr>", fseg, re.S)
        edits.append((s, e, (seg[:m.end()] if m else seg[:seg.index(">")+1])
                            + (fseg[fm.end():] if fm else fseg)))
    if j2-j1 > n:
        anchor = rp[ri[i1+n-1]][1] if n else rp[ri[i1]][0]
        edits.append((anchor, anchor,
                      "".join(fp[fi[j1+d]][2] for d in range(n, j2-j1))))
    for d in range(n, i2-i1):
        s, e, _ = rp[ri[i1+d]]
        edits.append((s, e, ""))

if DRY:
    print("[dry-run] 編集 %d 件。--apply で書き込みます。" % len(edits)); sys.exit()

out = rx
for s, e, rep in sorted(edits, key=lambda x: -x[0]):
    out = out[:s] + rep + out[e:]
shutil.copyfile(REAL, str(REAL) + ".bak")
zin = zipfile.ZipFile(REAL); items = zin.infolist()
data = {n.filename: zin.read(n.filename) for n in items}; zin.close()
data["word/document.xml"] = out.encode("utf-8")
with zipfile.ZipFile(REAL, "w", zipfile.ZIP_DEFLATED) as z:
    for n in items: z.writestr(n, data[n.filename])
print("書き込み完了。編集 %d 件 / バックアップ %s.bak" % (len(edits), REAL.name))
