# Markdown書式仕様 (docx-md-roundtrip)

## フロントマター

```yaml
---
template: template/s-13.docx   # 再構築の土台となる空の様式 (mdファイルからの相対パス)
output: s-13.docx              # 出力docx (相対パス)。毎回上書きされる
page_targets: "2=6,3=8,4=9"    # 節番号=開始ページ。get_baseline.ps1 でテンプレートから取得した値
line_spacing: 220              # 本文の行送り (twips)。様式の空行段落の spacing に合わせる (220 or 240 が多い)

# --- 以下は任意。書かなければ従来どおりの出力になる (既定はすべて無効) ---
heading_shading: pct15         # 見出しに網掛けを掛ける (Word の「網かけ」15%相当)
heading_before_lines: 50       # 見出しの前アキ (0.5行 = 50)。w:beforeLines に入る
bold_gothic: true              # 本文の **強調** をＭＳゴシック+太字にする (既定は明朝+太字)
---
```

任意オプションは、様式や好みに合わせて後から足せるように**オプトイン**にしてある。
指定しない文書の出力はこれまでと1バイトも変わらない。追加するときもこの方式を守ること
(既定を変えると、過去の申請書を再ビルドしたときに見た目が変わってしまう)。

| オプション | 効果 | 生成されるXML |
|---|---|---|
| `heading_shading` | 見出しの網掛け | `<w:shd w:val="pct15" w:color="auto" w:fill="FFFFFF"/>` |
| `heading_before_lines` | 見出しの前アキ | `<w:spacing w:beforeLines="50" w:before="180" .../>` |
| `bold_gothic` | 強調をゴシック化 | `<w:rFonts w:hAnsi="ＭＳ ゴシック" w:cs="Times New Roman" w:hint="eastAsia"/>` |

`bold_gothic` の書体指定は、Word で手動でＭＳゴシックを当てたときに Word が書く形と同じにしてある。
手編集と混在しても差が出ない。

`line_spacing` の調べ方: テンプレートの document.xml 内の空行段落 `<w:spacing w:line="220" ...>` を見る。
迷ったら 240。ページ数はグリッド (docGrid) 支配なのでどちらでも大きくは変わらない。

## セクション区切りとアンカー

`# section: <アンカー> [| table]` の行で「様式内のどこに内容を流し込むか」を指定する。

- `# section: （概要）` — 「（概要）」という文字列を含む**段落**の直後に挿入
- `# section: ５頁以内で記述すること | table` — その文字列を含む**表**(指示書きの枠)の直後に挿入

アンカー選定のコツ:
- 様式内で一意な文字列を選ぶ (「１頁以内で記述すること」は複数の節に現れがち。節固有の指示文を使う)
- 見出し段落そのもの (「（本文）」等) か、指示書き表の中の文言 (この場合 `| table`) を使う
- 文字列は様式の表記そのまま (全角括弧・全角空白を含めて) 書く

連続するセクションの間にある空行段落は自動で除去される (内容が入るぶん詰める)。
節末尾の空行は fit_pages.ps1 がページ合わせで増減するので気にしなくてよい。

## 段落の書式

空行で段落を区切る。段落内の改行は連結される (日本語は空白なし、英数字間は空白1つ)。

| Markdown | docxでの見た目 |
|---|---|
| `## (1) 見出し` | ＭＳゴシック太字の見出し段落 |
| 通常の段落 | 明朝体・1字下げ・両端揃え |
| `**[ラベル]** 本文...` で始まる段落 | 字下げなし段落 (太字ラベル書き出し) |
| `- 項目` | 「・項目」のぶら下げインデント箇条書き |
| `[1] 著者: 題名...` | 文献リスト用の深いぶら下げインデント |
| `**太字**` (段落内) | 太字 (インライン) |
| `![図1　キャプション](fig.png){width=450}` | 中央揃えの画像+ゴシック太字キャプション |

注意:
- 段落先頭の「・」は `- ` 記法が自動で付けるので書かない
- 様式が求める最低フォントサイズ (11pt) は本文スタイル側で保証される。mdでフォントサイズは指定しない
- 表・複雑なレイアウトは未対応。必要なら図 (PNG) にして挿入する

## サンプル

```markdown
---
template: template/s-13.docx
output: s-13.docx
page_targets: "2=6,3=8,4=9"
line_spacing: 220
---

# section: （概要）

本研究の目的は...である。**中核概念**を構築する。

# section: （本文）

## (1) 学術的背景

**[背景]** 織物は...

- **課題1**: ...
- **課題2**: ...

![図1　研究の全体像](figure1.png){width=450}

## (2) 目的

...

# section: 実行可能性を示すため | table

## (1) これまでの研究活動

[1] M. Toyoura, et al.: Paper Title, Journal, Vol.1, pp.1-10, 2026.
```

## スクリプトの引数

### scripts/md2docx.py
```
$env:PYTHONUTF8=1; python md2docx.py <content.md絶対パス>
```
- テンプレートを読み、指示テキストボックス除去 → 内容挿入 → セクション間空行除去 → 画像埋め込み → output に書き出し
- 挿入結果のサマリ (セクション数・画像数) を表示する。エラー時はアンカー名を表示する

