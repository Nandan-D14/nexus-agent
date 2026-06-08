/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { ChatMarkdown } from "@/components/chat-markdown";

type Props = {
  text: string;
  isStreaming: boolean;
  speed?: number;
};

export function StreamingText({ text, isStreaming, speed = 12 }: Props) {
  const [revealedLength, setRevealedLength] = useState(0);
  const rafRef = useRef<number>(0);
  const lastTickRef = useRef(0);
  const prevTextRef = useRef("");

  useEffect(() => {
    if (text !== prevTextRef.current) {
      if (!isStreaming) {
        setRevealedLength(text.length);
      } else if (text.length < prevTextRef.current.length) {
        setRevealedLength(0);
      }
      prevTextRef.current = text;
    }
  }, [text, isStreaming]);

  useEffect(() => {
    if (!isStreaming) {
      setRevealedLength(text.length);
      return;
    }

    if (revealedLength >= text.length) return;

    const tick = (timestamp: number) => {
      if (!lastTickRef.current) lastTickRef.current = timestamp;
      const elapsed = timestamp - lastTickRef.current;

      if (elapsed >= speed) {
        const charsPerTick = Math.max(1, Math.floor(elapsed / speed));
        setRevealedLength((prev) => {
          const next = Math.min(prev + charsPerTick, text.length);
          return next;
        });
        lastTickRef.current = timestamp;
      }

      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(rafRef.current);
      lastTickRef.current = 0;
    };
  }, [isStreaming, revealedLength, text, speed]);

  const isComplete = revealedLength >= text.length;
  const displayedText = text.slice(0, revealedLength);

  return (
    <div className="relative">
      <ChatMarkdown content={displayedText} />
      {!isComplete && isStreaming && (
        <span className="inline-block w-[2px] h-[1em] bg-foreground/60 ml-0.5 align-text-bottom animate-pulse" />
      )}
    </div>
  );
}
