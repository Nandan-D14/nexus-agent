/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { ArrowUpRight, Globe, Loader2 } from "lucide-react";
import type { SearchResult } from "@/lib/search-result-utils";
import { cx } from "@/utils/cx";

type Props = {
  query?: string | null;
  results: SearchResult[];
  isRunning?: boolean;
};

function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function faviconUrl(url: string): string {
  const host = hostname(url);
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=32`;
}

/** AICSS Web Search — query header + result rows with title/snippet/host. */
export function WebSearchCard({ query, results, isRunning }: Props) {
  return (
    <div className="flex w-full max-w-xl flex-col gap-2.5">
      <div className="flex min-w-0 items-center gap-2 text-body-medium text-text-secondary">
        <Globe className="size-4 shrink-0 text-foreground-icon-secondary" aria-hidden />
        <span className="min-w-0 truncate">
          <span className="text-text-tertiary">Web search</span>
          {query ? (
            <>
              {" "}
              <span className="text-text-primary">
                &ldquo;{query}&rdquo;
              </span>
            </>
          ) : null}
        </span>
        {isRunning ? (
          <Loader2 className="ml-auto size-3.5 shrink-0 animate-spin text-blue-500" />
        ) : null}
      </div>

      {results.length > 0 ? (
        <ul className="divide-y divide-separator-border overflow-hidden rounded-2lg border border-separator-border bg-background-primary-default">
          {results.map((result, index) => {
            const host = hostname(result.url);
            return (
              <li key={`${result.url}-${index}`}>
                <a
                  href={result.url || undefined}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={cx(
                    "group flex flex-col gap-0.5 px-3.5 py-2.5 transition-colors",
                    "hover:bg-background-secondary-hover",
                    !result.url && "pointer-events-none",
                  )}
                >
                  <div className="flex min-w-0 items-center gap-2">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={faviconUrl(result.url || host)}
                      alt=""
                      width={16}
                      height={16}
                      className="size-4 shrink-0 rounded-sm"
                    />
                    <span className="min-w-0 flex-1 truncate text-body-semibold text-text-primary">
                      {result.title || host || "Result"}
                    </span>
                    <ArrowUpRight className="size-3.5 shrink-0 text-foreground-icon-tertiary opacity-0 transition-opacity group-hover:opacity-100" />
                  </div>
                  {result.snippet ? (
                    <p className="line-clamp-2 pl-6 text-body-2-regular text-text-secondary">
                      {result.snippet}
                    </p>
                  ) : null}
                  {host ? (
                    <span className="pl-6 font-mono text-caption-1-regular text-text-tertiary">
                      {host}
                    </span>
                  ) : null}
                </a>
              </li>
            );
          })}
        </ul>
      ) : isRunning ? (
        <p className="pl-6 text-body-2-regular text-text-tertiary">Searching…</p>
      ) : null}
    </div>
  );
}
