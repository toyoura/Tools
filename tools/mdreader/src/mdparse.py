"""Markdown (and LaTeX-flavoured Markdown) -> speakable chunks with line numbers.

Each chunk is a dict:
    {"i": index, "line": first source line, "end": last source line,
     "kind": "h1".."h6"|"p"|"li"|"quote"|"skip",
     "text": text shown in the UI, "say": text handed to the TTS engine (None = not spoken)}

Manuscripts written for a LaTeX venue are often kept in a .md file: no Markdown
headings at all, but \\section, \\ref, \\cite, % comments and figure/table
environments. Those are handled here too, because reading them out verbatim
makes the text unusable, and a stray % comment line silently merges into the
paragraph below it and shifts every line number in that paragraph.
"""
from __future__ import annotations

import re

FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})(.*)$")
HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
LIST = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
QUOTE = re.compile(r"^\s{0,3}>+\s?(.*)$")
HR = re.compile(r"^\s{0,3}(?:(?:-\s*){3,}|(?:\*\s*){3,}|(?:_\s*){3,})$")
TABLE = re.compile(r"^\s{0,3}\|")
FOOTNOTE = re.compile(r"^\s{0,3}\[\^[^\]]+\]:")
MATH_OPEN = re.compile(r"^\s{0,3}\$\$\s*$")

TEX_COMMENT = re.compile(r"^\s*%")
TEX_SECTION = re.compile(r"^\s*\\(section|subsection|subsubsection|paragraph)\*?\{(.*)\}\s*$")
TEX_BEGIN = re.compile(r"^\s*\\begin\{([A-Za-z*]+)\}")
TEX_ENV_LINE = re.compile(r"^\s*\\(begin|end)\{[A-Za-z*]+\}\s*$")
TEX_ITEM = re.compile(r"^\s*\\item\s*(.*)$")
TEX_CAPTION = re.compile(r"\\caption\{(.*)\}\s*$")
TEX_DOC_OPEN = re.compile(r"^\s*\\begin\{document\}")
TEX_DOC_CLOSE = re.compile(r"^\s*\\end\{document\}")
TEX_TITLE = re.compile(r"^\s*\\title\s*(\[[^\]]*\])?\s*\{(.*)\}\s*$")
TEX_INPUT = re.compile(r"^\s*\\(input|include)\s*\{([^}]*)\}")
# Commands whose braced argument is not prose. The argument can run over many
# lines (an IEEE \author block is easily fifty), so it is consumed by balance.
TEX_DROP_BLOCK = re.compile(
    r"^\s*\\(author|thanks|affil|address|IEEEauthorblock[A-Z]?|keywords|markboth"
    r"|pagestyle|thispagestyle|setcounter|renewcommand|newcommand|def)\b"
)
TEX_DROP_LINE = re.compile(
    r"^\s*\\(maketitle|bibliographystyle|bibliography|printbibliography|tableofcontents"
    r"|listoffigures|listoftables|newpage|clearpage|appendices|appendix|EOD|IEEEpeerreviewmaketitle)\b"
)

# Environments whose body is not prose. Their \caption is still read aloud.
TEX_SKIP_ENVS = {
    "figure", "figure*", "table", "table*", "tabular", "tabular*", "tabularx",
    "equation", "equation*", "align", "align*", "eqnarray", "gather",
    "verbatim", "lstlisting", "algorithm", "algorithmic", "minted",
    "thebibliography", "IEEEbiography", "IEEEbiographynophoto",
}
TEX_SECTION_LEVEL = {"section": 1, "subsection": 2, "subsubsection": 3, "paragraph": 4}

TERMS = "。．！？!?"
CLOSERS = "」』）)”\"'’】〉》"
MAX_LEN = 150

_PCT = "\x00pct\x00"


def _is_ascii_word(ch: str) -> bool:
    return ch.isascii() and (ch.isalnum() or ch in "-_/.")


