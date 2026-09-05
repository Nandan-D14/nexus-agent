/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CornerDownLeft, LayoutGrid, Pencil, X, Check, Clock, Plug } from "lucide-react";
import { providerLogo } from "@/lib/connectors";
import { ChatMarkdown } from "@/components/chat-markdown";
import { cx } from "@/utils/cx";

export type SuggestionItem = {
  name: string;
  description: string;
  action_label?: string;
};

export type ElicitationProps = {
  elicitationId: string;
  mode?: "choice" | "suggestion";
  /** Choice mode */
  question?: string;
  options?: string[];
  allowFreeText?: boolean;
  /** Suggestion mode */
  title?: string;
  items?: SuggestionItem[];
  /** State */
  answer?: string;
  answered?: boolean;
  timedOut?: boolean;
  timeoutSeconds?: number;
  issuedAt?: number;
  onRespond?: (elicitationId: string, answer: string) => void;
};

const DEFAULT_TIMEOUT_SECONDS = 300;

function resolveItemLogo(name: string): string | null {
  const clean = name.toLowerCase().replace(/[\s_-]+/g, "_").trim();
  if (clean.includes("gmail")) return providerLogo("gmail");
  if (clean.includes("drive") || clean.includes("google_drive")) return providerLogo("google_drive");
  if (clean.includes("calendar")) return providerLogo("google_calendar");
  if (clean.includes("tasks")) return providerLogo("google_tasks");
  if (clean.includes("github")) return providerLogo("github");
  if (clean.includes("slack")) return providerLogo("slack");
  if (clean.includes("linear")) return providerLogo("linear");
  if (clean.includes("tavily")) return providerLogo("tavily");
  if (clean.includes("exa")) return providerLogo("exa");
  if (clean.includes("stripe")) return providerLogo("stripe");
  if (clean.includes("vercel")) return providerLogo("vercel");
  if (clean.includes("cloudflare")) return providerLogo("cloudflare");
  return providerLogo(clean) || null;
}

