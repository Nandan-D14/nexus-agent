/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { ArrowUpRight } from "lucide-react";
import { cx } from "@/utils/cx";

export type CiteRef = {
  n: number;
  label: string;
  host: string;
  url: string;
};

const MD_LINK_RE = /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g;

function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** Extract unique markdown links in first-seen order as numbered citations. */
export function extractMarkdownCitations(content: string): {
  citationMap: Map<string, number>;
  refs: CiteRef[];
} {
  const citationMap = new Map<string, number>();
  const refs: CiteRef[] = [];
  let match: RegExpExecArray | null;
  const re = new RegExp(MD_LINK_RE.source, "g");
  while ((match = re.exec(content)) !== null) {
    const label = match[1]?.trim() || "";
    const url = match[2]?.trim() || "";
    if (!url || citationMap.has(url)) continue;
    const n = refs.length + 1;
    citationMap.set(url, n);
    refs.push({
      n,
      label: label || hostname(url),
      host: hostname(url),
      url,
    });
  }
  return { citationMap, refs };
}

type Props = {
  refs: CiteRef[];
  className?: string;
};

/** AICSS Inline Citations — numbered source footer under agent prose. */
export function InlineCitations({ refs, className }: Props) {
  if (refs.length === 0) return null;

  return (
    <div
      className={cx(
        "mt-3 flex flex-col gap-1.5 border-t border-separator-border pt-3",
        className,
      )}
    >
      <span className="text-caption-1-semibold tracking-wide text-text-tertiary uppercase">
        Sources
      </span>
      <div className="flex flex-col gap-1">
        {refs.map((ref, index) => (
          <a
            key={ref.url}
            id={`cite-ref-${ref.n}`}
            href={ref.url}
            target="_blank"
            rel="noopener noreferrer"
            className="animate-source-chip-in group flex min-w-0 items-center gap-2 rounded-lg px-1.5 py-1 text-body-2-regular transition-colors hover:bg-background-secondary-hover"
            style={{ animationDelay: `${index * 40}ms` }}
          >
            <span className="inline-flex size-5 shrink-0 items-center justify-center rounded-md bg-background-tertiary-default text-[10px] font-semibold text-text-secondary">
              {ref.n}
            </span>
            <span className="min-w-0 flex-1 truncate text-text-primary">
              {ref.label}
            </span>
            <span className="shrink-0 text-text-tertiary">·</span>
            <span className="shrink-0 font-mono text-caption-1-regular text-text-tertiary">
              {ref.host}
            </span>
            <ArrowUpRight className="size-3 shrink-0 text-foreground-icon-tertiary opacity-0 transition-opacity group-hover:opacity-100" />
          </a>
        ))}
      </div>
    </div>
  );
}
