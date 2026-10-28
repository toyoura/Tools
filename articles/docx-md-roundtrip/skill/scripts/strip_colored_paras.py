# -*- coding: utf-8 -*-
"""Remove every <w:p> paragraph that contains a run of a given font color.

Use to clean institution-added guidance text (e.g. Yamanashi Univ. blue notes,
color 0070C0, marked "この青文字は調書作成後に削除して下さい") out of a form
template before using it with md2docx.py.

Usage:
    set PYTHONUTF8=1
    python strip_colored_paras.py <in.docx> <out.docx> [color=0070C0]

Only paragraphs are removed; tables/cells are left intact (guidance text lives
in body paragraphs, not inside the instruction tables). Verify by PDF after.
"""
import os
import re
import sys
import zipfile


def element_ranges(xml, tag):
    """Yield (start, end) of <tag>...</tag>, handling self-closing and nesting."""
    open_re = re.compile(r"<" + re.escape(tag) + r"[ >/]")
    close = "</" + tag + ">"
    i = 0
    while True:
        m = open_re.search(xml, i)
        if not m:
            return
        s = m.start()
        if xml[m.end() - 1] == "/" and xml[m.end()] == ">":
            yield (s, m.end() + 1)
            i = m.end() + 1
            continue
        depth, j = 1, m.end()
        while depth:
            mo = open_re.search(xml, j)
            mc = xml.find(close, j)
            if mc == -1:
                raise SystemExit(f"unbalanced <{tag}>")
            if mo and mo.start() < mc:
                if xml[mo.end() - 1] == "/" and xml[mo.end()] == ">":
                    j = mo.end() + 1
                else:
                    depth += 1
                    j = mo.end()
            else:
                depth -= 1
                j = mc + len(close)
        yield (s, j)
        i = j


def main():
    if len(sys.argv) < 3:
        raise SystemExit("usage: python strip_colored_paras.py <in.docx> <out.docx> [color]")
    inp, outp = sys.argv[1], sys.argv[2]
    color = sys.argv[3] if len(sys.argv) > 3 else "0070C0"
    needle = f'<w:color w:val="{color}"'

    zin = zipfile.ZipFile(inp)
    xml = zin.read("word/document.xml").decode("utf-8")

    keep, pos, removed = [], 0, 0
    for s, e in element_ranges(xml, "w:p"):
        if needle in xml[s:e]:
            keep.append(xml[pos:s])
            removed += 1
        else:
            keep.append(xml[pos:e])
        pos = e
    keep.append(xml[pos:])
    new_xml = "".join(keep)

    with zipfile.ZipFile(outp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = (new_xml.encode("utf-8") if item.filename == "word/document.xml"
                    else zin.read(item.filename))
            zout.writestr(item, data)
    zin.close()
    print(f"removed {removed} colored({color}) paragraphs -> {outp}")


if __name__ == "__main__":
    main()
