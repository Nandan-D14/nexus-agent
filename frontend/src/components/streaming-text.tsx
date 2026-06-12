/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { ChatMarkdown } from "@/components/chat-markdown";

type Props = {
  text: string;
  isStreaming: boolean;
};

export function StreamingText({ text, isStreaming }: Props) {
  return (
    <div className="relative">
      <ChatMarkdown content={text} />
      {isStreaming && (
        <span className="inline-block w-[2px] h-[1em] bg-foreground/60 ml-0.5 align-text-bottom animate-pulse" />
      )}
    </div>
  );
}