def _latex_inline(s: str) -> str:
    """Strip LaTeX markup. Skipped entirely for lines with no LaTeX in them, so
    ordinary Markdown (braces, percent signs) is left alone."""
    if "\\" not in s and "``" not in s:
        return s
    s = s.replace(r"\%", _PCT)
    s = re.sub(r"%.*$", "", s)                      # trailing comment
    s = re.sub(
        r"\\(label|ref|eqref|cref|autoref|cite[a-z]*|includegraphics|vspace|hspace"
        r"|footnote|caption|index|nocite)\s*(\[[^\]]*\])?\s*\{[^{}]*\}",
        "", s,
    )
    for _ in range(3):  # nesting such as \textbf{\texttt{x}}
        s = re.sub(r"\\(textbf|textit|texttt|emph|textrm|textsf|mbox|text|bm)\{([^{}]*)\}", r"\2", s)
    s = re.sub(r"``([^`']*)''", r"\1", s)
    s = re.sub(r"`([^`']*)'", r"\1", s)
    s = re.sub(r"\\\\", " ", s)
    s = re.sub(r"\\[A-Za-z]+\*?\s*(\[[^\]]*\])?", "", s)   # any command left over
    s = re.sub(r"\\[^A-Za-z]", "", s)                      # \&, \_, ...
    s = s.replace("~", " ").replace("{", "").replace("}", "")
    return s.replace(_PCT, "%")


