/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronLeft, ChevronRight, X } from "lucide-react";
import { cx } from "@/utils/cx";

type Props = {
  taskId: string;
  approvalId?: string;
  durableTaskId?: string;
  description: string;
  estimatedSeconds: number;
  agent: string;
  /** Epoch ms when the request was issued; countdown continues from this. */
  issuedAt?: number;
  /** Restored/live settled outcome. */
  decision?: "approved" | "denied" | "timed_out";
  timedOut?: boolean;
  onRespond: (
    taskId: string,
    approved: boolean,
    approvalId?: string,
    durableTaskId?: string,
  ) => void;
};

function formatCountdown(seconds: number): string {
  const s = Math.max(0, Math.ceil(seconds));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

/** ApprovalCard chrome — human-in-the-loop approve / deny. */
export function PermissionCard({
  taskId,
  approvalId,
  durableTaskId,
  description,
  estimatedSeconds,
  agent,
  issuedAt,
  decision,
  timedOut: timedOutProp = false,
  onRespond,
}: Props) {
  const [response, setResponse] = useState<"approved" | "denied" | null>(() =>
    decision === "approved" ? "approved" : decision === "denied" ? "denied" : null,
  );
  const [submitting, setSubmitting] = useState(false);
  const [open, setOpen] = useState(true);
  const [localTimedOut, setLocalTimedOut] = useState(
    () => decision === "timed_out" || timedOutProp,
  );
  const [remaining, setRemaining] = useState(estimatedSeconds);
  const startRef = useRef(issuedAt ?? Date.now());
  const cardRef = useRef<HTMLDivElement>(null);

  const sent = response !== null;
  const timedOut = !sent && (decision === "timed_out" || timedOutProp || localTimedOut);
  const frozen = sent || timedOut || submitting;
  const budget = Math.max(1, estimatedSeconds || 120);

  useEffect(() => {
    if (decision === "approved" || decision === "denied") {
      setResponse(decision);
    } else if (decision === "timed_out") {
      setLocalTimedOut(true);
    }
  }, [decision]);

  function handleRespond(approved: boolean) {
    if (response !== null || submitting || timedOut) return;
    setSubmitting(true);
    setResponse(approved ? "approved" : "denied");
    onRespond(taskId, approved, approvalId, durableTaskId);
  }

  useEffect(() => {
    if (timedOutProp || decision === "timed_out") setLocalTimedOut(true);
  }, [timedOutProp, decision]);

  useEffect(() => {
    if (frozen) return;
    const start = issuedAt ?? Date.now();
    startRef.current = start;
    const initialLeft = Math.max(0, budget - (Date.now() - start) / 1000);
    setRemaining(initialLeft);
    if (initialLeft <= 0) {
      setLocalTimedOut(true);
      return;
    }

    const id = window.setInterval(() => {
      const elapsed = (Date.now() - startRef.current) / 1000;
      const left = Math.max(0, budget - elapsed);
      setRemaining(left);
      if (left <= 0) {
        setLocalTimedOut(true);
        window.clearInterval(id);
      }
    }, 250);

    return () => window.clearInterval(id);
  }, [budget, frozen, taskId, issuedAt]);

  useEffect(() => {
    if (frozen) return;

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
  }, [frozen, taskId, approvalId, durableTaskId]);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-lg bg-background-primary-default px-3 py-2 text-[12.5px] font-medium text-text-primary shadow-card transition-colors duration-150 hover:bg-background-primary-hover"
      >
        Open approval
      </button>
    );
  }

  return (
    <div
      ref={cardRef}
      className="flex w-full max-w-80 flex-col items-stretch animate-fade-up"
    >
      <div className="w-full self-start overflow-hidden rounded-xl border border-separator-border bg-background-primary-default shadow-card">
        {sent ? (
          <div className="flex h-37 flex-col items-center justify-center gap-2 px-4 py-8">
            <span
              className={cx(
                "flex size-6 items-center justify-center rounded-full text-white animate-pop-in",
                response === "approved" ? "bg-emerald-500" : "bg-red-500",
              )}
            >
              <Check className="size-3" strokeWidth={3} aria-hidden />
            </span>
            <span className="text-[13px] font-medium text-text-primary animate-fade-up">
              {response === "approved" ? "Approved" : "Denied"}
            </span>
            {agent ? (
              <span className="text-[12px] text-text-tertiary">{agent}</span>
            ) : null}
          </div>
        ) : timedOut ? (
          <div className="flex h-37 flex-col items-center justify-center gap-2 px-4 py-8">
            <span className="flex size-6 items-center justify-center rounded-full bg-background-secondary-default text-text-tertiary animate-pop-in">
              <Check className="size-3" strokeWidth={3} aria-hidden />
            </span>
            <span className="text-[13px] font-medium text-text-secondary animate-fade-up">
              Approval timed out
            </span>
          </div>
        ) : (
          <div className="px-3.5 pt-3.5 pb-2">
            <div className="flex items-start justify-between gap-3">
              <span className="min-w-0 flex-1 text-[13px] font-medium text-text-primary">
                {description}
              </span>
              <button
                type="button"
                aria-label="Dismiss"
                onClick={() => setOpen(false)}
                className="flex size-6 shrink-0 items-center justify-center rounded-[5px] text-text-tertiary transition-colors duration-100 hover:bg-background-primary-hover hover:text-text-primary"
              >
                <X className="size-3.5" strokeWidth={2.2} aria-hidden />
              </button>
            </div>

            <div className="mt-2 flex flex-col gap-0.5" role="radiogroup" aria-label="Approval choice">
              {(
                [
                  { label: "Approve", value: true, shortcut: "Y" },
                  { label: "Deny", value: false, shortcut: "N" },
                ] as const
              ).map((option) => {
                const on = response === (option.value ? "approved" : "denied");
                return (
                  <button
                    key={option.label}
                    type="button"
                    role="radio"
                    aria-checked={on}
                    disabled={frozen}
                    onClick={() => handleRespond(option.value)}
                    className="-mx-1.5 flex items-center gap-2 rounded-lg px-1.5 py-1 text-left transition-colors duration-100 hover:bg-background-primary-hover disabled:cursor-not-allowed"
                  >
                    <span
                      className={cx(
                        "flex size-4 shrink-0 items-center justify-center rounded-full transition-colors duration-200",
                        on
                          ? "bg-text-primary text-background-primary-default"
                          : "text-transparent shadow-[inset_0_0_0_1.5px_var(--color-separator-border-strong)]",
                      )}
                    >
                      <span
                        className="size-1.5 rounded-full bg-background-primary-default transition-transform duration-200"
                        style={{ transform: on ? "scale(1)" : "scale(0)" }}
                      />
                    </span>
                    <span
                      className={cx(
                        "flex-1 text-[13px] transition-colors duration-200",
                        on ? "text-text-primary" : "text-text-secondary",
                      )}
                    >
                      {option.label}
                    </span>
                    <kbd className="rounded px-1 text-[10px] font-medium text-text-tertiary">
                      {option.shortcut}
                    </kbd>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div className="flex items-center justify-between border-t border-separator-border px-2.5 py-2">
          <span className="flex items-center gap-2">
            <span
              className="flex size-6 items-center justify-center rounded-[5px] text-text-tertiary opacity-35"
              aria-hidden
            >
              <ChevronLeft className="size-3.5" strokeWidth={2.2} />
            </span>
            <span className="flex items-center gap-1" aria-hidden>
              <span
                className="rounded-full"
                style={{
                  width: 9,
                  height: 9,
                  border: "2.5px solid var(--color-text-primary)",
                }}
              />
            </span>
            <span
              className="flex size-6 items-center justify-center rounded-[5px] text-text-tertiary opacity-35"
              aria-hidden
            >
              <ChevronRight className="size-3.5" strokeWidth={2.2} />
            </span>
          </span>

          {!frozen ? (
            <span
              className="font-mono text-[11px] tabular-nums text-text-tertiary"
              aria-live="polite"
            >
              {formatCountdown(remaining)}
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
}
