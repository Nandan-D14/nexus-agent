/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { Bot, Check } from "lucide-react";
import { ChatMarkdown } from "@/components/chat-markdown";
import { Button } from "@/components/base/buttons/button";
import { Kbd } from "@/components/base/kbd/kbd";
import { cx } from "@/utils/cx";

type Props = {
  questionId: string;
  question: string;
  answered?: boolean;
  onRespond?: (questionId: string, answer: string) => void;
};

/**
 * Beautiful UI Recommendation Card chrome around free-text ask_user answers.
 * Option chips deferred until backend sends options[].
 */
export function AgentQuestionCard({
  questionId,
  question,
  answered = false,
  onRespond,
}: Props) {
  const [answer, setAnswer] = useState("");
  const [submitted, setSubmitted] = useState(answered);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const resolved = submitted || answered;
  const disabled = resolved || !onRespond;

  useEffect(() => {
    setSubmitted(answered);
  }, [answered]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el || resolved) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  }, [answer, resolved]);

  function handleSubmit() {
    const trimmed = answer.trim();
    if (!trimmed || !onRespond) return;
    setSubmitted(true);
    onRespond(questionId, trimmed);
  }

  return (
    <div
      className={cx(
        "relative w-full max-w-md space-y-3 rounded-2lg border bg-background-primary-default p-4 transition-all duration-300",
        resolved
          ? "border-blue-500/25"
          : "border-blue-500/35 shadow-[0_0_16px_rgba(51,146,255,0.08)]",
      )}
    >
      <div className="flex items-center gap-2.5">
        <div className="flex size-6 shrink-0 items-center justify-center rounded-md bg-linear-to-b from-blue-500 to-blue-600 text-white shadow-sm">
          <Bot className="size-3.5" aria-hidden />
        </div>
        <div className="flex items-center gap-2">
          <div
            className={cx(
              "size-1.5 rounded-full",
              resolved ? "bg-blue-500" : "animate-pulse bg-blue-500",
            )}
          />
          <span className="text-caption-2-bold tracking-[0.15em] text-blue-500 uppercase">
            Agent asks
          </span>
        </div>
      </div>

      <div className="text-body-medium text-text-primary [&_.markdown]:text-[14px] [&_.markdown]:leading-relaxed">
        <ChatMarkdown content={question} />
      </div>

      {!resolved ? (
        <div className="space-y-2">
          <div className="flex items-end gap-2">
            <textarea
              ref={textareaRef}
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit();
                }
              }}
              placeholder="Type your answer…"
              rows={1}
              disabled={disabled}
              className={cx(
                "min-h-9 flex-1 resize-none rounded-lg border border-separator-border",
                "bg-background-secondary-default px-3 py-2 text-body-medium text-text-primary",
                "placeholder:text-text-placeholder",
                "outline-none focus-visible:ring-2 focus-visible:ring-border-focus-ring",
                "disabled:cursor-not-allowed disabled:opacity-50",
              )}
            />
            <Button
              type="button"
              size="small"
              variant="primary"
              onClick={handleSubmit}
              disabled={disabled || !answer.trim()}
              aria-label="Send answer"
            >
              Send
            </Button>
          </div>
          <p className="flex items-center gap-1.5 text-caption-1-regular text-text-tertiary">
            <Kbd>↵</Kbd>
            <span>to send</span>
            <span>·</span>
            <Kbd>⇧↵</Kbd>
            <span>newline</span>
          </p>
        </div>
      ) : (
        <div className="flex items-center gap-2 rounded-lg bg-background-secondary-default px-3 py-2 text-body-2-regular text-text-secondary">
          <Check className="size-3.5 shrink-0 text-emerald-500" aria-hidden />
          <span className="min-w-0 truncate">
            {answer.trim()
              ? `Answer sent: ${answer.trim()}`
              : "Answer sent"}
          </span>
        </div>
      )}
    </div>
  );
}
