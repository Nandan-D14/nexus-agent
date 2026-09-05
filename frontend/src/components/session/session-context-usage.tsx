/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import {
  Context,
  ContextContent,
  ContextContentBody,
  ContextContentFooter,
  ContextContentHeader,
  ContextInputUsage,
  ContextOutputUsage,
  ContextTrigger,
  type ContextUsage,
} from "@/components/ai-elements/context";

export type SessionContextUsageState = {
  maxTokens: number;
  usedTokens: number;
  usage: ContextUsage;
  model?: string;
};

/** Map provider model names to tokenlens catalog ids when known. */
export function resolveTokenlensModelId(model?: string): string | undefined {
  const raw = (model || "").trim();
  if (!raw) return undefined;
  const lower = raw.toLowerCase();
  if (lower.startsWith("openai:")) return raw;
  if (lower.startsWith("anthropic:")) return raw;
  if (lower.startsWith("google:") || lower.startsWith("gemini:")) return raw;
  if (/^gpt-/.test(lower) || /^o[1-9]/.test(lower)) return `openai:${raw}`;
  if (/^claude-/.test(lower)) return `anthropic:${raw}`;
  if (/^gemini-/.test(lower)) return `google:${raw}`;
  // Qwen / Vultr / custom: skip cost estimation
  return undefined;
}

export function SessionContextUsage({
  state,
}: {
  state: SessionContextUsageState | null;
}) {
  if (!state || state.maxTokens <= 0) return null;

  const modelId = resolveTokenlensModelId(state.model);

  return (
    <Context
      maxTokens={state.maxTokens}
      usedTokens={Math.max(0, state.usedTokens)}
      usage={state.usage}
      modelId={modelId}
    >
      <ContextTrigger className="h-7 gap-1 px-1.5 text-xs text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100" />
      <ContextContent className="min-w-60 border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 shadow-lg">
        <ContextContentHeader />
        <ContextContentBody className="space-y-2">
          <ContextInputUsage />
          <ContextOutputUsage />
        </ContextContentBody>
        {modelId ? <ContextContentFooter /> : null}
      </ContextContent>
    </Context>
  );
}
