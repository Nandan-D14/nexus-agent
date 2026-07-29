/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { Bot } from "lucide-react";
import { Button } from "@/components/base/buttons/button";
import { Kbd } from "@/components/base/kbd/kbd";
import { cx } from "@/utils/cx";

type Props = {
  taskId: string;
  approvalId?: string;
  durableTaskId?: string;
  description: string;
  estimatedSeconds: number;
  agent: string;
  onRespond: (
    taskId: string,
    approved: boolean,
    approvalId?: string,
    durableTaskId?: string,
  ) => void;
};

function formatEstimatedTime(seconds: number): string {
  if (seconds < 60) return `${seconds} sec`;
  return `~${Math.round(seconds / 60)} min`;
}

function DotStrip() {
  return (
    <span className="inline-flex items-center justify-center gap-1" aria-hidden>
      <span className="size-1 animate-pulse rounded-full bg-current [animation-delay:0ms]" />
      <span className="size-1 animate-pulse rounded-full bg-current [animation-delay:120ms]" />
      <span className="size-1 animate-pulse rounded-full bg-current [animation-delay:240ms]" />
    </span>
  );
}

/** Beautiful UI Approval Card — human-in-the-loop approve / deny. */
export function PermissionCard({
  taskId,
  approvalId,
  durableTaskId,
  description,
  estimatedSeconds,
  agent,
  onRespond,
}: Props) {
  const [response, setResponse] = useState<"approved" | "denied" | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  function handleRespond(approved: boolean) {
    if (response !== null || submitting) return;
    setSubmitting(true);
    setResponse(approved ? "approved" : "denied");
    onRespond(taskId, approved, approvalId, durableTaskId);
  }

  const resolved = response !== null;
  const disabled = resolved || submitting;

  useEffect(() => {
    if (resolved) return;

    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      const el = cardRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const visible =
        rect.bottom > 0 &&
        rect.top < (typeof window !== "undefined" ? window.innerHeight : 0);
      if (!visible) return;

      const key = e.key.toLowerCase();
      if (key === "y") {
        e.preventDefault();
        handleRespond(true);
      } else if (key === "n") {
        e.preventDefault();
        handleRespond(false);
      }
    }

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- respond only while unresolved
  }, [resolved, submitting, taskId, approvalId, durableTaskId]);

  const agentInitial = (agent || "A").trim().charAt(0).toUpperCase() || "A";

  return (
    <div
      ref={cardRef}
      className={cx(
        "relative w-full max-w-sm space-y-3 rounded-2lg border bg-background-primary-default p-4 transition-all duration-300",
        resolved
          ? response === "approved"
            ? "border-emerald-500/30"
            : "border-red-500/30"
          : "border-amber-500/40 shadow-[0_0_16px_rgba(245,158,11,0.08)]",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <div className="flex size-6 shrink-0 items-center justify-center rounded-md bg-linear-to-b from-amber-500 to-amber-600 text-[11px] font-bold text-white shadow-sm">
            {agentInitial}
          </div>
          <div className="flex items-center gap-2">
            <div
              className={cx(
                "size-1.5 rounded-full transition-colors duration-300",
                resolved
                  ? response === "approved"
                    ? "bg-emerald-500"
                    : "bg-red-500"
                  : "animate-pulse bg-amber-500",
              )}
            />
            <span className="text-caption-2-bold tracking-[0.15em] text-amber-500 uppercase">
              Permission request
            </span>
          </div>
        </div>
        {resolved ? (
          <span
            className={cx(
              "rounded px-1.5 py-0.5 text-caption-2-bold tracking-widest uppercase",
              response === "approved"
                ? "bg-emerald-500/10 text-emerald-500"
                : "bg-red-500/10 text-red-500",
            )}
          >
            {response === "approved" ? "Approved" : "Denied"}
          </span>
        ) : (
          <div className="flex items-center gap-1 text-caption-1-regular text-text-tertiary">
            <Kbd>Y</Kbd>
            <span>/</span>
            <Kbd>N</Kbd>
          </div>
        )}
      </div>

      <p className="text-body-medium leading-relaxed text-text-primary">
        {description}
      </p>

      <div className="flex items-center gap-3 text-caption-1-semibold tracking-wider text-text-tertiary uppercase">
        <div className="flex items-center gap-1.5">
          <Bot className="size-3 text-foreground-icon-tertiary" aria-hidden />
          <span className="normal-case tracking-normal text-text-secondary">
            {agent}
          </span>
        </div>
        <div className="h-3 w-px bg-separator-border" />
        <div className="flex items-center gap-1.5">
          <span>Est.</span>
          <span className="normal-case tracking-normal text-text-secondary">
            {formatEstimatedTime(estimatedSeconds)}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2 pt-0.5">
        <Button
          type="button"
          size="small"
          variant={resolved && response === "approved" ? "primary" : "secondary"}
          disabled={disabled}
          onClick={() => handleRespond(true)}
          className={cx(
            "flex-1",
            !resolved &&
              "border-emerald-500/25 bg-emerald-500/10 text-emerald-600 hover:bg-emerald-500/20 dark:text-emerald-400",
            resolved &&
              response === "approved" &&
              "border-emerald-500/20 bg-emerald-500/10 text-emerald-500",
          )}
        >
          {submitting && response === "approved" ? (
            <DotStrip />
          ) : resolved && response === "approved" ? (
            "Approved"
          ) : (
            "Approve"
          )}
        </Button>
        <Button
          type="button"
          size="small"
          variant="ghost"
          disabled={disabled}
          onClick={() => handleRespond(false)}
          className={cx(
            "flex-1",
            !resolved &&
              "border border-separator-border text-red-500 hover:bg-red-500/10 hover:text-red-500",
            resolved &&
              response === "denied" &&
              "border border-red-500/20 bg-red-500/10 text-red-500",
            resolved &&
              response !== "denied" &&
              "text-text-tertiary",
          )}
        >
          {submitting && response === "denied" ? (
            <DotStrip />
          ) : resolved && response === "denied" ? (
            "Denied"
          ) : (
            "Deny"
          )}
        </Button>
      </div>
    </div>
  );
}
