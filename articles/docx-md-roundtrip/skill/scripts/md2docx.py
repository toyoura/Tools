# -*- coding: utf-8 -*-
"""Build a form-preserving docx from a Markdown content file.

Usage:
    set PYTHONUTF8=1
    python md2docx.py <content.md>

The Markdown frontmatter defines: template, output, page_targets, line_spacing.
See references/format.md for the full format specification.
"""
import io
import os
import re
import struct
import sys
import zipfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

EMU_PER_PT = 12700
DELETE_MARKER = "このテキストボックスごと削除すること"


# ---------------------------------------------------------------- frontmatter
def parse_frontmatter(text):
    m = re.match(r"---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        raise SystemExit("ERROR: frontmatter (--- ... ---) not found")
    meta = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, text[m.end():]


# ------------------------------------------------------------------- markdown
def split_sections(body):
    """Return list of (anchor, is_table, [block, ...])."""
    parts = re.split(r"(?m)^#\s*section:\s*(.+?)\s*$", body)
    if len(parts) < 3:
        raise SystemExit("ERROR: no '# section: <anchor>' headers found")
    sections = []
    for i in range(1, len(parts), 2):
        spec, chunk = parts[i], parts[i + 1]
        is_table = False
        if "|" in spec:
            head, _, tail = spec.rpartition("|")
            if tail.strip() == "table":
                spec, is_table = head.strip(), True
        blocks = [b.strip("\n") for b in re.split(r"\n\s*\n", chunk) if b.strip()]
        sections.append((spec, is_table, blocks))
    return sections


def join_lines(lines):
    """Join soft-wrapped lines: no space between CJK, one space between ASCII."""
    out = ""
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if out and re.search(r"[0-9A-Za-z,.;:)%\]]$", out) and re.match(r"[0-9A-Za-z(\[]", ln):
            out += " " + ln
        else:
            out += ln
    return out


# ----------------------------------------------------------------- XML build
def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# 見出しの装飾。frontmatter の heading_shading / heading_before_lines で有効化する。
# 既定は空文字なので、指定しない文書の出力はこれまでと一切変わらない。
HEAD_SHD = ""
HEAD_BEFORE = ""
# 本文の強調(**...**)の書体。frontmatter の bold_gothic で有効化する。
# 既定は空文字なので、指定しない文書の出力はこれまでと一切変わらない。
BOLD_GOTHIC = ""


def runs(text, gothic=False, shd=""):
    out = []
    for i, part in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
        if not part:
            continue
        bold = (i % 2 == 1)
        if gothic:
            fonts = '<w:rFonts w:hAnsi="ＭＳ ゴシック" w:hint="eastAsia"/>'
        elif bold and BOLD_GOTHIC:
            fonts = BOLD_GOTHIC
        else:
            fonts = ('<w:rFonts w:ascii="Times New Roman" w:eastAsia="ＭＳ 明朝"'
                     ' w:cs="Times New Roman" w:hint="eastAsia"/>')
        b = "<w:b/>" if (bold or gothic) else ""
        out.append(f'<w:r><w:rPr>{fonts}{b}<w:sz w:val="22"/>{shd}</w:rPr>'
                   f'<w:t xml:space="preserve">{esc(part)}</w:t></w:r>')
    return "".join(out)


def para(text, style, spacing):
    if style == "h":
        ppr = (f'<w:pPr><w:spacing {HEAD_BEFORE}w:line="240" w:lineRule="atLeast"/>'
               '<w:rPr><w:rFonts w:hAnsi="ＭＳ ゴシック"/><w:b/><w:sz w:val="22"/>'
               f'{HEAD_SHD}</w:rPr></w:pPr>')
        return f"<w:p>{ppr}{runs(text, gothic=True, shd=HEAD_SHD)}</w:p>"
    ind = ""
    if style == "b":
        ind = '<w:ind w:firstLineChars="100" w:firstLine="220"/>'
    elif style == "bl":
        ind = '<w:ind w:left="220" w:hangingChars="100" w:hanging="220"/>'
    elif style == "ref":
        ind = '<w:ind w:left="440" w:hangingChars="200" w:hanging="440"/>'
    ppr = (f'<w:pPr><w:spacing w:line="{spacing}" w:lineRule="atLeast"/>'
           f'{ind}<w:jc w:val="both"/>'
           '<w:rPr><w:rFonts w:ascii="Times New Roman" w:eastAsia="ＭＳ 明朝"'
           ' w:cs="Times New Roman"/><w:sz w:val="22"/></w:rPr></w:pPr>')
    return f"<w:p>{ppr}{runs(text)}</w:p>"


def png_size(path):
    with open(path, "rb") as f:
        if f.read(8) != b"\x89PNG\r\n\x1a\n":
            raise SystemExit(f"ERROR: not a PNG file: {path}")
        f.read(8)  # length + 'IHDR'
        return struct.unpack(">II", f.read(8))


def image_xml(rid, doc_pr_id, cx, cy, spacing):
    return (
        f'<w:p><w:pPr><w:spacing w:line="{spacing}" w:lineRule="atLeast"/>'
        '<w:jc w:val="center"/></w:pPr>'
        '<w:r><w:rPr><w:noProof/></w:rPr><w:drawing>'
        '<wp:inline distT="0" distB="0" distL="0" distR="0">'
        f'<wp:extent cx="{cx}" cy="{cy}"/><wp:effectExtent l="0" t="0" r="0" b="0"/>'
        f'<wp:docPr id="{doc_pr_id}" name="mdimg{doc_pr_id}"/>'
        '<wp:cNvGraphicFramePr>'
        '<a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/>'
        '</wp:cNvGraphicFramePr>'
        '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f'<pic:nvPicPr><pic:cNvPr id="{doc_pr_id}" name="mdimg{doc_pr_id}"/><pic:cNvPicPr/></pic:nvPicPr>'
        f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
        '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'
    )


def caption_xml(text, spacing):
    return (
        f'<w:p><w:pPr><w:spacing w:line="{spacing}" w:lineRule="atLeast"/>'
        '<w:jc w:val="center"/>'
        '<w:rPr><w:rFonts w:hAnsi="ＭＳ ゴシック"/><w:b/><w:sz w:val="22"/></w:rPr></w:pPr>'
        f'{runs(text, gothic=True)}</w:p>'
    )


# Greedy path capture so filenames may contain "(" and ")" -- common on Japanese
# Windows (e.g. "科研費申請(開拓).png"). Backtracking anchors on the LAST ")".
# キャプションに業績番号 ([4] など) を書けるよう、alt に ] を許す。
# 貪欲マッチ + 直後の "](" で境界を決める。パスは最後の ")" で閉じる。
IMG_RE = re.compile(r"^!\[(.*)\]\((.+)\)(?:\{width=(\d+)\})?\s*$")


def build_blocks(blocks, spacing, md_dir, images):
    """Convert markdown blocks to XML. Appends (path, rid_token) to images."""
    xml = []
    for block in blocks:
        lines = block.splitlines()
        first = lines[0].strip()
        m = IMG_RE.match(first)
        if m:
            caption, path, width = m.group(1), m.group(2), m.group(3)
            width_pt = int(width) if width else 450
            abs_path = os.path.normpath(os.path.join(md_dir, path))
            if not os.path.exists(abs_path):
                raise SystemExit(f"ERROR: image not found: {abs_path}")
            w_px, h_px = png_size(abs_path)
            cx = width_pt * EMU_PER_PT
            cy = int(cx * h_px / w_px)
            token = f"__RID_{len(images)}__"
            doc_pr_id = 9000 + len(images)
            images.append((abs_path, token))
            xml.append(image_xml(token, doc_pr_id, cx, cy, spacing))
            if caption.strip():
                xml.append(caption_xml(caption.strip(), spacing))
            continue
        if first.startswith("## "):
            xml.append(para(join_lines([l.lstrip("# ").strip() if i == 0 else l
                                        for i, l in enumerate(lines)]), "h", spacing))
        elif first.startswith("- "):
            # each "- " line is its own bullet paragraph; wrapped lines belong to previous bullet
            cur = None
            for ln in lines:
                if ln.strip().startswith("- "):
                    if cur:
                        xml.append(para("・" + join_lines(cur), "bl", spacing))
                    cur = [ln.strip()[2:]]
                elif cur is not None:
                    cur.append(ln)
            if cur:
                xml.append(para("・" + join_lines(cur), "bl", spacing))
        elif re.match(r"^\[\d+\]\s", first):
            xml.append(para(join_lines(lines), "ref", spacing))
        elif first.startswith("**["):
            xml.append(para(join_lines(lines), "bn", spacing))
        else:
            xml.append(para(join_lines(lines), "b", spacing))
    return "\n".join(xml)


# -------------------------------------------------------------- XML scanning
def element_ranges(xml, tag):
    """Yield (start, end) of <tag>...</tag> elements, handling same-tag nesting."""
    open_re = re.compile(r"<" + re.escape(tag) + r"[ >/]")
    close = "</" + tag + ">"
    i = 0
    while True:
        m = open_re.search(xml, i)
        if not m:
            return
        s = m.start()
        if xml[m.end() - 1] == "/" and xml[m.end()] == ">":  # self-closing <w:p/>
            yield (s, m.end() + 1)
            i = m.end() + 1
            continue
        depth, j = 1, m.end()
        while depth:
            mo = open_re.search(xml, j)
            mc = xml.find(close, j)
            if mc == -1:
                raise SystemExit(f"ERROR: unbalanced <{tag}>")
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


def strip_tags(seg):
    return re.sub(r"<[^>]*>", "", seg)


def find_anchor(xml, anchor, is_table, from_pos=0):
    tag = "w:tbl" if is_table else "w:p"
    for s, e in element_ranges(xml[from_pos:], tag):
        seg = xml[from_pos + s:from_pos + e]
        if anchor in strip_tags(seg):
            return (from_pos + s, from_pos + e)
    return None


def remove_instruction_textboxes(xml):
    n = 0
    while True:
        found = None
        for m in re.finditer(r"<mc:AlternateContent>", xml):
            e = xml.index("</mc:AlternateContent>", m.start()) + len("</mc:AlternateContent>")
            # run splits can break the marker string; compare tag-stripped text
            if DELETE_MARKER in strip_tags(xml[m.start():e]):
                found = (m.start(), e)
                break
        if not found:
            break
        xml = xml[:found[0]] + xml[found[1]:]
        n += 1
    return xml, n


def remove_fillers_between(xml, start, end):
    """Remove empty paragraphs in xml[start:end]. Returns (xml, removed_count)."""
    seg = xml[start:end]
    keep, removed, pos = [], 0, 0
    for s, e in element_ranges(seg, "w:p"):
        piece = seg[s:e]
        if (not strip_tags(piece).strip() and "<w:sectPr" not in piece
                and "<w:drawing" not in piece and "AlternateContent" not in piece):
            keep.append(seg[pos:s])
            removed += 1
        else:
            keep.append(seg[pos:e])
        pos = e
    keep.append(seg[pos:])
    return xml[:start] + "".join(keep) + xml[end:], removed


# ------------------------------------------------------------------ zip I/O
def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: python md2docx.py <content.md>")
    md_path = os.path.abspath(sys.argv[1])
    md_dir = os.path.dirname(md_path)
    with open(md_path, encoding="utf-8") as f:
        meta, body = parse_frontmatter(f.read())

    for key in ("template", "output"):
        if key not in meta:
            raise SystemExit(f"ERROR: frontmatter missing '{key}'")
    template = os.path.normpath(os.path.join(md_dir, meta["template"]))
    output = os.path.normpath(os.path.join(md_dir, meta["output"]))
    spacing = int(meta.get("line_spacing", "240"))
    global HEAD_SHD, HEAD_BEFORE, BOLD_GOTHIC
    if meta.get("heading_shading"):
        HEAD_SHD = (f'<w:shd w:val="{meta["heading_shading"]}"'
                    ' w:color="auto" w:fill="FFFFFF"/>')
    if meta.get("heading_before_lines"):
        bl = int(meta["heading_before_lines"])
        HEAD_BEFORE = f'w:beforeLines="{bl}" w:before="{int(bl * 3.6)}" '
    if str(meta.get("bold_gothic", "")).lower() in ("true", "1", "yes"):
        BOLD_GOTHIC = ('<w:rFonts w:ascii="Arial" w:eastAsia="ＭＳ ゴシック"'
                       ' w:hAnsi="Arial" w:cs="Arial" w:hint="eastAsia"/>')
    if not os.path.exists(template):
        raise SystemExit(f"ERROR: template not found: {template}")
    if os.path.abspath(template) == os.path.abspath(output):
        raise SystemExit("ERROR: template and output must differ (template must stay pristine)")

    zin = zipfile.ZipFile(template)
    xml = zin.read("word/document.xml").decode("utf-8")
    rels = zin.read("word/_rels/document.xml.rels").decode("utf-8")
    ctypes = zin.read("[Content_Types].xml").decode("utf-8")

    xml, n_boxes = remove_instruction_textboxes(xml)
    sections = split_sections(body)
    images = []

    for idx, (anchor, is_table, blocks) in enumerate(sections):
        rng = find_anchor(xml, anchor, is_table)
        if rng is None:
            raise SystemExit(f"ERROR: anchor not found: {anchor!r}"
                             + (" (| table)" if is_table else ""))
        content = build_blocks(blocks, spacing, md_dir, images)
        ins = rng[1]
        xml = xml[:ins] + "\n" + content + xml[ins:]
        content_end = ins + 1 + len(content)
        if idx + 1 < len(sections):
            nxt_anchor, nxt_table, _ = sections[idx + 1]
            nxt = find_anchor(xml, nxt_anchor, nxt_table, from_pos=content_end)
            if nxt:
                xml, n_fill = remove_fillers_between(xml, content_end, nxt[0])
                if n_fill:
                    print(f"section {idx + 1}: removed {n_fill} filler paragraphs before next anchor")
        print(f"section {idx + 1}: inserted after {anchor!r}")

    # register images
    used = [int(m) for m in re.findall(r'Id="rId(\d+)"', rels)]
    next_id = max(used) + 1 if used else 1
    media = []
    for i, (path, token) in enumerate(images):
        rid = f"rId{next_id + i}"
        name = f"media/mdimg{next_id + i}.png"
        rels = rels.replace("</Relationships>",
                            f'<Relationship Id="{rid}" '
                            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                            f'Target="{name}"/></Relationships>')
        xml = xml.replace(token, rid)
        media.append((f"word/{name}", path))
    if images and 'Extension="png"' not in ctypes:
        ctypes = ctypes.replace("</Types>",
                                '<Default Extension="png" ContentType="image/png"/></Types>')

    replaced = {"word/document.xml": xml.encode("utf-8"),
                "word/_rels/document.xml.rels": rels.encode("utf-8"),
                "[Content_Types].xml": ctypes.encode("utf-8")}
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = replaced.pop(item.filename, None)
            zout.writestr(item, data if data is not None else zin.read(item.filename))
        for name, data in replaced.items():
            zout.writestr(name, data)
        for arcname, path in media:
            zout.write(path, arcname)
    zin.close()

    print(f"OK: {output}")
    print(f"  sections={len(sections)} images={len(images)} textboxes_removed={n_boxes}")
    if "page_targets" in meta:
        print("NEXT: run fit_pages.ps1 -InPath <output> -OutPath <output> "
              f"-Targets \"{meta['page_targets']}\"")


if __name__ == "__main__":
    main()
