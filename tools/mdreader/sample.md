# MdReader の試し読み

## Abstract

This file is a short sample for MdReader. Japanese sentences are read by a Japanese voice, and English sentences like this one by an English voice.

## はじめに

MdReader は、Markdown の原稿を1文ずつ読み上げる。読んでいる文は画面で色が付き、クリックするとそこから読み直す。

原稿を目で追うだけでは、主語のねじれや同じ語の繰り返しを見落としやすい。耳で聞くと、こうした引っかかりに気づける。

## 読まないもの

コードブロックと表は灰色で表示し、読み飛ばす。

```python
print("ここは読まない")
```

| 要素 | 扱い |
|---|---|
| 見出し・段落 | 読む |
| コード・表 | 飛ばす |

インライン数式 $E = mc^2$ は「数式」と読む。

## おわりに

[リンク](https://example.com) は表示テキストだけを読む。
