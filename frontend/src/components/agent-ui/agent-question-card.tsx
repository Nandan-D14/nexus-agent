/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowUp, Check, Clock, HelpCircle, X } from "lucide-react";
import { ChatMarkdown } from "@/components/chat-markdown";
import {
  coerceAskUserOptions,
  isCustomAskUserOption,
  splitAskUserQuestion,
} from "@/lib/ask-user-options";
import { cx } from "@/utils/cx";

type Props = {
  questionId: string;
  question: string;
  options?: string[];
  answer?: string;
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

function selectedLabel(
  choices: string[],
  picked: string | null,
): string | null {
  if (!picked) return null;
  if (choices.includes(picked)) return picked;
  const custom = choices.find(isCustomAskUserOption);
  return custom ?? picked;
}

/**
 * Numbered multiple-choice picker for ask_user, with a free-text fallback.
 */
export function AgentQuestionCard({
  questionId,
  question,
  options,
  answer: answerProp,
  answered = false,
  timedOut: timedOutProp = false,
  timeoutSeconds = DEFAULT_TIMEOUT_SECONDS,
  issuedAt,
  onRespond,
}: Props) {
  const parsed = useMemo(() => splitAskUserQuestion(question), [question]);
  const choices = coerceAskUserOptions(options) ?? parsed.options;
  const heading = parsed.options.length >= 2 ? parsed.prompt : question;

  const [textAnswer, setTextAnswer] = useState("");
  const [picked, setPicked] = useState<string | null>(answerProp ?? null);
  const [submitted, setSubmitted] = useState(answered);
  const [open, setOpen] = useState(true);
  const [localTimedOut, setLocalTimedOut] = useState(timedOutProp);
  const [remaining, setRemaining] = useState(timeoutSeconds);
  const startRef = useRef(issuedAt ?? Date.now());
  const inputRef = useRef<HTMLInputElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  const sent = submitted || answered;
  const timedOut = !sent && (timedOutProp || localTimedOut);
  const frozen = sent || timedOut;
  const budget = Math.max(1, timeoutSeconds || DEFAULT_TIMEOUT_SECONDS);
  const active = selectedLabel(choices, picked ?? answerProp ?? null);
  const customChoice = choices.find(isCustomAskUserOption) ?? null;
  const customOpen =
    Boolean(customChoice) &&
    !frozen &&
    (active === customChoice || (picked != null && !choices.includes(picked)));
  const canSendCustom = Boolean(textAnswer.trim()) && Boolean(onRespond) && !frozen;

  useEffect(() => {
    setSubmitted(answered);
  }, [answered]);

  useEffect(() => {
    if (answerProp) setPicked(answerProp);
  }, [answerProp]);

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

  useEffect(() => {
    if (frozen || !open) return;
    cardRef.current?.focus();
  }, [frozen, open, questionId]);

  useEffect(() => {
    if (customOpen) inputRef.current?.focus();
  }, [customOpen]);

  function commit(value: string) {
    const trimmed = value.trim();
    if (!trimmed || !onRespond || frozen) return;
    setPicked(trimmed);
    setSubmitted(true);
    onRespond(questionId, trimmed);
  }

  function handlePick(label: string) {
    if (frozen || !onRespond) return;
    if (isCustomAskUserOption(label)) {
      setPicked(label);
      return;
    }
    commit(label);
  }

  function handleSubmitCustom() {
    commit(textAnswer);
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 rounded-lg border border-border/70 bg-background px-3 py-1.5 text-[12.5px] font-medium text-foreground shadow-sm transition-colors hover:bg-muted"
      >
        <HelpCircle className="size-3.5 text-indigo-500" />
        <span>Open question</span>
      </button>
    );
  }

  return (
    <div
      ref={cardRef}
      tabIndex={frozen ? -1 : 0}
      onKeyDown={(event) => {
        if (frozen) return;
        if (event.target instanceof HTMLInputElement) return;
        const index = Number(event.key);
        if (index >= 1 && index <= choices.length) {
          event.preventDefault();
          handlePick(choices[index - 1]);
        }
      }}
      className="flex w-full max-w-[28rem] flex-col items-stretch outline-none animate-fade-up"
    >
      <div className="w-full self-start overflow-hidden rounded-2xl border border-indigo-500/20 bg-background shadow-lg dark:border-indigo-500/30">
        {/* Header bar */}
        <div className="border-b border-border/50 bg-indigo-50/50 px-4 py-3 dark:bg-indigo-950/20">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="flex size-6 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-400">
                <HelpCircle className="size-3.5" />
              </span>
              <span className="text-[11.5px] font-semibold uppercase tracking-wider text-indigo-600 dark:text-indigo-400">
                Agent Question
              </span>
            </div>

            <div className="flex items-center gap-2">
              {!frozen ? (
                <span
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-mono text-[11px] font-medium tabular-nums ${
                    remaining <= 30
                      ? "bg-amber-500/15 text-amber-600 dark:text-amber-400 animate-pulse"
                      : "bg-muted text-muted-foreground"
                  }`}
                  aria-live="polite"
                >
                  <Clock className="size-3" />
                  {formatCountdown(remaining)}
                </span>
              ) : timedOut ? (
                <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                  Timed out
                </span>
              ) : null}

              <button
                type="button"
                aria-label="Dismiss"
                onClick={() => setOpen(false)}
                className="flex size-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                <X className="size-3.5" aria-hidden />
              </button>
            </div>
          </div>

          <div className="mt-2.5 text-[13.5px] font-medium leading-relaxed text-foreground [&_.markdown]:text-[13.5px]">
            <ChatMarkdown content={heading} />
          </div>
        </div>

        {/* Options list */}
        {choices.length >= 2 ? (
          <div className="flex flex-col gap-1.5 p-3" role="listbox" aria-label={heading}>
            {choices.map((label, index) => {
              const selected = active === label;
              return (
                <button
                  key={`${index}-${label}`}
                  type="button"
                  role="option"
                  aria-selected={selected}
                  disabled={frozen}
                  onClick={() => handlePick(label)}
                  className={`group/opt flex min-h-10 items-center justify-between gap-3 rounded-xl border p-2.5 text-left transition-all ${
                    selected
                      ? "border-indigo-500 bg-indigo-50/70 dark:border-indigo-500 dark:bg-indigo-950/40 shadow-sm"
                      : "border-border/60 bg-muted/30 hover:border-indigo-500/40 hover:bg-muted/80"
                  } disabled:cursor-default disabled:hover:border-border/60 disabled:hover:bg-muted/30`}
                >
                  <div className="flex min-w-0 items-center gap-2.5">
                    <span
                      className={`flex size-5 shrink-0 items-center justify-center rounded-md font-mono text-[11px] font-semibold tabular-nums transition-colors ${
                        selected
                          ? "bg-indigo-600 text-white"
                          : "bg-muted text-muted-foreground group-hover/opt:bg-indigo-500/10 group-hover/opt:text-indigo-600 dark:group-hover/opt:text-indigo-400"
                      }`}
                    >
                      {index + 1}
                    </span>
                    <span
                      className={`min-w-0 text-[13px] leading-snug ${
                        selected ? "font-semibold text-indigo-900 dark:text-indigo-200" : "text-foreground"
                      }`}
                    >
                      {label}
                    </span>
                  </div>

                  {selected ? (
                    <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-white">
                      <Check className="size-3" strokeWidth={3} aria-hidden />
                    </span>
                  ) : null}
                </button>
              );
            })}

            {customOpen ? (
              <label className="mt-2 flex items-center gap-2 rounded-xl border border-indigo-500/40 bg-background p-1.5 focus-within:ring-2 focus-within:ring-indigo-500/20">
                <input
                  ref={inputRef}
                  value={textAnswer}
                  onChange={(event) => setTextAnswer(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      handleSubmitCustom();
                    }
                  }}
                  placeholder="Type a custom answer…"
                  aria-label="Custom answer"
                  disabled={frozen || !onRespond}
                  className="min-w-0 flex-1 bg-transparent px-2 text-[13px] text-foreground outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50"
                />
                <button
                  type="button"
                  aria-label="Send answer"
                  disabled={!canSendCustom}
                  onClick={handleSubmitCustom}
                  className={`flex size-7 shrink-0 items-center justify-center rounded-lg transition-all ${
                    canSendCustom
                      ? "bg-indigo-600 text-white shadow hover:bg-indigo-700"
                      : "bg-muted text-muted-foreground opacity-50"
                  }`}
                >
                  <ArrowUp className="size-3.5" strokeWidth={2.5} aria-hidden />
                </button>
              </label>
            ) : null}
          </div>
        ) : sent ? (
          <div className="flex flex-col items-center justify-center gap-2 px-4 py-8">
            <span className="flex size-7 items-center justify-center rounded-full bg-emerald-500 text-white">
              <Check className="size-3.5" strokeWidth={3} aria-hidden />
            </span>
            <span className="text-[13px] font-semibold text-foreground">Answer submitted</span>
          </div>
        ) : timedOut ? (
          <div className="flex flex-col items-center justify-center gap-2 px-4 pb-8 pt-4">
            <span className="text-[13px] text-muted-foreground">No response in time</span>
          </div>
        ) : (
          <div className="p-3">
            <label className="flex items-center gap-2 rounded-xl border border-border/80 bg-background p-1.5 focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-500/20">
              <input
                ref={inputRef}
                value={textAnswer}
                onChange={(event) => setTextAnswer(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    handleSubmitCustom();
                  }
                }}
                placeholder="Type your response here…"
                aria-label="Your answer"
                disabled={frozen || !onRespond}
                className="min-w-0 flex-1 bg-transparent px-2 text-[13px] text-foreground outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50"
              />
              <button
                type="button"
                aria-label="Send answer"
                disabled={!canSendCustom}
                onClick={handleSubmitCustom}
                className={`flex size-7 shrink-0 items-center justify-center rounded-lg transition-all ${
                  canSendCustom
                    ? "bg-indigo-600 text-white shadow hover:bg-indigo-700"
                    : "bg-muted text-muted-foreground opacity-50"
                }`}
              >
                <ArrowUp className="size-3.5" strokeWidth={2.5} aria-hidden />
              </button>
            </label>
          </div>
        )}
      </div>
    </div>
  );
}
