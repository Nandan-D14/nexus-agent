/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
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

type Props = {
  text: string;
  isStreaming: boolean;
  className?: string;
  extraSources?: SearchCiteRef[];
};

function mergeCitationRefs(
  text: string,
  extraSources?: SearchCiteRef[],
): CiteRef[] {
  const { refs: markdownRefs } = extractMarkdownCitations(text);
  if (!extraSources?.length) return markdownRefs;
  const merged: CiteRef[] = markdownRefs.map((r) => ({ ...r }));
  const byUrl = new Map(merged.map((r) => [r.url, r]));
  for (const src of extraSources) {
    if (!src.url) continue;
    const existing = byUrl.get(src.url);
    if (existing) {
      if (!existing.description && src.description) existing.description = src.description;
      continue;
    }
    const ref: CiteRef = {
      n: merged.length + 1,
      label: src.label || src.host,
      host: src.host,
      url: src.url,
      description: src.description,
    };
    merged.push(ref);
    byUrl.set(src.url, ref);
  }
  return merged;
}

function faviconUrl(host: string): string {
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=32`;
}

export function StreamingText({
  text,
  isStreaming,
  className,
  extraSources,
}: Props) {
  const refs = useMemo(() => mergeCitationRefs(text, extraSources), [text, extraSources]);
  const [copied, setCopied] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const id = window.setTimeout(() => setCopied(false), 1600);
    return () => window.clearTimeout(id);
  }, [copied]);

  const showCaret = isStreaming;
  const showActions = !isStreaming;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {}
  };

  return (
    <div className={cx("relative w-full", className)}>
      <div className="relative">
        <TextResponse content={text} hideCitations sources={refs} />
        {showCaret ? <StreamCaret /> : null}
      </div>
      <div
        className="mt-2 flex items-center gap-0.5 transition-opacity duration-200"
        style={{
          opacity: showActions ? 1 : 0,
          pointerEvents: showActions ? "auto" : "none",
        }}
        aria-hidden={!showActions}
      >
        <ActionIconButton label={copied ? "Copied" : "Copy response"} onClick={handleCopy}>
          {copied ? <Check className="size-[15px] text-emerald-500" aria-hidden /> : <Clipboard className="size-[15px]" aria-hidden />}
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
                  <span className="ml-auto shrink-0 font-mono text-[10.5px] text-text-tertiary">{ref.host}</span>
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
    <span className="ml-0.5 inline-block h-3 w-0.5 translate-y-0.5 animate-pulse rounded-full bg-text-primary" aria-hidden />
  );
}

function ActionIconButton({ children, label, onClick, disabled, title }: { children: ReactNode; label: string; onClick?: () => void; disabled?: boolean; title?: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={title ?? label}
      disabled={disabled}
      onClick={onClick}
      className={cx(
        "flex size-6 items-center justify-center rounded-[6px] text-text-tertiary transition-colors duration-100",
        disabled ? "cursor-default opacity-50" : "hover:bg-background-tertiary-hover hover:text-text-secondary",
      )}
    >
      {children}
    </button>
  );
}

function SourceFavicon({ host, size = "sm", stacked = false, rounded = "full" }: { host: string; size?: "xs" | "sm" | "md"; stacked?: boolean; rounded?: "full" | "sm" }) {
  const [failed, setFailed] = useState(false);
  const dim = size === "md" ? "size-4" : size === "xs" ? "size-3" : "size-3.5";
  const radius = rounded === "sm" ? "rounded-[3px]" : "rounded-full";
  if (failed) {
    return (
      <span className={cx(dim, radius, "inline-flex shrink-0 items-center justify-center border border-separator-border bg-background-tertiary-default text-[8px] font-semibold uppercase text-text-tertiary", stacked && "bg-background-primary-default shadow-[0_0_0_1.5px_var(--color-background-primary-default)]")} aria-hidden>
        {host.charAt(0) || "?"}
      </span>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={faviconUrl(host)}
      alt=""
      width={size === "md" ? 16 : size === "xs" ? 12 : 14}
      height={size === "md" ? 16 : size === "xs" ? 12 : 14}
      className={cx(dim, radius, "shrink-0 bg-background-secondary-default", stacked && "bg-background-primary-default shadow-[0_0_0_1.5px_var(--color-background-primary-default)]")}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}