### scripts/fit_pages.ps1
```
powershell -ExecutionPolicy Bypass -File fit_pages.ps1 -InPath <in.docx> -OutPath <out.docx> -Targets "2=6,3=8,4=9"
```
- 各節の末尾の空段落を増減して、次節の開始ページを Targets に合わせる (Word COM、Repaginate込み)
- 空段落が尽きても収まらない場合は `SECTION n: OVERFLOW` を出力 (内容の削減が必要)
- InPath と OutPath は同じでよい (上書き)

### scripts/get_baseline.ps1
```
powershell -ExecutionPolicy Bypass -File get_baseline.ps1 -Path <template.docx>
```
- テンプレートの総ページ数と各節の開始ページを表示。page_targets の値はここから作る

### scripts/topdf.ps1
```
powershell -ExecutionPolicy Bypass -File topdf.ps1 -InPath <in.docx> -OutPath <out.pdf>
```
- Word COMでPDFにエクスポート (検証用)

### scripts/docx2md.py
```
$env:PYTHONUTF8=1; python docx2md.py <in.docx>
```
- 記入済みdocxの段落を分類してMarkdown風に標準出力へ書き出す (初回インポートの素材)
- 様式の表は `<!-- 様式表: ... -->`、節区切りは `<!-- 改セクション -->` コメントになる
- **出力はそのままmdとして使えない**。アンカー指定・フロントマターの付与はClaudeが行う

### scripts/docx2md_sync.py

```
python docx2md_sync.py <filled.docx> <current.md> <template.docx>
```

**docx を Word で手直ししたあと、その内容を md に取り込む**ためのもの。`docx2md.py` が段落の羅列を
吐くだけなのに対し、こちらは既存 md の構造を保ったまま本文だけ差し替えた `<current.md>.new` を書く。

保つもの: フロントマター、最初の `# section:` より前の領域(提出用の別欄など)、`# section:` 行、画像行。
復元するもの: `<w:b/>` から `**強調**`、pPr から見出し(`## `)・箇条書き(`- `)・文献(`[N] `)の区別。
除外するもの: テンプレートに同じ文字列がある段落(様式の指示書き)。

取り込み後は必ず往復ビルドで検証する。残差が「見出し末尾の余白」だけなら正常
(網掛けを行末まで伸ばすために Word 側で入れた空白であり、md では表現しない)。

### scripts/patch_body.py

```
python patch_body.py <target.docx> <reference.docx>            # dry-run
python patch_body.py <target.docx> <reference.docx> --apply
```

**図を Word で調整済みの docx に、本文の変更だけを入れる**ためのもの。md2docx で再ビルドすると
図の手調整が失われるので、既存 docx を土台に本文段落のランだけを差し替える。

`<reference.docx>` は md から作った出力(フロントマターの `output:` を一時名に変えてビルドする)。

保つもの: 図を含む段落、頁調整用の空段落、段落書式(pPr)、見出しの網掛け・改頁マーカー。

**文字列比較なので、書体だけの変更は検出しない。** 書体を変えるときは md2docx で再ビルドするか、
rFonts を直接置換する。

### scripts/lines_per_page.ps1

```
powershell -ExecutionPolicy Bypass -File lines_per_page.ps1 -Path <docx>
```

ページごとの実際の行数と文字数を出す。**fit_pages.ps1 の超過行数は図の高さを数えない**ので、
あと何行削ればよいかを知りたいときはこちらで実測する。あふれ量が一目で分かる
(例: `p6 lines=2` なら次ページに2行だけこぼれている)。

### scripts/measure_sections.ps1

```
powershell -ExecutionPolicy Bypass -File measure_sections.ps1 -Path <docx> -Targets "2=6,3=8,4=9"
```

節ごとに「割り当て最終ページ」を超えた行数を出す。どの欄があふれているかの切り分け用。

**注意: 最終節の判定は当てにならない。** 最終節が2ページ以上を割り当てられている様式
(S-41-2 の人権欄など)では、常に超過があるように見える。総ページ数で判断すること。

## docx の XML を直接いじるときの落とし穴

自作スクリプトで document.xml を触るときに実際に踏んだもの。

- **`<w:t[^>]*>` は `<w:tabs>` にマッチする。** タブ設定を持つ段落の中身が壊れて読まれる。
  必ず `<w:t(?: [^>]*)?>` と書く(`<w:t` の次が `>` か半角空白のときだけ通す)
- **`<w:r>` だけを探すと、属性付きのランを取りこぼす。** Word が編集すると
  `<w:r w:rsidRPr="...">` になる。`<w:r[ >]` で探す
- **空段落を差分に含めない。** fit_pages が入れた頁調整用の空段落を「不足」と判定して挿入すると、
  頁割りが壊れる。段落を突き合わせる前に空段落を除外する
- **Word COM のページ番号は `Repaginate()` を呼ぶまで古い値を返す**(同梱スクリプトは毎回呼んでいる)
- **図を含む段落には触れない。** `<w:drawing>` を含む段落を検出したら処理を中止する安全弁を入れておく
