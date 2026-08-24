/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

const OPTION_LINE = /^\s*\d+[.)]\s+(.+?)\s*$/;
const CUSTOM_OPTION =
  /^(something else|something different|other|none of (the )?these|none of the above|type (my|your) own)\.?$/i;

const MAX_OPTIONS = 6;
const MIN_OPTIONS = 2;
const MAX_OPTION_CHARS = 80;

export function isCustomAskUserOption(label: string): boolean {
  return CUSTOM_OPTION.test(label.trim());
}

export function coerceAskUserOptions(raw: unknown): string[] | undefined {
  if (!Array.isArray(raw)) return undefined;
  const labels: string[] = [];
  const seen = new Set<string>();
  for (const item of raw) {
    let label = String(item ?? "")
      .replace(/\s+/g, " ")
      .trim()
      .replace(/^\d+[.)]\s+/, "");
    if (!label) continue;
    if (label.length > MAX_OPTION_CHARS) {
      label = `${label.slice(0, MAX_OPTION_CHARS - 1)}…`;
    }
    const key = label.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    labels.push(label);
    if (labels.length >= MAX_OPTIONS) break;
  }
  return labels.length >= MIN_OPTIONS ? labels : undefined;
}

export function splitAskUserQuestion(question: string): {
  prompt: string;
  options: string[];
} {
  const lines = question.replace(/\r\n/g, "\n").split("\n");
  const options: string[] = [];
  const promptLines: string[] = [];
  let sawOption = false;
  for (const line of lines) {
    const match = line.match(OPTION_LINE);
    if (match) {
      sawOption = true;
      const label = match[1].trim();
      if (label) options.push(label);
      continue;
    }
    if (sawOption && !line.trim()) continue;
    promptLines.push(line);
  }
  const coerced = coerceAskUserOptions(options);
  return {
    prompt: promptLines.join("\n").trim() || question.trim(),
    options: coerced ?? [],
  };
}