function formatCountdown(seconds: number): string {
  const s = Math.max(0, Math.ceil(seconds));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

export function ElicitationUI({
  elicitationId,
  mode = "choice",
  question = "",
  options = [],
  allowFreeText = true,
  title = "Connectors that could help",
  items = [],
  answer: answerProp,
  answered = false,
  timedOut: timedOutProp = false,
  timeoutSeconds = DEFAULT_TIMEOUT_SECONDS,
  issuedAt,
  onRespond,
}: ElicitationProps) {
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(answerProp ?? null);
  const [submitted, setSubmitted] = useState(answered);
  const [freeText, setFreeText] = useState("");
  const [dismissed, setDismissed] = useState(false);
  const [localTimedOut, setLocalTimedOut] = useState(timedOutProp);
  const [remaining, setRemaining] = useState(timeoutSeconds);
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null);

  const startRef = useRef(issuedAt ?? Date.now());
  const cardRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const sent = submitted || answered;
  const timedOut = !sent && (timedOutProp || localTimedOut);
  const frozen = sent || timedOut;
  const budget = Math.max(1, timeoutSeconds || DEFAULT_TIMEOUT_SECONDS);

  const choices = useMemo(() => {
    return (options || []).slice(0, 4);
  }, [options]);

  useEffect(() => {
    setSubmitted(answered);
  }, [answered]);

  useEffect(() => {
    if (answerProp) setSelectedAnswer(answerProp);
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
  }, [budget, frozen, elicitationId, issuedAt]);

  function commit(value: string) {
    const trimmed = value.trim();
    if (!trimmed || !onRespond || frozen) return;
    setSelectedAnswer(trimmed);
    setSubmitted(true);
    onRespond(elicitationId, trimmed);
  }

  function handleChoiceClick(label: string) {
    if (frozen) return;
    commit(label);
  }

  function handleSkip() {
    if (frozen) return;
    commit("Skip");
  }

  function handleCustomSubmit() {
    if (frozen || !freeText.trim()) return;
    commit(freeText);
  }

  function handleSuggestionClick(item: SuggestionItem) {
    if (frozen) return;
    commit(`Connect ${item.name}`);
  }

  if (dismissed) {
    return (
      <button
        type="button"
        onClick={() => setDismissed(false)}
        className="flex items-center gap-1.5 rounded-lg border border-border/70 bg-zinc-900/90 px-3 py-1.5 text-[12px] font-medium text-zinc-300 shadow-sm transition-colors hover:bg-zinc-800"
      >
        <LayoutGrid className="size-3.5 text-indigo-400" />
        <span>{mode === "suggestion" ? "Show connectors" : "Show choices"}</span>
      </button>
    );
  }

  return (
    <div
      ref={cardRef}
      tabIndex={frozen ? -1 : 0}
      onKeyDown={(e) => {
        if (frozen) return;
        if (e.target instanceof HTMLInputElement) return;
        const num = Number(e.key);
        if (num >= 1 && num <= choices.length) {
          e.preventDefault();
          commit(choices[num - 1]);
        }
      }}
      className="flex w-full max-w-[32rem] flex-col items-stretch outline-none animate-fade-up"
    >
      <div className="w-full overflow-hidden rounded-2xl border border-zinc-800 bg-[#18181b] p-4 text-zinc-100 shadow-xl dark:border-zinc-800/80">
        {/* Header Bar */}
        <div className="flex items-start justify-between gap-3 pb-3">
          <div className="flex-1 pr-2">
            {mode === "suggestion" ? (
              <div className="flex items-center gap-2">
                <span className="text-[14.5px] font-semibold text-zinc-100">{title}</span>
              </div>
            ) : (
              <div className="text-[14.5px] font-medium leading-snug text-zinc-100">
                <ChatMarkdown content={question} />
              </div>
            )}
          </div>

          <div className="flex items-center gap-2 shrink-0 pt-0.5">
            {!frozen && remaining <= 60 && (
              <span className="flex items-center gap-1 font-mono text-[11px] font-medium text-amber-400">
                <Clock className="size-3" />
                {formatCountdown(remaining)}
              </span>
            )}
            {mode === "suggestion" && (
              <LayoutGrid className="size-4 text-zinc-400" aria-hidden />
            )}
            <button
              type="button"
              aria-label="Dismiss"
              onClick={() => setDismissed(true)}
              className="flex size-5 items-center justify-center rounded text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
            >
              <X className="size-3.5" />
            </button>
          </div>
        </div>

        {/* Choice Mode Content */}
        {mode === "choice" && (
          <div className="flex flex-col gap-1.5 pt-1">
            {choices.map((label, index) => {
              const num = index + 1;
              const isSelected = selectedAnswer === label;
              const isFocused = focusedIndex === index;

              return (
                <button
                  key={`${index}-${label}`}
                  type="button"
                  disabled={frozen}
                  onClick={() => handleChoiceClick(label)}
                  onMouseEnter={() => setFocusedIndex(index)}
                  onMouseLeave={() => setFocusedIndex(null)}
                  className={cx(
                    "group flex min-h-10 items-center justify-between gap-3 rounded-xl px-3 py-2 text-left transition-all",
                    isSelected
                      ? "bg-zinc-800 border border-zinc-700 text-white shadow-sm"
                      : "bg-zinc-900/50 hover:bg-zinc-800/60 text-zinc-200 border border-transparent",
                    frozen && !isSelected && "opacity-50 cursor-default hover:bg-zinc-900/50"
                  )}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span
                      className={cx(
                        "flex size-6 shrink-0 items-center justify-center rounded-md font-mono text-[11.5px] font-semibold",
                        isSelected
                          ? "bg-zinc-700 text-white"
                          : "bg-zinc-800/80 text-zinc-400 group-hover:text-zinc-200"
                      )}
                    >
                      {num}
                    </span>
                    <span className="text-[13.5px] truncate font-normal">{label}</span>
                  </div>

                  {isSelected ? (
                    <Check className="size-3.5 text-emerald-400 shrink-0" />
                  ) : isFocused && !frozen ? (
                    <CornerDownLeft className="size-3.5 text-zinc-400 shrink-0 transition-opacity opacity-80" />
                  ) : null}
                </button>
              );
            })}

            {/* Custom Answer / Skip Row */}
            {allowFreeText && (
              <div
                className={cx(
                  "mt-1 flex items-center justify-between gap-2 rounded-xl bg-zinc-900/40 px-3 py-1.5 border border-zinc-800/60",
                  frozen && "opacity-50"
                )}
              >
                <div className="flex flex-1 items-center gap-2.5">
                  <Pencil className="size-3.5 text-zinc-400 shrink-0" />
                  <input
                    ref={inputRef}
                    type="text"
                    disabled={frozen}
                    placeholder="Something else"
                    value={freeText}
                    onChange={(e) => setFreeText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        handleCustomSubmit();
                      }
                    }}
                    className="w-full bg-transparent text-[13px] text-zinc-200 placeholder:text-zinc-500 outline-none disabled:cursor-not-allowed"
                  />
                </div>

                {freeText.trim() && !frozen ? (
                  <button
                    type="button"
                    onClick={handleCustomSubmit}
                    className="rounded-md bg-zinc-800 px-2.5 py-1 text-[11.5px] font-medium text-zinc-200 hover:bg-zinc-700 hover:text-white transition-colors"
                  >
                    Submit
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled={frozen}
                    onClick={handleSkip}
                    className="rounded-md bg-zinc-800/70 px-2.5 py-1 text-[11.5px] font-medium text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200 transition-colors disabled:cursor-not-allowed"
                  >
                    Skip
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {/* Suggestion Mode Content */}
        {mode === "suggestion" && (
          <div className="flex flex-col gap-2 pt-1">
            {items.map((item, index) => {
              const logoUrl = resolveItemLogo(item.name);
              const isSelected = selectedAnswer === `Connect ${item.name}` || selectedAnswer === item.name;

              return (
                <div
                  key={`${index}-${item.name}`}
                  className={cx(
                    "flex items-center justify-between gap-3 rounded-xl p-3 transition-colors border",
                    isSelected
                      ? "bg-zinc-800/80 border-zinc-700"
                      : "bg-zinc-900/40 border-zinc-800/60 hover:bg-zinc-800/40"
                  )}
                >
                  <div className="flex items-center gap-3.5 min-w-0">
                    <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-zinc-800/80 p-1.5">
                      {logoUrl ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={logoUrl}
                          alt={item.name}
                          className="size-6 object-contain"
                        />
                      ) : (
                        <Plug className="size-4 text-zinc-400" />
                      )}
                    </div>

                    <div className="flex flex-col min-w-0">
                      <span className="text-[13.5px] font-semibold text-zinc-100 truncate">
                        {item.name}
                      </span>
                      <span className="text-[12px] text-zinc-400 line-clamp-1">
                        {item.description}
                      </span>
                    </div>
                  </div>

                  <button
                    type="button"
                    disabled={frozen}
                    onClick={() => handleSuggestionClick(item)}
                    className={cx(
                      "shrink-0 rounded-lg px-3.5 py-1.5 text-[12.5px] font-medium transition-colors border",
                      isSelected
                        ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
                        : "bg-zinc-800 text-zinc-200 border-zinc-700 hover:bg-zinc-700 hover:text-white",
                      frozen && !isSelected && "opacity-50 cursor-default hover:bg-zinc-800"
                    )}
                  >
                    {isSelected ? (
                      <span className="flex items-center gap-1">
                        <Check className="size-3 text-emerald-400" />
                        <span>Connected</span>
                      </span>
                    ) : (
                      item.action_label || "Connect"
                    )}
                  </button>
                </div>
              );
            })}
          </div>
        )}

        {/* Resolved Footer Note */}
        {sent && selectedAnswer && (
          <div className="mt-3 flex items-center gap-1.5 border-t border-zinc-800/80 pt-2 text-[11.5px] text-zinc-400">
            <Check className="size-3.5 text-emerald-400" />
            <span>Selected: {selectedAnswer}</span>
          </div>
        )}
        {timedOut && (
          <div className="mt-3 flex items-center gap-1.5 border-t border-zinc-800/80 pt-2 text-[11.5px] text-zinc-500">
            <Clock className="size-3.5 text-zinc-500" />
            <span>Timed out</span>
          </div>
        )}
      </div>
    </div>
  );
}
