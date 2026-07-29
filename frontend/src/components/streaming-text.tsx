/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { TextResponse } from "@/components/agent-ui/text-response";
import { cx } from "@/utils/cx";

type Props = {
  text: string;
  isStreaming: boolean;
};

/**
 * Beautiful UI Streaming Text polish — soft mount reveal + caret.
 * WS delivers full transcript text; no fake typewriter.
 */
export function StreamingText({ text, isStreaming }: Props) {
  return (
    <div
      className={cx(
        "relative",
        isStreaming && "animate-text-reveal-fade",
      )}
    >
      <TextResponse content={text} />
      {isStreaming ? (
        <span
          className="animate-cursor-blink ml-0.5 inline-block h-[1.05em] w-[1.5px] align-text-bottom bg-blue-500"
          aria-hidden
        />
      ) : null}
    </div>
  );
}
