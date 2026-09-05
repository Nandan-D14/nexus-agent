/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Clock, CornerDownLeft, LayoutGrid, X } from "lucide-react";
import { ChatMarkdown } from "@/components/chat-markdown";
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
  /** Policy risk tier (low/medium/high) shown under the description. */
  risk?: string;
  /** Opaque fingerprint of the exact approved args. */
  actionHash?: string;
  /** Tool that requested approval, for log lines. */
  tool?: string;
  /** Epoch ms when the decision landed. */
  decidedAt?: number;
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

function formatTime(ts?: number): string | null {
  if (!ts || !Number.isFinite(ts)) return null;
  try {
    return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return null;
  }
}

/** Approval card — same card language as ElicitationUI (ask_choice / suggest_options). */
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
  risk,
  actionHash,
  tool,
  decidedAt,
  onRespond,
}: Props) {
  const [response, setResponse] = useState<"approved" | "denied" | null>(() =>
    decision === "approved" ? "approved" : decision === "denied" ? "denied" : null,
  );
  const [submitting, setSubmitting] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null);
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
      if (key === "y" || key === "1") {
        e.preventDefault();
        handleRespond(true);
      } else if (key === "n" || key === "2") {
        e.preventDefault();
        handleRespond(false);
      }
    }

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- respond only while unresolved
  }, [frozen, taskId, approvalId, durableTaskId]);

  if (dismissed && !frozen) {
    return (
      <button
        type="button"
        onClick={() => setDismissed(false)}
        className="flex items-center gap-1.5 rounded-lg border border-border/70 bg-zinc-900/90 px-3 py-1.5 text-[12px] font-medium text-zinc-300 shadow-sm transition-colors hover:bg-zinc-800"
      >
        <LayoutGrid className="size-3.5 text-indigo-400" />
        <span>Show approval</span>
      </button>
    );
  }

  const subtitle = [
    agent || "policy",
    risk ? `risk: ${risk}` : null,
    tool ? tool.replace(/_/g, " ") : null,
  ]
    .filter(Boolean)
    .join(" • ");
  const decidedLabel = formatTime(decidedAt);
  const shortHash =
    actionHash && actionHash.length > 10
      ? `${actionHash.slice(0, 10)}…`
      : actionHash || null;

  const options = [
    { label: "Approve", value: true, num: 1, shortcut: "Y" },
    { label: "Deny", value: false, num: 2, shortcut: "N" },
  ] as const;

  return (
    <div
      ref={cardRef}
      tabIndex={frozen ? -1 : 0}
      onKeyDown={(e) => {
        if (frozen) return;
        if (e.target instanceof HTMLInputElement) return;
        const num = Number(e.key);
        if (num === 1) {
          e.preventDefault();
          handleRespond(true);
        } else if (num === 2) {
          e.preventDefault();
          handleRespond(false);
        }
      }}
      className="flex w-full max-w-[32rem] flex-col items-stretch outline-none animate-fade-up"
    >
      <div className="w-full overflow-hidden rounded-2xl border border-zinc-800 bg-[#18181b] p-4 text-zinc-100 shadow-xl dark:border-zinc-800/80">
        {/* Header bar — mirrors ElicitationUI */}
        <div className="flex items-start justify-between gap-3 pb-3">
          <div className="flex-1 pr-2">
            <div className="text-[14.5px] font-medium leading-snug text-zinc-100">
              <ChatMarkdown content={description || "Approval required to continue."} />
            </div>
            {subtitle ? (
              <div className="mt-1 text-[12px] text-zinc-400">{subtitle}</div>
            ) : null}
          </div>

          <div className="flex items-center gap-2 shrink-0 pt-0.5">
            {!frozen && remaining <= 60 && (
              <span className="flex items-center gap-1 font-mono text-[11px] font-medium text-amber-400">
                <Clock className="size-3" />
                {formatCountdown(remaining)}
              </span>
            )}
            {!frozen && (
              <button
                type="button"
                aria-label="Dismiss"
                onClick={() => setDismissed(true)}
                className="flex size-5 items-center justify-center rounded text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
              >
                <X className="size-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Pending: numbered Approve / Deny rows */}
        {!sent && !timedOut ? (
          <div className="flex flex-col gap-1.5 pt-1" role="radiogroup" aria-label="Approval choice">
            {options.map((option, index) => {
              const on = response === (option.value ? "approved" : "denied");
              const isFocused = focusedIndex === index;
              return (
                <button
                  key={option.label}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  disabled={frozen}
                  onClick={() => handleRespond(option.value)}
                  onMouseEnter={() => setFocusedIndex(index)}
                  onMouseLeave={() => setFocusedIndex(null)}
                  className={cx(
                    "group flex min-h-10 items-center justify-between gap-3 rounded-xl px-3 py-2 text-left transition-all",
                    on
                      ? "bg-zinc-800 border border-zinc-700 text-white shadow-sm"
                      : "bg-zinc-900/50 hover:bg-zinc-800/60 text-zinc-200 border border-transparent",
                    frozen && !on && "opacity-50 cursor-default hover:bg-zinc-900/50",
                  )}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span
                      className={cx(
                        "flex size-6 shrink-0 items-center justify-center rounded-md font-mono text-[11.5px] font-semibold",
                        on
                          ? "bg-zinc-700 text-white"
                          : "bg-zinc-800/80 text-zinc-400 group-hover:text-zinc-200",
                      )}
                    >
                      {option.num}
                    </span>
                    <span className="text-[13.5px] truncate font-normal">{option.label}</span>
                  </div>

                  {on ? (
                    <Check className="size-3.5 text-emerald-400 shrink-0" />
                  ) : isFocused && !frozen ? (
                    <CornerDownLeft className="size-3.5 text-zinc-400 shrink-0 transition-opacity opacity-80" />
                  ) : (
                    <kbd className="rounded px-1 text-[10px] font-medium text-zinc-500">
                      {option.shortcut}
                    </kbd>
                  )}
                </button>
              );
            })}
          </div>
        ) : null}

        {/* Resolved: keep full context (fixes "Approved / policy" losing description) */}
        {sent ? (
          <div className="flex flex-col items-center justify-center gap-1.5 px-4 py-4">
            <span
              className={cx(
                "flex size-6 items-center justify-center rounded-full text-white animate-pop-in",
                response === "approved" ? "bg-emerald-500" : "bg-red-500",
              )}
            >
              {response === "approved" ? (
                <Check className="size-3" strokeWidth={3} aria-hidden />
              ) : (
                <X className="size-3" strokeWidth={3} aria-hidden />
              )}
            </span>
            <span className="text-[13px] font-medium text-text-primary animate-fade-up">
              {response === "approved" ? "Approved" : "Denied"}
            </span>
            {subtitle ? (
              <span className="text-[12px] text-zinc-400">{subtitle}</span>
            ) : null}
          </div>
        ) : null}

        {timedOut ? (
          <div className="flex flex-col items-center justify-center gap-1.5 px-4 py-4">
            <span className="flex size-6 items-center justify-center rounded-full bg-zinc-800 text-zinc-400 animate-pop-in">
              <Clock className="size-3" aria-hidden />
            </span>
            <span className="text-[13px] font-medium text-zinc-400 animate-fade-up">
              Approval timed out
            </span>
            {subtitle ? (
              <span className="text-[12px] text-zinc-500">{subtitle}</span>
            ) : null}
          </div>
        ) : null}

        {/* Resolved footer note — mirrors ElicitationUI "Selected:" row */}
        {sent && response && (
          <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-0.5 border-t border-zinc-800/80 pt-2 text-[11.5px] text-zinc-400">
            <span className="flex items-center gap-1.5">
              <Check className="size-3.5 text-emerald-400" />
              <span>
                Selected: {response === "approved" ? "Approved" : "Denied"}
              </span>
            </span>
            {decidedLabel ? <span>• {decidedLabel}</span> : null}
            {shortHash ? (
              <span className="font-mono" title={actionHash}>
                • {shortHash}
              </span>
            ) : null}
          </div>
        )}
        {timedOut && (
          <div className="mt-3 flex items-center gap-1.5 border-t border-zinc-800/80 pt-2 text-[11.5px] text-zinc-500">
            <Clock className="size-3.5 text-zinc-500" />
            <span>Timed out — continue with a safe default</span>
          </div>
        )}
      </div>
    </div>
  );
}
