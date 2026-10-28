---
name: docx-md-roundtrip
description: 様式付きWord文書(科研費申請書の様式S-13/S-41など、指示書き・節区切り・ページ数制限を持つdocx)を、レイアウトを崩さずにMarkdown経由で編集するスキル。(1)docx→Markdown読み取り、(2)Markdown編集、(3)Markdown→docx反映(様式構造とページ割りを維持、Word COMで自動調整)、図(PNG)の挿入までを行う。"申請書を更新して" "docxをMarkdownにして" "mdの内容をdocxに反映して" "様式を崩さずに編集して" "s-13を書き換えて" など、様式付きdocxの作成・編集・往復変換の依頼では必ずこのスキルを使うこと。様式のない新規Word文書の作成には anthropic-skills:docx を使う。
compatibility: Windows + Microsoft Word (COM) + Python 3。ページ調整とPDF検証にWordを使用する。
---

# docx-md-roundtrip: 様式付きdocxのMarkdown往復編集

科研費申請書のような「様式」docx (指示書きテーブル・節ごとのページ数制限・空行で確保されたページ構造を持つ文書) を、
**Markdownを編集の起点(source of truth)** にして安全に編集する。

原理: 記入済みdocxを直接いじるのではなく、**毎回まっさらな様式テンプレートに Markdown の内容を流し込んで再構築**する。
これにより書式の劣化が蓄積せず、何度編集しても崩れない。ページ割りは最後に Word COM で節ごとに自動調整する。

## ファイル構成の前提

```
<申請書フォルダ>/
├── template/          # まっさらな様式docx (これが再構築の土台。絶対に編集しない)
│   └── s-13.docx
├── s-13.md            # 編集の起点となるMarkdown (このスキルが生成・管理)
├── s-13.docx          # 出力 (毎回上書き再生成される)
└── figure1.png        # 挿入する図 (あれば)
```

- `template/` に空の様式がない場合は、記入済みdocxのコピーをtemplateにしてはいけない (内容が二重になる)。
  ユーザーに空の様式ファイルの場所を確認するか、配布元様式の入手を依頼する。

## ワークフロー

### A. 初回セットアップ (docx → Markdown)

1. **基準ページ構成を取得** (テンプレートの節が何ページ目から始まるか):
   ```powershell
   powershell -ExecutionPolicy Bypass -File <skill>/scripts/get_baseline.ps1 -Path <絶対パス>\template\s-13.docx
   ```
   出力の `SECTION n starts page p` から `page_targets: "2=6,3=8,4=9"` の形式を組み立てる (節1は常にp1なので省略)。

2. **記入済みdocxがある場合はテキストを抽出**:
   ```powershell
   $env:PYTHONUTF8=1; python <skill>/scripts/docx2md.py <絶対パス>\s-13.docx > draft.md
   ```
   出力は「分類済みの段落の羅列」であり、そのままでは使えない。これを素材に次を行う:
   - 様式指示表 (`<!-- 様式表: ... -->` コメント) は削除する (テンプレート側に既にある)
   - 内容段落を `# section:` ブロックに振り分ける (アンカーの選び方は後述)

3. **Markdownを組み立てる**。書式仕様は [references/format.md](references/format.md) を必ず読むこと。
   最低限の骨格:
   ```markdown
   ---
   template: template/s-13.docx
   output: s-13.docx
   page_targets: "2=6,3=8,4=9"
   line_spacing: 220
   ---

   # section: （概要）

   本文の段落...

   # section: ５頁以内で記述すること | table

   ## (1) 見出し
   ...
   ```

4. **検証**: 一度ビルドしてPDF化し、元のdocxと見比べて内容の欠落がないか確認する (下記C参照)。

### B. 編集反映 (Markdown → docx)

Markdownを編集したら、次の2コマンドで反映する。md2docx は docx をテンプレートから作り直すので、
Word 側の手修正は消える。実行前に docx の更新時刻を前回ビルドと比べ、新しければ先に D で md へ取り込む。
上書きする前に `backup/` へ `.bak_日時` のコピーを残す:

