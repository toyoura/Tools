// Prompt for the reply draft. Edit SYSTEM to change how drafts read.

export const POLICIES = [
  { value: "", label: "指定なし (元メールに合わせる)", text: "" },
  { value: "accept", label: "引き受ける・承諾する", text: "依頼を引き受ける (承諾する)。" },
  { value: "decline", label: "断る", text: "依頼を丁寧に断る。理由はメモにあればそれを使い、なければ深くは書かない。" },
  { value: "thanks", label: "受け取ったことと礼だけ伝える", text: "受け取ったことと礼だけを短く伝える。" },
  { value: "ask", label: "確認・質問をする", text: "返事をする前に確認したいことを尋ねる。尋ねる内容はメモに従う。" },
  { value: "schedule", label: "日程を調整する", text: "日程を調整する。候補はメモに従い、メモになければ [要確認: 候補日時] と書く。" },
];

const SYSTEM = `あなたは、メールの書き手本人に代わって、返信メールの本文の下書きを書く。

出力の形
- 出力するのは本文だけ。件名、前置き、説明、Markdown の記法、コードブロックは付けない。
- 元メールと同じ言語で書く。日本語のメールには日本語、英語のメールには英語で返す。
- 引用部分 (元メールの再掲) は書かない。メールソフトが付ける。
- 署名ブロック (“-- ”以下の所属・連絡先) は書かない。メールソフトが付ける。手本が名前だけで結んでいれば、それに倣う。

文体
- 宛名、名乗り、結び、句読点の種類 (、。 か ，． か)、改行の入れ方、敬語の度合いは“文体の手本”に合わせる。手本がなければ、大学教員が同僚や学生に送る普通の業務メールの体裁にする。
- 宛名は“この返信の宛先”に入っている人に向ける。
- 短く書く。用件に答えたら終える。
- 決まり文句を重ねない。大げさな言い回し、強調のためのかぎ括弧、なんでも3つ並べる書き方、“まず” “次に” “さらに”の羅列は使わない。
- 日本語では、括弧は半角の ()、引用符は “” を使う。

中身
- 方針が指定されていれば、それに従う。指定がなければ、元メールの依頼や質問に対して自然な返事を書く。
- 書き手にしか決められないこと (引き受けるかどうか、日程、金額、人名など) を勝手に決めない。決まっていなければ [要確認: ○○] と書いて残す。
- 元メールとメモにない事実、約束、日付、数字を作らない。`;

export function buildSystem(extra) {
  return extra ? `${SYSTEM}\n\n追加の指示 (書き手の設定)\n${extra}` : SYSTEM;
}

export function buildUser(ctx, policyValue, memo) {
  const { details, identity, original, samples, sampleSource } = ctx;
  const policy = POLICIES.find((p) => p.value === policyValue);
  const out = [];

  out.push("## 返信する元メール");
  if (original.author) out.push(`差出人: ${original.author}`);
  if (original.to.length) out.push(`宛先: ${original.to.join(", ")}`);
  if (original.cc.length) out.push(`CC: ${original.cc.join(", ")}`);
  if (original.date) out.push(`日時: ${formatDate(original.date)}`);
  out.push(`件名: ${original.subject}`, "", original.body.trim(), "");

  out.push("## この返信の宛先");
  out.push(`To: ${recipientsText(details.to)}`);
  if (recipientsText(details.cc)) out.push(`CC: ${recipientsText(details.cc)}`);
  out.push("");

  if (identity) {
    out.push("## 書き手 (私)", `${identity.name || ""} <${identity.email}>`, "");
  }

  if (samples.length) {
    out.push(
      sampleSource === "recipient"
        ? "## 文体の手本 (私が同じ相手に最近送ったメール。本文のみ)"
        : "## 文体の手本 (私が最近送ったメール。相手は今回と違う。本文のみ)"
    );
    samples.forEach((s, i) => {
      out.push(`### 手本${i + 1} (${formatDate(s.date)} / 件名: ${s.subject})`, s.body, "");
    });
  }

  out.push("## 返信の方針");
  out.push(policy && policy.text ? policy.text : "指定なし。");
  if (memo.trim()) out.push("", "メモ (書き手から):", memo.trim());

  return out.join("\n");
}

function recipientsText(list) {
  return (list || []).filter((r) => typeof r === "string").join(", ");
}

export function formatDate(d) {
  if (!d) return "";
  return new Date(d).toLocaleString("ja-JP", {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}
