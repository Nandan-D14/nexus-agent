/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp, Check, ChevronLeft, ChevronRight, X } from "lucide-react";
import { ChatMarkdown } from "@/components/chat-markdown";
import { cx } from "@/utils/cx";

type Props = {
  questionId: string;
  question: string;
  answered?: boolean;
  timedOut?: boolean;
  timeoutSeconds?: number;
  /** Epoch ms when the question was issued; countdown continues from this. */
  issuedAt?: number;
  onRespond?: (questionId: string, answer: string) => void;
};

const DEFAULT_TIMEOUT_SECONDS = 300;

function formatCountdown(seconds: number): string {
  const s = Math.max(0, Math.ceil(seconds));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

/**
 * ApprovalCard chrome around free-text ask_user answers.
 * Option chips deferred until backend sends options[].
 */
export function AgentQuestionCard({
  questionId,
  question,
  answered = false,
  timedOut: timedOutProp = false,
  timeoutSeconds = DEFAULT_TIMEOUT_SECONDS,
  issuedAt,
  onRespond,
}: Props) {
  const [answer, setAnswer] = useState("");
  const [submitted, setSubmitted] = useState(answered);
  const [open, setOpen] = useState(true);
  const [localTimedOut, setLocalTimedOut] = useState(timedOutProp);
  const [remaining, setRemaining] = useState(timeoutSeconds);
  const startRef = useRef(issuedAt ?? Date.now());
  const inputRef = useRef<HTMLInputElement>(null);

  const sent = submitted || answered;
  const timedOut = !sent && (timedOutProp || localTimedOut);
  const frozen = sent || timedOut;
  const canSend = Boolean(answer.trim()) && Boolean(onRespond) && !frozen;
  const budget = Math.max(1, timeoutSeconds || DEFAULT_TIMEOUT_SECONDS);

  useEffect(() => {
    setSubmitted(answered);
  }, [answered]);

  useEffect(() => {
    if (timedOutProp) setLocalTimedOut(true);
  }, [timedOutProp]);

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
  }, [budget, frozen, questionId, issuedAt]);

  function handleSubmit() {
    const trimmed = answer.trim();
    if (!trimmed || !onRespond || frozen) return;
    setSubmitted(true);
    onRespond(questionId, trimmed);
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-lg bg-background-primary-default px-3 py-2 text-[12.5px] font-medium text-text-primary shadow-card transition-colors duration-150 hover:bg-background-primary-hover"
      >
        Open question
      </button>
    );
  }

  return (
    <div className="flex w-full max-w-80 flex-col items-stretch animate-fade-up">
      <div className="w-full self-start overflow-hidden rounded-xl border border-separator-border bg-background-primary-default shadow-card">
        {sent ? (
          <div className="flex h-37 flex-col items-center justify-center gap-2 px-4 py-8">
            <span className="flex size-6 items-center justify-center rounded-full bg-emerald-500 text-white animate-pop-in">
              <Check className="size-3" strokeWidth={3} aria-hidden />
            </span>
            <span className="text-[13px] font-medium text-text-primary animate-fade-up">
              Answers sent
            </span>
          </div>
        ) : timedOut ? (
          <div className="flex h-37 flex-col items-center justify-center gap-2 px-4 py-8">
            <span className="flex size-6 items-center justify-center rounded-full bg-background-secondary-default text-text-tertiary animate-pop-in">
              <Check className="size-3" strokeWidth={3} aria-hidden />
            </span>
            <span className="text-[13px] font-medium text-text-secondary animate-fade-up">
              No answer in time
            </span>
          </div>
        ) : (
          <div className="px-3.5 pt-3.5 pb-2">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1 text-[13px] font-medium text-text-primary [&_.markdown]:text-[13px] [&_.markdown]:leading-snug [&_.markdown]:font-medium">
                <ChatMarkdown content={question} />
              </div>
              <button
                type="button"
                aria-label="Dismiss"
                onClick={() => setOpen(false)}
                className="flex size-6 shrink-0 items-center justify-center rounded-[5px] text-text-tertiary transition-colors duration-100 hover:bg-background-primary-hover hover:text-text-primary"
              >
                <X className="size-3.5" strokeWidth={2.2} aria-hidden />
              </button>
            </div>

            <label className="-mx-1.5 mt-2 flex items-center gap-2 rounded-lg px-1.5 py-1 transition-colors duration-100 focus-within:bg-background-primary-hover hover:bg-background-primary-hover">
              <span aria-hidden className="size-4 shrink-0" />
              <input
                ref={inputRef}
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSubmit();
                  }
                }}
                placeholder="Type something…"
                aria-label="Your answer"
                disabled={frozen || !onRespond}
                className="min-w-0 flex-1 bg-transparent text-[13px] text-text-primary outline-none placeholder:text-text-tertiary disabled:cursor-not-allowed disabled:opacity-50"
              />
            </label>
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
            {/* Single-step: hide multi-dot pager */}
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

          <div className="flex items-center gap-2">
            {!frozen ? (
              <span
                className="font-mono text-[11px] tabular-nums text-text-tertiary"
                aria-live="polite"
              >
                {formatCountdown(remaining)}
              </span>
            ) : null}
            {!sent && !timedOut ? (
              <button
                type="button"
                aria-label="Send answer"
                disabled={!canSend}
                onClick={handleSubmit}
                className={cx(
                  "flex size-7 items-center justify-center rounded-[8px] transition-[background-color,color,transform] duration-200",
                  "enabled:active:scale-[0.96]",
                  canSend
                    ? "bg-text-primary text-background-primary-default shadow-[inset_0_1px_0_rgba(255,255,255,0.14)]"
                    : "bg-background-secondary-default text-text-tertiary shadow-card",
                )}
              >
                <ArrowUp className="size-3.5" strokeWidth={2.5} aria-hidden />
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
