/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChatMarkdown } from "@/components/chat-markdown";
import { formatDuration } from "@/components/agent-ui/activity-log";
import { cx } from "@/utils/cx";

const COLLAPSE_BEAT_MS = 360;
const MAX_H = 180;
const FADE = 16;

export function hasRealReasoning(chunks: string[]): boolean {
  return chunks.some((c) => {
    const t = c.trim();
    return t.length > 0 && t !== "Thinking...";
  });
}

type Props = {
  chunks: string[];
  isActive: boolean;
  startedAt: number;
  endedAt?: number;
  className?: string;
};

/**
 * AICSS Thinking + Reasoning — shimmer while active, then "Thought for 19m 47s".
 * Driven by real agent_thinking chunks (no fake SENTENCES).
 */
export function ThinkingReasoning({
  chunks,
  isActive,
  startedAt,
  endedAt,
  className,
}: Props) {
  const [open, setOpen] = useState(false);
  const [liveNow, setLiveNow] = useState(() => Date.now());
  const [fade, setFade] = useState({ top: false, bottom: true });
  // After thinking ends, keep body open briefly before allowing collapse.
  const [holdOpen, setHoldOpen] = useState(false);
  const viewportRef = useRef<HTMLDivElement>(null);
  const prevActive = useRef(isActive);

  const text = useMemo(
    () => chunks.map((c) => c.trim()).filter(Boolean).join("\n\n"),
    [chunks],
  );

  const elapsedLabel = useMemo(() => {
    const end = isActive ? liveNow : (endedAt ?? liveNow);
    const ms = Math.max(1000, end - startedAt);
    return formatDuration(ms) || "1s";
  }, [isActive, liveNow, endedAt, startedAt]);

  useEffect(() => {
    if (!isActive) return;
    const id = window.setInterval(() => setLiveNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [isActive]);

  useEffect(() => {
    const wasActive = prevActive.current;
    prevActive.current = isActive;

    if (wasActive && !isActive) {
      if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
        return;
      }
      // Async only — satisfies react-hooks/set-state-in-effect.
      const start = window.setTimeout(() => setHoldOpen(true), 0);
      const end = window.setTimeout(() => {
        setHoldOpen(false);
        setOpen(false);
      }, COLLAPSE_BEAT_MS);
      return () => {
        window.clearTimeout(start);
        window.clearTimeout(end);
      };
    }
  }, [isActive]);

  const done = !isActive && !holdOpen;
  const expanded = isActive || holdOpen || open;

  const onScroll = () => {
    const el = viewportRef.current;
    if (!el) return;
    setFade({
      top: el.scrollTop > 1,
      bottom: el.scrollTop + el.clientHeight < el.scrollHeight - 1,
    });
  };

  const toggle = () => {
    const next = !open;
    if (next) {
      setFade({ top: false, bottom: true });
      if (viewportRef.current) viewportRef.current.scrollTop = 0;
    }
    setOpen(next);
  };

  const scrollable = done && open;
  const mask =
    scrollable || (!done && text.length > 400)
      ? `linear-gradient(to bottom, transparent 0, #000 ${fade.top || (!scrollable && text.length > 400) ? FADE : 0}px, #000 calc(100% - ${fade.bottom || (!scrollable && text.length > 400) ? FADE : 0}px), transparent 100%)`
      : "none";

  return (
    <div className={cx("flex w-full max-w-xl flex-col gap-1", className)}>
      <button
        type="button"
        className={cx(
          "flex w-fit items-center gap-1.5 py-0.5 text-left select-none",
          done && "cursor-pointer",
          !done && "cursor-default",
        )}
        aria-expanded={expanded}
        aria-label="Toggle thought"
        onClick={done ? toggle : undefined}
        disabled={!done}
      >
        {done ? (
          <span className="text-body-medium text-text-secondary">
            <span className="text-text-primary">Thought</span> for {elapsedLabel}
          </span>
        ) : (
          <span className="text-body-medium agent-progress-loading-text">
            Thinking…
          </span>
        )}
        {done ? (
          <svg
            className={cx(
              "size-3 text-foreground-icon-tertiary transition-transform",
              open && "rotate-180",
            )}
            viewBox="0 0 24 24"
            aria-hidden
          >
            <path
              d="m4.5 15.75 7.5-7.5 7.5 7.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        ) : null}
      </button>

      <div
        className={cx(
          "grid transition-[grid-template-rows] duration-300 ease-out",
          expanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
        )}
      >
        <div className="overflow-hidden">
          <div
            ref={viewportRef}
            className={cx(
              "relative border-l-2 border-separator-border pl-3",
              scrollable && "overflow-y-auto",
            )}
            style={{
              maxHeight: scrollable || !done ? MAX_H : undefined,
              WebkitMaskImage: mask,
              maskImage: mask,
            }}
            onScroll={scrollable ? onScroll : undefined}
          >
            <div className="text-body-2-regular text-text-secondary [&_.markdown]:text-[13px] [&_.markdown]:leading-relaxed">
              {text ? (
                <ChatMarkdown content={text} />
              ) : (
                <span className="text-text-tertiary">…</span>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
