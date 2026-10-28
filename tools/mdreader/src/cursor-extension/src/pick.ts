/** Chunk shape shared with mdparse.py output. */
export interface Chunk {
  i: number;
  line: number; // 1-based first source line the sentence covers
  end: number; // 1-based last source line it covers
  kind: string;
  text: string;
  say: string | null;
}

/**
 * The speakable chunk to start at for a 1-based caret line.
 *
 * A sentence covers a range of source lines: a paragraph written on one long
 * line (the usual shape in Japanese Markdown) puts several sentences on the
 * same line, and one sentence can also run across several wrapped lines. The
 * caret's line must resolve to the *first* sentence covering it — otherwise
 * "read from here" skips into the middle of the paragraph. Lines that produce
 * nothing spoken (code blocks, tables, LaTeX floats) fall back to the sentence
 * above, and a caret above the first sentence starts at the top.
 */
export function pickChunkForLine(chunks: Chunk[], line: number): Chunk | undefined {
  const covering = chunks.find(
    (c) => c.say && c.line <= line && (c.end ?? c.line) >= line
  );
  if (covering) {
    return covering;
  }
  let target: Chunk | undefined;
  for (const c of chunks) {
    if (c.say && c.line < line) {
      target = c;
    }
  }
  return target ?? chunks.find((c) => c.say);
}
