/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useMemo, useState } from "react";
import type { SearchResult } from "@/lib/search-result-utils";
import { cx } from "@/utils/cx";

type Props = {
  query?: string | null;
  results: SearchResult[];
  isRunning?: boolean;
};

type RowState = "pending" | "loading" | "done";

const STAGGER_MS = 110;
const HOLD_MS = 220;
const SKELETON_COUNT = 3;

function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function faviconUrl(host: string): string {
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=32`;
}

/** Site logo with a lettered fallback when the favicon service has nothing. */
function SiteFavicon({ host }: { host: string }) {
  const [failed, setFailed] = useState(false);

  if (!host || failed) {
    return (
      <span
        className="inline-flex size-4 shrink-0 items-center justify-center rounded-[3px] border border-separator-border bg-background-tertiary-default text-[8px] font-semibold uppercase text-text-tertiary"
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
      width={16}
      height={16}
      className="size-4 shrink-0 rounded-[3px] bg-background-secondary-default"
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}

const M = {
  L: "M6.057 11.565 C2.081 11.565 0.371 8.159 0.371 5.964 C0.371 3.642 2.152 0.329 6.05 0.329",
  ML: "M6.012 11.55 C4.575 10.496 3.333 8.116 3.321 5.964 C3.307 3.399 4.974 0.977 6.012 0.329",
  MR: "M6.012 11.55 C7.211 10.781 8.715 8.287 8.715 5.964 C8.715 3.399 7.24 1.233 6.012 0.329",
  R: "M6.012 11.55 C9.677 11.55 11.65 8.487 11.65 5.964 C11.65 3.499 9.748 0.329 6.012 0.329",
};

function GlobeIcon() {
  const values = [M.L, M.ML, M.MR, M.R, M.L].join(";");
  return (
    <svg
      viewBox="0 0 12 12"
      width="12"
      height="12"
      fill="none"
      stroke="currentColor"
      strokeWidth="0.85"
      strokeLinecap="round"
      className="overflow-visible"
      aria-hidden
    >
      <circle cx="6" cy="6" r="5.7" opacity="0.9" />
      <line x1="0.3" y1="6" x2="11.7" y2="6" opacity="0.9" />
      {["0s", "-1.2s", "-2.4s", "-3.6s", "-4.8s", "-6s"].map((begin) => (
        <path key={begin} d={M.L} opacity="0">
          <animate
            attributeName="d"
            dur="7.2s"
            begin={begin}
            repeatCount="indefinite"
            calcMode="spline"
            keyTimes="0;0.25;0.5;0.75;1"
            keySplines="0.42 0 0.58 1;0.42 0 0.58 1;0.42 0 0.58 1;0.42 0 0.58 1"
            values={values}
          />
          <animate
            attributeName="opacity"
            dur="7.2s"
            begin={begin}
            repeatCount="indefinite"
            calcMode="linear"
            keyTimes="0;0.05;0.7;0.75;1"
            values="0;0.9;0.9;0;0"
          />
        </path>
      ))}
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
    </svg>
  );
}

function CaretIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="10"
      height="10"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cx("transition-transform", open && "rotate-180")}
      aria-hidden
    >
      <path d="m4.5 15.75 7.5-7.5 7.5 7.5" />
    </svg>
  );
}

function ArrowUpIcon() {
  return (
    <svg
      width="10"
      height="10"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M4.5 10.5 12 3m0 0 7.5 7.5M12 3v18" />
    </svg>
  );
}

function DotsIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" aria-hidden>
      <circle
        cx="12"
        cy="12"
        r="9"
        strokeWidth="1.8"
        strokeDasharray="1.8 3.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
    </svg>
  );
}

function ResultBullet({ state }: { state: RowState }) {
  return (
    <span className="relative inline-flex size-4 shrink-0 items-center justify-center text-text-tertiary">
      <span
        className={cx(
          "absolute inset-0 flex items-center justify-center transition-opacity duration-200",
          state === "pending" ? "opacity-100" : "opacity-0",
        )}
      >
        <DotsIcon />
      </span>
      <span
        className={cx(
          "absolute inset-0 flex items-center justify-center transition-opacity duration-200",
          state === "loading" ? "opacity-100" : "opacity-0",
        )}
      >
        <GlobeIcon />
      </span>
      <span
        className={cx(
          "absolute inset-0 flex items-center justify-center text-emerald-500 transition-opacity duration-200",
          state === "done" ? "opacity-100" : "opacity-0",
        )}
      >
        <CheckIcon />
      </span>
    </span>
  );
}

/** AICSS Web Search — shimmer query, collapsible rail, per-result states. */
export function WebSearchCard({ query, results, isRunning }: Props) {
  const [open, setOpen] = useState(true);
  // Number of rows that have reached "done" via staggered reveal (async timers only).
  const [doneCount, setDoneCount] = useState(() =>
    !isRunning && results.length > 0 ? results.length : 0,
  );
  const [loadingCount, setLoadingCount] = useState(0);

  const displayResults = useMemo(() => {
    if (results.length > 0) return results;
    if (isRunning) {
      return Array.from({ length: SKELETON_COUNT }, (_, i) => ({
        title: "",
        url: `skeleton-${i}`,
        snippet: "",
      }));
    }
    return [];
  }, [results, isRunning]);

  const done = !isRunning && results.length > 0;
  const searching = Boolean(isRunning);

  useEffect(() => {
    const n = results.length;
    const preferReduce =
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

    if (isRunning && n === 0) {
      const t = window.setTimeout(() => setLoadingCount(SKELETON_COUNT), 0);
      return () => window.clearTimeout(t);
    }

    if (n === 0) return;

    if (preferReduce || !isRunning) {
      const t = window.setTimeout(() => {
        setDoneCount(n);
        setLoadingCount(n);
      }, 0);
      return () => window.clearTimeout(t);
    }

    const timers: ReturnType<typeof setTimeout>[] = [];
    timers.push(
      setTimeout(() => {
        setDoneCount(0);
        setLoadingCount(0);
      }, 0),
    );
    for (let i = 0; i < n; i++) {
      const discover = 10 + i * STAGGER_MS;
      const finish = discover + HOLD_MS + 180;
      timers.push(
        setTimeout(() => setLoadingCount((c) => Math.max(c, i + 1)), discover),
      );
      timers.push(
        setTimeout(() => setDoneCount((c) => Math.max(c, i + 1)), finish),
      );
    }
    return () => timers.forEach(clearTimeout);
  }, [results, isRunning]);

  const rowState = (i: number): RowState => {
    if (displayResults[i]?.url.startsWith("skeleton-")) return "loading";
    if (i < doneCount) return "done";
    if (i < loadingCount) return "loading";
    if (done) return "done";
    return "pending";
  };

  if (!query && displayResults.length === 0) return null;

  return (
    <div
      className="flex w-full max-w-xl flex-col gap-1.5"
      data-state={done ? "done" : "loading"}
    >
      <div className="flex min-w-0 items-center gap-2 text-body-medium text-text-secondary">
        <span className="shrink-0 text-foreground-icon-secondary">
          <SearchIcon />
        </span>
        <span className="min-w-0 flex-1 truncate">
          <span
            className={cx(
              searching && "agent-progress-loading-text",
              !searching && "text-text-secondary",
            )}
          >
            Searching{" "}
            {query ? (
              <span className={cx(!searching && "text-text-primary")}>
                &ldquo;{query}&rdquo;
              </span>
            ) : (
              "…"
            )}
          </span>
        </span>
        <button
          type="button"
          className="shrink-0 rounded p-0.5 text-foreground-icon-tertiary hover:text-text-secondary"
          aria-label="Toggle results"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
        >
          <CaretIcon open={open} />
        </button>
      </div>

      <div
        className={cx(
          "grid transition-[grid-template-rows] duration-300 ease-out",
          open ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
        )}
      >
        <div className="overflow-hidden">
          {displayResults.length > 0 ? (
            <div className="relative pl-2">
              <span
                className="absolute top-1 bottom-1 left-[11px] w-px bg-separator-border"
                aria-hidden
              />
              <ul className="flex flex-col gap-0.5">
                {displayResults.map((result, i) => {
                  const state = rowState(i);
                  const host = result.url.startsWith("skeleton-")
                    ? ""
                    : hostname(result.url);
                  const isSkeleton = result.url.startsWith("skeleton-");
                  return (
                    <li key={`${result.url}-${i}`} data-state={state}>
                      {isSkeleton ? (
                        <div className="flex items-center gap-2 py-1.5 pl-4">
                          <ResultBullet state="loading" />
                          <span className="aicss-skeleton-shimmer h-3 max-w-[70%] flex-1 rounded" />
                        </div>
                      ) : (
                        <a
                          href={result.url || undefined}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={cx(
                            "group flex min-w-0 items-center gap-2 py-1.5 pl-4 text-body-2-regular transition-colors",
                            "hover:text-text-primary",
                            !result.url && "pointer-events-none",
                          )}
                        >
                          <ResultBullet state={state} />
                          <SiteFavicon host={host} />
                          <span className="min-w-0 flex-1 truncate text-text-primary">
                            {result.title || host || "Result"}
                          </span>
                          {host ? (
                            <>
                              <span className="shrink-0 text-text-tertiary">·</span>
                              <span className="max-w-[40%] shrink-0 truncate font-mono text-caption-1-regular text-text-tertiary">
                                {host}
                              </span>
                            </>
                          ) : null}
                          <span className="shrink-0 text-foreground-icon-tertiary opacity-0 transition-opacity group-hover:opacity-100">
                            <ArrowUpIcon />
                          </span>
                        </a>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
