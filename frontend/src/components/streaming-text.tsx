/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Check,
  Clipboard,
  RotateCcw,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { TextResponse } from "@/components/agent-ui/text-response";
import {
  extractMarkdownCitations,
  type CiteRef,
} from "@/components/agent-ui/inline-citations";
import type { SearchCiteRef } from "@/lib/search-result-utils";
import { cx } from "@/utils/cx";

const WORD_MS = 80;

type Props = {
  text: string;
  isStreaming: boolean;
  className?: string;
  /** Search / tool results to merge into the Sources UI (markdown citations win on URL clash). */
  extraSources?: SearchCiteRef[];
};

type RevealToken =
  | { kind: "word"; text: string }
  | { kind: "cite"; ref: CiteRef };

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return reduced;
}

/** Structured markdown that would look broken as word spans. */
function isMarkdownHeavy(text: string): boolean {
  return (
    /```/.test(text) ||
    /^\s{0,3}#{1,6}\s/m.test(text) ||
    /^\s*\|.+\|/m.test(text) ||
    /^\s*>\s/m.test(text)
  );
}

/**
 * Build demo-like reveal tokens from real agent text:
 * markdown links → label words + first citation as an inline SourceChip slot.
 */
function buildRevealTokens(text: string, refs: CiteRef[]): RevealToken[] {
  const tokens: RevealToken[] = [];
  const re = /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let insertedCite = false;

  const pushPlain = (chunk: string) => {
    const words = chunk.match(/\S+\s*/g) ?? [];
    for (const w of words) {
      tokens.push({ kind: "word", text: w });
    }
  };

  const stripInline = (chunk: string) =>
    chunk
      .replace(/`([^`]+)`/g, "$1")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/\*([^*]+)\*/g, "$1")
      .replace(/_([^_]+)_/g, "$1");

  while ((match = re.exec(text)) !== null) {
    pushPlain(stripInline(text.slice(last, match.index)));
    const label = match[1]?.trim() || "";
    const url = match[2]?.trim() || "";
    pushPlain(stripInline(label) + " ");
    if (!insertedCite && url) {
      const ref = refs.find((r) => r.url === url) ?? refs[0];
      if (ref) {
        tokens.push({ kind: "cite", ref });
        insertedCite = true;
      }
    }
    last = match.index + match[0].length;
  }
  pushPlain(stripInline(text.slice(last)));
  return tokens;
}

function faviconUrl(host: string): string {
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=32`;
}

function wordPrefix(text: string, count: number): string {
  const words = text.match(/\S+\s*/g) ?? (text ? [text] : []);
  if (count >= words.length) return text;
  return words.slice(0, Math.max(0, count)).join("");
}

/** Markdown citations first; append search-only URLs. Prefer markdown label on clash. */
function mergeCitationRefs(
  text: string,
  extraSources?: SearchCiteRef[],
): CiteRef[] {
  const { refs: markdownRefs } = extractMarkdownCitations(text);
  if (!extraSources?.length) return markdownRefs;

  const seen = new Set(markdownRefs.map((r) => r.url));
  const merged = [...markdownRefs];
  for (const src of extraSources) {
    if (!src.url || seen.has(src.url)) continue;
    seen.add(src.url);
    merged.push({
      n: merged.length + 1,
      label: src.label || src.host,
      host: src.host,
      url: src.url,
    });
  }
  return merged;
}

/**
 * Agent answer shell — demo-style word fade-in while streaming, then
 * Copy / Retry / thumbs + expandable sources (BoardUI tokens).
 */
export function StreamingText({
  text,
  isStreaming,
  className,
  extraSources,
}: Props) {
  const reducedMotion = usePrefersReducedMotion();
  const refs = useMemo(
    () => mergeCitationRefs(text, extraSources),
    [text, extraSources],
  );
  const heavyMd = useMemo(() => isMarkdownHeavy(text), [text]);
  const revealTokens = useMemo(() => buildRevealTokens(text, refs), [text, refs]);
  const totalTokens = revealTokens.length;
  const totalWords = useMemo(() => {
    const words = text.match(/\S+\s*/g);
    return words?.length ?? (text ? 1 : 0);
  }, [text]);

  const shouldAnimate = isStreaming && !reducedMotion;
  const useWordSpans = shouldAnimate && !heavyMd;

  const [visibleCount, setVisibleCount] = useState(() =>
    shouldAnimate ? 0 : useWordSpans ? totalTokens : totalWords,
  );
  const [copied, setCopied] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);

  useEffect(() => {
    if (!shouldAnimate) {
      setVisibleCount(useWordSpans ? totalTokens : totalWords);
      return;
    }
    setVisibleCount(0);
  }, [text, shouldAnimate, totalTokens, totalWords, useWordSpans]);

  const animateTotal = useWordSpans ? totalTokens : totalWords;

  useEffect(() => {
    if (!shouldAnimate) return;
    if (visibleCount >= animateTotal) return;
    const id = window.setTimeout(() => {
      setVisibleCount((c) => Math.min(c + 1, animateTotal));
    }, WORD_MS);
    return () => window.clearTimeout(id);
  }, [shouldAnimate, visibleCount, animateTotal]);

  useEffect(() => {
    if (!copied) return;
    const id = window.setTimeout(() => setCopied(false), 1600);
    return () => window.clearTimeout(id);
  }, [copied]);

  const revealDone = !shouldAnimate || visibleCount >= animateTotal;
  const showCaret = shouldAnimate && !revealDone;
  const showActions = revealDone;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      // Clipboard may be denied; leave UI unchanged.
    }
  };

  return (
    <div className={cx("relative w-full", className)}>
      {/* Prose */}
      {revealDone || !shouldAnimate ? (
        <TextResponse content={text} hideCitations />
      ) : useWordSpans ? (
        <p className="m-0 text-[15px] leading-[1.75] font-medium text-text-primary">
          {revealTokens.slice(0, visibleCount).map((token, i) =>
            token.kind === "cite" ? (
              <SourceChip key={`cite-${token.ref.url}-${i}`} refItem={token.ref} />
            ) : (
              <span
                key={`w-${i}`}
                className="inline animate-fade-in"
                style={{ animationDuration: "250ms" }}
              >
                {token.text}
              </span>
            ),
          )}
          {showCaret ? <StreamCaret /> : null}
        </p>
      ) : (
        <div>
          <TextResponse content={wordPrefix(text, visibleCount)} hideCitations />
          {showCaret ? <StreamCaret /> : null}
        </div>
      )}

      {/* Action icons + sources toggle — demo layout */}
      <div
        className="mt-2 flex items-center gap-0.5 transition-opacity duration-[400ms]"
        style={{
          opacity: showActions ? 1 : 0,
          pointerEvents: showActions ? "auto" : "none",
        }}
        aria-hidden={!showActions}
      >
        <ActionIconButton
          label={copied ? "Copied" : "Copy response"}
          onClick={handleCopy}
        >
          {copied ? (
            <Check className="size-[15px] text-emerald-500" aria-hidden />
          ) : (
            <Clipboard className="size-[15px]" aria-hidden />
          )}
        </ActionIconButton>
        <ActionIconButton label="Retry" title="Coming soon" disabled>
          <RotateCcw className="size-[15px]" aria-hidden />
        </ActionIconButton>
        <ActionIconButton label="Thumbs up" title="Coming soon" disabled>
          <ThumbsUp className="size-[15px]" aria-hidden />
        </ActionIconButton>
        <ActionIconButton label="Thumbs down" title="Coming soon" disabled>
          <ThumbsDown className="size-[15px]" aria-hidden />
        </ActionIconButton>

        {refs.length > 0 ? (
          <button
            type="button"
            aria-expanded={sourcesOpen}
            onClick={() => setSourcesOpen((o) => !o)}
            className="ml-1.5 flex items-center gap-1.5 rounded-[6px] px-1 py-0.5 text-left transition-colors duration-150 hover:bg-background-secondary-hover"
          >
            <span className="flex -space-x-1" aria-hidden>
              {refs.slice(0, 3).map((ref) => (
                <SourceFavicon key={ref.url} host={ref.host} size="sm" stacked />
              ))}
            </span>
            <span className="text-[12px] text-text-secondary">
              {refs.length} {refs.length === 1 ? "source" : "sources"}
            </span>
          </button>
        ) : null}
      </div>

      {/* Expandable sources — grid collapse like demo */}
      {refs.length > 0 ? (
        <div
          className="grid transition-[grid-template-rows,opacity] duration-300"
          style={{
            gridTemplateRows: showActions && sourcesOpen ? "1fr" : "0fr",
            opacity: showActions && sourcesOpen ? 1 : 0,
            transitionTimingFunction: "cubic-bezier(0.23, 1, 0.32, 1)",
          }}
        >
          <div className="overflow-hidden">
            <div className="mt-1.5 flex flex-col rounded-lg bg-background-secondary-default p-1 shadow-card">
              {refs.map((ref) => (
                <a
                  key={ref.url}
                  id={`cite-ref-${ref.n}`}
                  href={ref.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 rounded-[6px] px-1.5 py-1 text-[12px] text-text-secondary transition-colors duration-150 hover:bg-background-secondary-hover hover:text-text-primary"
                >
                  <SourceFavicon host={ref.host} size="md" rounded="sm" />
                  <span className="min-w-0 flex-1 truncate">{ref.label}</span>
                  <span className="ml-auto shrink-0 font-mono text-[10.5px] text-text-tertiary">
                    {ref.host}
                  </span>
                </a>
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function StreamCaret() {
  return (
    <span
      className="animate-fade-in ml-0.5 inline-block h-3 w-0.5 translate-y-0.5 rounded-full bg-text-primary"
      style={{ animationDuration: "150ms" }}
      aria-hidden
    />
  );
}

function ActionIconButton({
  children,
  label,
  onClick,
  disabled,
  title,
}: {
  children: ReactNode;
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={title ?? label}
      disabled={disabled}
      onClick={onClick}
      className={cx(
        "flex size-6 items-center justify-center rounded-[6px] text-text-tertiary transition-colors duration-100",
        disabled
          ? "cursor-default opacity-50"
          : "hover:bg-background-tertiary-hover hover:text-text-secondary",
      )}
    >
      {children}
    </button>
  );
}

function SourceChip({ refItem }: { refItem: CiteRef }) {
  return (
    <a
      href={refItem.url}
      target="_blank"
      rel="noopener noreferrer"
      className="ml-0 mr-1 inline-flex h-[18px] translate-y-[-1px] items-center gap-1 rounded-[5px] bg-background-secondary-default pr-1.5 pl-[3px] align-middle font-mono text-[10.5px] text-text-secondary shadow-card transition-colors duration-150 hover:bg-background-secondary-hover hover:text-text-primary animate-pop-in"
      style={{ animationDuration: "250ms" }}
    >
      <SourceFavicon host={refItem.host} size="xs" rounded="sm" />
      <span>{refItem.host}</span>
    </a>
  );
}

function SourceFavicon({
  host,
  size = "sm",
  stacked = false,
  rounded = "full",
}: {
  host: string;
  size?: "xs" | "sm" | "md";
  stacked?: boolean;
  rounded?: "full" | "sm";
}) {
  const [failed, setFailed] = useState(false);
  const dim =
    size === "md" ? "size-4" : size === "xs" ? "size-3" : "size-3.5";
  const radius = rounded === "sm" ? "rounded-[3px]" : "rounded-full";

  if (failed) {
    return (
      <span
        className={cx(
          dim,
          radius,
          "inline-flex shrink-0 items-center justify-center border border-separator-border bg-background-tertiary-default text-[8px] font-semibold uppercase text-text-tertiary",
          stacked && "bg-background-primary-default shadow-[0_0_0_1.5px_var(--color-background-primary-default)]",
        )}
        aria-hidden
      >
        {host.charAt(0) || "?"}
      </span>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element -- remote favicon URLs
    <img
      src={faviconUrl(host)}
      alt=""
      width={size === "md" ? 16 : size === "xs" ? 12 : 14}
      height={size === "md" ? 16 : size === "xs" ? 12 : 14}
      className={cx(
        dim,
        radius,
        "shrink-0 bg-background-secondary-default",
        stacked &&
          "bg-background-primary-default shadow-[0_0_0_1.5px_var(--color-background-primary-default)]",
      )}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}