```powershell
# 1. テンプレートに内容を流し込んでdocxを再構築 (図の挿入もここで行われる)
$env:PYTHONUTF8=1; python <skill>/scripts/md2docx.py <絶対パス>\s-13.md

# 2. Word COMで節ごとのページ境界を基準に合わせる (末尾の空行を増減)
powershell -ExecutionPolicy Bypass -File <skill>/scripts/fit_pages.ps1 `
  -InPath <絶対パス>\s-13.docx -OutPath <絶対パス>\s-13.docx -Targets "2=6,3=8,4=9"
```

fit_pages が `OVERFLOW` を報告したら、その節の内容がページ制限を超えている。Markdownを削って再実行する。

### C. 検証 (必ず行う)

反映後は必ずPDF化してページ構成と見た目を確認し、確認した旨とスクリーンショットに相当する情報をユーザーに報告する:

```powershell
powershell -ExecutionPolicy Bypass -File <skill>/scripts/topdf.ps1 -InPath <docx絶対パス> -OutPath <pdf絶対パス>
python -c "import fitz; d=fitz.open(r'<pdf>'); [d[i].get_pixmap(dpi=100).save(rf'<scratch>\pg{i+1}.png') for i in range(len(d))]; print(len(d))"
```

生成したページ画像をReadで目視確認する。チェック項目:
- 総ページ数と各節の開始ページが `page_targets` と一致しているか (fit_pagesの出力でも確認できる)
- 指示書き (各節冒頭の枠) が保存されているか
- 図が意図した位置・サイズで入っているか
- 見出し・太字・箇条書きのスタイルが揃っているか

### D. docx を手直ししたあとの取り込み (docx → md)

ユーザーが Word で直接書き直すことは普通に起きる。**md が source of truth なので、必ず md へ戻す。**

```powershell
$env:PYTHONUTF8=1
python <skill>/scripts/docx2md_sync.py <s-13.docx> <s-13.md> <template/s-13.docx>
# → s-13.md.new が出る。差分を見てから差し替える
```

`docx2md.py` (段落の羅列) とは別物で、こちらは**フロントマター・冒頭の非出力領域・`# section:` 行・画像行を
そのまま保ったまま本文だけ入れ替える**。

取り込み後は次の2つを必ず確認する。

1. **本文の取りこぼしがゼロか** — docx の全段落(様式の指示書きを除く)が md に入っているかを突き合わせる。
   箇条書きは docx 側が `・`、md 側が `- ` なので、比較時に正規化する
2. **往復ビルドの残差** — md → docx し直して元の docx と比べる。残差が「見出し末尾の余白」だけなら正常

よくある副作用(いずれも取り込み後に直す):

- **図キャプションの二重化** — docx 側でキャプション文を変えると md の `![alt]` と一致しなくなり、
  独立段落として重複する。docx 側の文言を alt に畳む
- **読点だけを囲む空の強調** (`**、**`) — Word のラン分割の副産物。除去する
- **強調の内側末尾の空白** (`**[ラベル] **`) — 空白を強調の外へ出す

### E. 図を壊さずに本文だけ反映 (md → docx)

図を Word で位置・サイズ調整したあとは、**md2docx で再ビルドしてはいけない**(手調整が消える)。
既存 docx を土台に本文段落だけを差し替える。

```powershell
# 1. md から参照用 docx を作る (output: を一時名にしたコピーを使う)
sed 's|^output: .*|output: _ref.docx|' s-13.md > _ref.md
$env:PYTHONUTF8=1; python <skill>/scripts/md2docx.py _ref.md

# 2. 差分を確認してから当てる
python <skill>/scripts/patch_body.py s-13.docx _ref.docx          # dry-run
python <skill>/scripts/patch_body.py s-13.docx _ref.docx --apply

# 3. 頁を合わせ直す (空段落だけを増減するので図には影響しない)
powershell -ExecutionPolicy Bypass -File <skill>/scripts/fit_pages.ps1 `
  -InPath s-13.docx -OutPath s-13.docx -Targets "2=6,3=8,4=9"
