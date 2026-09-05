/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

/**
 * Normalizes streaming or partial markdown content so that unclosed code fences,
 * unclosed math blocks, and currency symbols render cleanly without syntax crashes
 * or visual jumping.
 */
export function normalizeStreamingMarkdown(raw: string): string {
  if (!raw || typeof raw !== "string") return "";

  let text = raw;

  // 1. Currency Guard: Escape dollar signs that are immediately followed by digits
  // so remark-math doesn't falsely interpret "$50 and $100" as inline math.
  text = text.replace(/(^|[^\\])\$([0-9]+(?:[.,][0-9]+)*)/g, "$1\\$$2");

  // 2. Unclosed Code Blocks:
  const codeBlockMatches = text.match(/(^|\n)```/g);
  const codeBlockCount = codeBlockMatches ? codeBlockMatches.length : 0;
  if (codeBlockCount % 2 !== 0) {
    text = text.endsWith("\n") ? `${text}\`\`\`` : `${text}\n\`\`\``;
  }

  // 3. Unclosed Block Math ($$):
  const mathBlockMatches = text.match(/(^|\n)\$\$/g);
  const mathBlockCount = mathBlockMatches ? mathBlockMatches.length : 0;
  if (mathBlockCount % 2 !== 0) {
    text = text.endsWith("\n") ? `${text}$$` : `${text}\n$$`;
  }

  return text;
}