def clean_inline(s: str) -> str:
    """Strip markup, leaving text that reads naturally aloud."""
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = _latex_inline(s)
    s = re.sub(r"!\[\[[^\]]*\]\]", "", s)
    s = re.sub(r"\[\[([^\]|]+)\|?([^\]]*)\]\]", lambda m: m.group(2) or m.group(1), s)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"!\[[^\]]*\]\[[^\]]*\]", "", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", s)
    s = re.sub(r"\[\^[^\]]+\]", "", s)
    s = re.sub(r"`+([^`]*)`+", r"\1", s)
    s = re.sub(r"\$\$?[^$]*\$\$?", "数式", s)
    s = re.sub(r"<[^>]{1,80}>", "", s)
    s = re.sub(r"(\*\*\*|___)(.+?)\1", r"\2", s)
    s = re.sub(r"(\*\*|__)(.+?)\1", r"\2", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", s)
    s = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"\1", s)
    s = re.sub(r"~~(.+?)~~", r"\1", s)
    s = re.sub(r"^\s*\[[ xX]\]\s*", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _join(parts):
    """parts: [(line, cleaned_text)] -> (joined, [(offset, line)])"""
    out, marks = "", []
    for ln, s in parts:
        if not s:
            continue
        if out and _is_ascii_word(out[-1]) and _is_ascii_word(s[0]):
            out += " "
        marks.append((len(out), ln))
        out += s
    return out, marks


def _split_sentences(s: str):
    res, start, i = [], 0, 0
    while i < len(s):
        if s[i] in TERMS:
            j = i
            while j < len(s) and s[j] in TERMS:
                j += 1
            while j < len(s) and s[j] in CLOSERS:
                j += 1
            res.append((start, s[start:j]))
            start = i = j
            continue
        i += 1
    if start < len(s):
        res.append((start, s[start:]))
    return [(o, t) for o, t in res if t.strip()]


def _cap(off: int, txt: str, limit: int = MAX_LEN):
    """Break an over-long sentence at commas so highlighting stays fine-grained."""
    if len(txt) <= limit:
        return [(off, txt)]
    pieces, bstart, cut = [], 0, None
    for i, ch in enumerate(txt):
        if ch in "、，,":
            cut = i + 1
        if i - bstart >= limit and cut and cut > bstart:
            pieces.append((off + bstart, txt[bstart:cut]))
            bstart, cut = cut, None
    pieces.append((off + bstart, txt[bstart:]))
    return [(o, t) for o, t in pieces if t.strip()]


def _consume_braces(lines, i):
    r"""Advance past a command and every braced argument that follows it, even
    when they span lines. \author{...} has one group and \markboth{...}{...}
    has two; an IEEE author block runs to fifty lines. Returns the index of the
    first line after the command."""
    n = len(lines)
    depth, seen = 0, False
    end = i  # line on which the most recent group closed
    while i < n:
        # A trailing % continues the command onto the next line, so comments
        # have to come off before the braces are counted.
        line = re.sub(r"(?<!\\)%.*$", "", lines[i])
        for ch in line:
            if ch == "{":
                depth += 1
                seen = True
            elif ch == "}" and seen:
                depth -= 1
                if depth == 0:
                    end = i
            elif seen and depth == 0 and not ch.isspace():
                return end + 1  # a new statement started: stop before it
        i += 1
        if not seen:
            return i  # no group opened at all
        if depth == 0:
            nxt = re.sub(r"(?<!\\)%.*$", "", lines[i]).lstrip() if i < n else ""
            if not nxt.startswith("{"):
                return end + 1
    return n


def _line_of(marks, offset):
    ln = marks[0][1] if marks else 1
    for o, l in marks:
        if o <= offset:
            ln = l
        else:
            break
    return ln


class _Builder:
    def __init__(self):
        self.chunks = []

    def skip(self, line, label, end=None):
        self.chunks.append(
            {"line": line, "end": end or line, "kind": "skip", "text": label, "say": None}
        )

    def block(self, kind, parts, tail="。"):
        joined, marks = _join(parts)
        if not joined:
            return
        for off, sent in [p for o, t in _split_sentences(joined) for p in _cap(o, t)]:
            disp = sent.strip()
            if not disp:
                continue
            say = disp if disp[-1] in TERMS else disp + tail
            self.chunks.append({
                "line": _line_of(marks, off),
                "end": _line_of(marks, off + len(sent) - 1),
                "kind": kind,
                "text": disp,
                "say": say,
            })


def parse(text: str):
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    n = len(lines)
    b = _Builder()
    para: list = []
    i = 0

    def flush():
        nonlocal para
        if para:
            b.block("p", para)
            para = []

    if n and lines[0].strip() == "---":
        for j in range(1, n):
            if lines[j].strip() in ("---", "..."):
                b.skip(1, "［フロントマター " + str(j + 1) + " 行］", j + 1)
                i = j + 1
                break

    # A standalone .tex file is mostly preamble: \documentclass, package loads
    # and macro definitions, none of it prose. Start at \begin{document}.
    for j in range(i, n):
        if TEX_DOC_OPEN.match(lines[j]):
            b.skip(i + 1, "［プリアンブル " + str(j - i + 1) + " 行］", j + 1)
            i = j + 1
            break

    while i < n:
        raw = lines[i]
        s = raw.strip()

        if not s:
            flush()
            i += 1
            continue

        # A LaTeX comment line is invisible to the reader. Do not flush: a comment
        # inside a paragraph must not split it, and it must not become the line
        # number of the sentence that follows.
        if TEX_COMMENT.match(raw):
            i += 1
            continue

        if TEX_DOC_CLOSE.match(raw):
            flush()
            if i + 1 < n:
                b.skip(i + 1, "［end{document} 以降 " + str(n - i) + " 行］", n)
            break

        m = TEX_TITLE.match(raw)
        if m:
            flush()
            b.block("h1", [(i + 1, clean_inline(m.group(2)))])
            i += 1
            continue

        m = TEX_INPUT.match(raw)
        if m:
            flush()
            # The prose lives in another file; say which one rather than drop it.
            b.skip(i + 1, "［別ファイル " + m.group(2) + "］")
            i += 1
            continue

        if TEX_DROP_BLOCK.match(raw):
            flush()
            start = i
            i = _consume_braces(lines, i)
            b.skip(start + 1, "［著者情報など " + str(i - start) + " 行］", i)
            continue

        if TEX_DROP_LINE.match(raw):
            flush()
            i += 1
            continue

        m = FENCE.match(raw)
        if m:
            flush()
            fence = m.group(1)[0] * 3
            lang = m.group(2).strip()
            start = i
            i += 1
            while i < n and not re.match(r"^\s{0,3}" + re.escape(fence), lines[i]):
                i += 1
            i = min(i + 1, n)
            label = "［コード" + (" " + lang if lang else "") + " " + str(i - start) + " 行］"
            b.skip(start + 1, label, i)
            continue

        m = TEX_BEGIN.match(raw)
        if m:
            env = m.group(1)
            if env in TEX_SKIP_ENVS:
                flush()
                start = i
                depth = 0
                caption = None
                while i < n:
                    if re.match(r"^\s*\\begin\{" + re.escape(env) + r"\}", lines[i]):
                        depth += 1
                    elif re.match(r"^\s*\\end\{" + re.escape(env) + r"\}", lines[i]):
                        depth -= 1
                        if depth == 0:
                            i += 1
                            break
                    if caption is None:
                        cm = TEX_CAPTION.search(lines[i])
                        if cm:
                            caption = (i + 1, clean_inline(cm.group(1)))
                    i += 1
                b.skip(start + 1, "［" + env + " 環境 " + str(i - start) + " 行］", i)
                if caption and caption[1]:
                    b.block("quote", [caption])
                continue
            if TEX_ENV_LINE.match(raw):  # itemize, enumerate, ... keep the body
                flush()
                i += 1
                continue

        if TEX_ENV_LINE.match(raw):  # a bare \end{...}
            flush()
            i += 1
            continue

        m = TEX_SECTION.match(raw)
        if m:
            flush()
            lvl = TEX_SECTION_LEVEL.get(m.group(1), 3)
            b.block("h" + str(lvl), [(i + 1, clean_inline(m.group(2)))])
            i += 1
            continue

        m = TEX_ITEM.match(raw)
        if m:
            flush()
            b.block("li", [(i + 1, clean_inline(m.group(1)))])
            i += 1
            continue

        if MATH_OPEN.match(raw):
            flush()
            start = i
            i += 1
            while i < n and not MATH_OPEN.match(lines[i]):
                i += 1
            i = min(i + 1, n)
            b.skip(start + 1, "［数式ブロック " + str(i - start) + " 行］", i)
            continue

        if HR.match(raw):
            flush()
            i += 1
            continue

        if FOOTNOTE.match(raw):
            flush()
            b.skip(i + 1, "［脚注］")
            i += 1
            continue

        if TABLE.match(raw):
            flush()
            start = i
            while i < n and TABLE.match(lines[i]):
                i += 1
            b.skip(start + 1, "［表 " + str(i - start) + " 行］", i)
            continue

        m = HEADING.match(raw)
        if m:
            flush()
            b.block("h" + str(len(m.group(1))), [(i + 1, clean_inline(m.group(2)))])
            i += 1
            continue

        m = QUOTE.match(raw)
        if m:
            flush()
            parts = []
            while i < n and QUOTE.match(lines[i]):
                parts.append((i + 1, clean_inline(QUOTE.match(lines[i]).group(1))))
                i += 1
            b.block("quote", parts)
            continue

        m = LIST.match(raw)
        if m:
            flush()
            parts = [(i + 1, clean_inline(m.group(3)))]
            i += 1
            while (i < n and lines[i].strip() and not LIST.match(lines[i])
                   and not HEADING.match(lines[i]) and not FENCE.match(lines[i])
                   and not TEX_COMMENT.match(lines[i])
                   and lines[i].startswith((" ", "\t"))):
                parts.append((i + 1, clean_inline(lines[i])))
                i += 1
            b.block("li", parts)
            continue

        para.append((i + 1, clean_inline(raw)))
        i += 1

    flush()

    for k, c in enumerate(b.chunks):
        c["i"] = k
    return b.chunks
