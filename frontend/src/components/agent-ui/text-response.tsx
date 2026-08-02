/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useMemo } from "react";
import { ChatMarkdown } from "@/components/chat-markdown";
import {
  extractMarkdownCitations,
  InlineCitations,
} from "@/components/agent-ui/inline-citations";
import { cx } from "@/utils/cx";

type Props = {
  content: string;
  className?: string;
  /** When true, skip the sources footer only (inline numbered badges still render). */
  hideCitations?: boolean;
};

/** AICSS Text Response — prose + optional numbered markdown-link citations. */
export function TextResponse({ content, className, hideCitations }: Props) {
  const { citationMap, refs } = useMemo(
    () => extractMarkdownCitations(content),
    [content],
  );

  return (
    <div className={cx("w-full text-text-primary", className)}>
      <ChatMarkdown content={content} citationMap={citationMap} />
      {!hideCitations ? <InlineCitations refs={refs} /> : null}
    </div>
  );
}
