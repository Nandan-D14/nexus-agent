/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowUp, Check, X } from "lucide-react";
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
        className="rounded-lg bg-background-primary-default px-3 py-2 text-[12.5px] font-medium text-text-primary shadow-card transition-colors duration-150 hover:bg-background-primary-hover"
      >
        Open question
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
      className="flex w-full max-w-[24rem] flex-col items-stretch outline-none animate-fade-up"
    >
      <div className="w-full self-start overflow-hidden rounded-xl border border-separator-border bg-background-primary-default shadow-card">
        <div className="px-3.5 pt-3.5 pb-1.5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1 text-[13px] font-semibold text-text-primary [&_.markdown]:text-[13px] [&_.markdown]:leading-snug [&_.markdown]:font-semibold">
              <ChatMarkdown content={heading} />
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
          {!frozen ? (
            <p className="mt-1 font-mono text-[11px] tabular-nums text-text-tertiary" aria-live="polite">
              {formatCountdown(remaining)}
            </p>
          ) : timedOut ? (
            <p className="mt-1 text-[11px] text-text-tertiary">No answer in time</p>
          ) : null}
        </div>

        {choices.length >= 2 ? (
          <div className="flex flex-col px-1.5 pb-2" role="listbox" aria-label={heading}>
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
                  className="flex min-h-9 items-center gap-2.5 rounded-lg px-2.5 text-left transition-colors duration-100 hover:bg-background-primary-hover disabled:cursor-default disabled:hover:bg-transparent"
                >
                  <span className="flex size-5 shrink-0 items-center justify-center rounded-[5px] bg-background-secondary-default text-[11px] tabular-nums text-text-tertiary">
                    {index + 1}
                  </span>
                  <span
                    className={cx(
                      "min-w-0 flex-1 truncate text-[13px]",
                      selected ? "font-medium text-text-primary" : "text-text-tertiary",
                    )}
                  >
                    {label}
                  </span>
                  {selected ? (
                    <Check className="size-3.5 shrink-0 text-text-primary" strokeWidth={2.5} aria-hidden />
                  ) : null}
                </button>
              );
            })}
            {customOpen ? (
              <label className="mt-1 flex items-center gap-2 rounded-lg px-2.5 py-1">
                <span aria-hidden className="size-5 shrink-0" />
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
                  placeholder="Type your answer…"
                  aria-label="Custom answer"
                  disabled={frozen || !onRespond}
                  className="min-w-0 flex-1 bg-transparent text-[13px] text-text-primary outline-none placeholder:text-text-tertiary disabled:cursor-not-allowed disabled:opacity-50"
                />
                <button
                  type="button"
                  aria-label="Send answer"
                  disabled={!canSendCustom}
                  onClick={handleSubmitCustom}
                  className={cx(
                    "flex size-7 shrink-0 items-center justify-center rounded-[8px] transition-[background-color,color,transform] duration-200",
                    "enabled:active:scale-[0.96]",
                    canSendCustom
                      ? "bg-text-primary text-background-primary-default"
                      : "bg-background-secondary-default text-text-tertiary",
                  )}
                >
                  <ArrowUp className="size-3.5" strokeWidth={2.5} aria-hidden />
                </button>
              </label>
            ) : null}
          </div>
        ) : sent ? (
          <div className="flex flex-col items-center justify-center gap-2 px-4 py-8">
            <span className="flex size-6 items-center justify-center rounded-full bg-emerald-500 text-white animate-pop-in">
              <Check className="size-3" strokeWidth={3} aria-hidden />
            </span>
            <span className="text-[13px] font-medium text-text-primary">Answer sent</span>
          </div>
        ) : timedOut ? (
          <div className="flex flex-col items-center justify-center gap-2 px-4 pb-8 pt-2">
            <span className="text-[13px] font-medium text-text-secondary">No answer in time</span>
          </div>
        ) : (
          <div className="px-3.5 pb-3">
            <label className="flex items-center gap-2 rounded-lg py-1">
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
                placeholder="Type something…"
                aria-label="Your answer"
                disabled={frozen || !onRespond}
                className="min-w-0 flex-1 bg-transparent text-[13px] text-text-primary outline-none placeholder:text-text-tertiary disabled:cursor-not-allowed disabled:opacity-50"
              />
              <button
                type="button"
                aria-label="Send answer"
                disabled={!canSendCustom}
                onClick={handleSubmitCustom}
                className={cx(
                  "flex size-7 items-center justify-center rounded-[8px] transition-[background-color,color,transform] duration-200",
                  "enabled:active:scale-[0.96]",
                  canSendCustom
                    ? "bg-text-primary text-background-primary-default"
                    : "bg-background-secondary-default text-text-tertiary",
                )}
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
