# -*- coding: utf-8 -*-
"""Extract paragraphs of a filled form-docx as Markdown-ish text (import aid).

Usage:
    set PYTHONUTF8=1
    python docx2md.py <in.docx> [> draft.md]

Output is raw material for building a content.md: tables and section breaks
appear as HTML comments; the section anchors and frontmatter must be added
by hand (see references/format.md).
"""
import io
import re
import sys
import zipfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def is_self_closing(xml, tag_start):
    """Given the start of an opening tag ("<w:p ..."), find where it ends
    and report whether it's self-closing ("... />") even when the tag
    carries attributes between the name and the closing angle bracket."""
    tag_end = xml.find(">", tag_start)
    return tag_end, xml[tag_end - 1] == "/"


def element_ranges(xml, tags):
    open_res = {t: re.compile(r"<" + re.escape(t) + r"[ >/]") for t in tags}
    i = 0
    while True:
        best = None
        for t, orx in open_res.items():
            m = orx.search(xml, i)
            if m and (best is None or m.start() < best[1].start()):
                best = (t, m)
        if best is None:
            return
        tag, m = best
        close = "</" + tag + ">"
        s = m.start()
        tag_end, self_closing = is_self_closing(xml, m.start())
        if self_closing:
            yield tag, s, tag_end + 1
            i = tag_end + 1
            continue
        depth, j = 1, tag_end + 1
        orx = open_res[tag]
        while depth:
            mo = orx.search(xml, j)
            mc = xml.find(close, j)
            if mc == -1:
                raise SystemExit(f"unbalanced <{tag}>")
            if mo and mo.start() < mc:
                mo_end, mo_self_closing = is_self_closing(xml, mo.start())
                if mo_self_closing:
                    j = mo_end + 1
                else:
                    depth += 1
                    j = mo_end + 1
            else:
                depth -= 1
                j = mc + len(close)
        yield tag, s, j
        i = j


def para_text_with_bold(pxml):
    """Reconstruct paragraph text, wrapping bold runs in **."""
    # drop nested textbox content to avoid duplicated text
    pxml = re.sub(r"<w:txbxContent>.*?</w:txbxContent>", "", pxml, flags=re.S)
    parts = []
    for rm in re.finditer(r"<w:r(?: [^>]*)?>(.*?)</w:r>", pxml, re.S):
        r = rm.group(1)
        texts = re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>", r, re.S)
        if not texts:
            continue
        t = "".join(texts)
        t = t.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
        bold = "<w:b/>" in r.split("</w:rPr>")[0] if "</w:rPr>" in r else False
        parts.append((t, bold))
    # merge adjacent same-bold segments
    out = ""
    i = 0
    while i < len(parts):
        t, bold = parts[i]
        j = i + 1
        while j < len(parts) and parts[j][1] == bold:
            t += parts[j][0]
            j += 1
        out += f"**{t}**" if bold and t.strip() else t
        i = j
    return out


def classify(pxml, text):
    ppr = pxml.split("</w:pPr>")[0] if "</w:pPr>" in pxml else ""
    gothic_heading = "ＭＳ ゴシック" in ppr and "<w:b/>" in ppr
    if gothic_heading and "w:jc w:val=\"center\"" not in ppr:
        return "heading"
    if 'w:hanging="440"' in ppr:
        return "ref"
    if 'w:hanging="220"' in ppr:
        return "bullet"
    return "body"


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: python docx2md.py <in.docx>")
    with zipfile.ZipFile(sys.argv[1]) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    body_m = re.search(r"<w:body>(.*)</w:body>", xml, re.S)
    body = body_m.group(1) if body_m else xml

    for tag, s, e in element_ranges(body, ["w:p", "w:tbl"]):
        seg = body[s:e]
        if tag == "w:tbl":
            head = re.sub(r"<[^>]*>", "", seg).strip().replace("\n", "")[:40]
            print(f"<!-- 様式表: {head}... -->")
            print()
            continue
        if "<w:sectPr" in seg:
            print("<!-- 改セクション -->")
            print()
            continue
        # check for images before the text-emptiness test: a pure-picture
        # paragraph has no <w:t> at all, so text would be "" and get skipped
        if "<w:drawing" in seg or "<w:pict>" in seg:
            print("<!-- 画像段落 (元docxの図): ![キャプション](ファイル名.png){width=450} の形で書き直す -->")
            print()
            continue
        text = para_text_with_bold(seg)
        if not text.strip():
            continue
        kind = classify(seg, text)
        if kind == "heading":
            print(f"## {text.replace('**', '')}")
        elif kind == "bullet":
            print(f"- {text.lstrip('・')}")
        else:
            print(text)
        print()


if __name__ == "__main__":
    main()
