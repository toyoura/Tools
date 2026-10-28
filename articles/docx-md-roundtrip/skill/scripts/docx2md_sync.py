# -*- coding: utf-8 -*-
"""docx の本文を md へ取り込む。frontmatter・冒頭ブロック・section マーカー・画像行は md のものを保つ。
太字は <w:b/> から ** ** を復元。見出しは pPr の網掛け/ゴシックで判定して '## ' を付ける。"""
import io, re, sys, zipfile, pathlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DOCX = pathlib.Path(sys.argv[1])
MD   = pathlib.Path(sys.argv[2])
TPL  = pathlib.Path(sys.argv[3])

def para_list(path):
    x = zipfile.ZipFile(path).read('word/document.xml').decode('utf-8')
    out = []
    for m in re.finditer(r'<w:p[ >].*?</w:p>', x, re.S):
        seg = m.group(0)
        if '<mc:AlternateContent>' in seg:
            continue
        if '<w:drawing>' in seg:
            out.append(('IMG', '')); continue
        ppr = re.search(r'<w:pPr>.*?</w:pPr>', seg, re.S)
        pxml = ppr.group(0) if ppr else ''
        body = seg[ppr.end():] if ppr else seg
        buf = ''
        for r in re.finditer(r'<w:r[ >](.*?)</w:r>', body, re.S):
            rs = r.group(1)
            t = ''.join(re.findall(r'<w:t(?: [^>]*)?>(.*?)</w:t>', rs, re.S))
            if not t: continue
            t = t.replace('&amp;','&').replace('&lt;','<').replace('&gt;','>')
            rpr = re.search(r'<w:rPr>(.*?)</w:rPr>', rs, re.S)
            b = bool(rpr and '<w:b/>' in rpr.group(1))
            buf += ('**'+t+'**') if b else t
        buf = buf.replace('****','').rstrip()
        if not buf.strip(): continue
        kind = 'H' if ('ＭＳ ゴシック' in pxml and '<w:b/>' in pxml) else \
               ('BL' if 'w:hangingChars="100"' in pxml else
                ('REF' if 'w:hangingChars="200"' in pxml else 'P'))
        out.append((kind, buf))
    return out

tpl = {re.sub(r'\s|\*','',t) for k,t in para_list(TPL) if t}
doc = [(k,t) for k,t in para_list(DOCX)]

md = MD.read_text(encoding='utf-8')
m0 = re.search(r'(?m)^#\s*section:', md)
head = md[:m0.start()]
markers = re.findall(r'(?m)^#\s*section:\s*(.+?)\s*$', md)
imgs = re.findall(r'(?m)^!\[.*\]\(.+?\)(?:\{width=\d+\})?\s*$', md)

# docx を section マーカーで区切る
groups, cur, gi = [], [], -1
for k,t in doc:
    key = re.sub(r'\s|\*','',t)
    hit = next((i for i,a in enumerate(markers) if re.sub(r'\s|\*','',a.split('|')[0]) in key), None)
    if hit is not None and hit == gi+1:
        if gi >= 0: groups.append(cur)
        cur, gi = [], hit
        continue
    if gi < 0: continue
    if key in tpl: continue          # 様式の指示書きは除外
    cur.append((k,t))
groups.append(cur)

out = [head.rstrip('\n'), '']
ii = 0
for i, mk in enumerate(markers):
    out.append(f'# section: {mk}'); out.append('')
    for k,t in groups[i]:
        if k == 'IMG':
            out.append(imgs[ii] if ii < len(imgs) else '![](MISSING)')
            cap = re.match(r'!\[(.*)\]\(', imgs[ii]).group(1) if ii < len(imgs) else ''
            skip_cap = re.sub(r'\s|\*','',cap); ii += 1
            out.append(''); last_img_cap = skip_cap; continue
        elif re.sub(r'\s|\*','',t) == locals().get('last_img_cap',''):
            last_img_cap = None; continue
        elif k == 'H':   out.append('## ' + t.replace('**','').strip())
        elif k == 'BL':  out.append('- ' + t.lstrip('・'))
        else:            out.append(t)
        out.append('')
new = '\n'.join(out).rstrip('\n') + '\n'
new = re.sub(r'\n{3,}', '\n\n', new)
pathlib.Path(str(MD) + '.new').write_text(new, encoding='utf-8')
print('段落数:', [len(g) for g in groups], ' 画像:', ii, '/', len(imgs))
print('出力:', str(MD) + '.new')