```

反映後は図の `<wp:extent>` と `word/media/` のバイト数が変わっていないことを確認して報告する。

**書体だけの変更は patch_body.py では入らない**(文字列比較のため)。`bold_gothic` を後から有効にした
場合などは、rFonts を直接置換する。

### F. ページ調整の実務

`fit_pages.ps1` が `OVERFLOW` を出したら内容を削る。削る量は次の手順で決める。

1. `lines_per_page.ps1` で実測する。**あふれたページの行数がそのまま削るべき量**
   (例: `p6 lines=2` なら2行 ≒ 45字)
2. 1行あたりの文字数は様式による(本文22pt行送りで23字程度)。ただし見出し・図・箇条書きで変わるので、
   字数はあくまで当たりを付けるためのもの
3. 削って → 参照docxを作り直して → patch_body → fit_pages → 再測定、を繰り返す。**1回で当てようとしない**

削る先は「内容を減らす」のではなく「**二重に言っている箇所を1回にする**」を優先する。
申請書は同じ主張が概要・本文・研究方法に3回出てくることが多く、たいていそこで足りる。

## 図の挿入

Markdown内に画像行を書くと、その位置に中央揃えで挿入され、直後にキャプション段落が付く:

```markdown
![図1　研究の全体像](figure1.png){width=450}
```

- `width` はポイント単位。A4縦・余白25mmの様式なら本文幅は約453pt (=約16cm) なので、全幅なら450が目安
- 図中の文字は印刷時に9〜11ptになるように作る。幅1000pxでSVGを設計するなら font-size 20〜24px (詳細は
  ponchie-generator スキル側のメモ参照)。PNGは印刷品質のため3倍解像度で用意する
- キャプションは「図N　タイトル」の形式で画像行の `[]` 内に書く

## 落とし穴 (重要)

- **PYTHONUTF8=1 を必ず付ける**。日本語Windowsではcp932でPythonのファイル読み書きが壊れる
- **docx2md.py の出力をPowerShellの `>` でファイルにリダイレクトしない**。コンソールのレガシーエンコーディングを経由して文字化けする。
  `subprocess.run(..., capture_output=True, encoding="utf-8")` の結果を Python 側で `open(path, "w", encoding="utf-8")` に書くか、
  Write ツールでファイルを作る
- **PowerShellスクリプトに日本語を書くならUTF-8 BOM付きで保存**する。同梱のps1はASCIIのみなのでそのまま動く
- Word COMのページ番号 (`Information(3)`) は**再計算しないと古い値を返す**。同梱の fit_pages.ps1 は
  毎回 `Repaginate()` を呼んでいるので、独自スクリプトを書く場合も必ず倣うこと
- 様式の「このテキストボックスごと削除すること」という指示書きテキストボックスは md2docx が自動削除する
- 様式に「空白の頁が生じても削除しないこと」とある通り、**節の総ページ数は変えない**。内容が少ないときは
  fit_pages が空行を足して埋める。これが `page_targets` の役割
- Wordが起動中でもCOMは動くが、対象ファイルをWordで開いたままにしない (保存競合する)

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| md2docx が「anchor not found」 | アンカー文字列が様式内の表記と一字一句一致しているか確認 (全角空白・句読点に注意)。`| table` の要否も確認 |
| fit_pages が OVERFLOW | その節の内容過多。Markdownを削るか、行間・図サイズを見直す |
| 反映後に書式が崩れて見える | template/ を編集してしまっていないか確認。templateは常に空の様式に保つ |
| 図が粗い | PNGを3倍解像度で再生成 (Edge headless: `--force-device-scale-factor=3`) |

詳細な書式仕様・スクリプトの引数は [references/format.md](references/format.md) を参照。
