/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, LayoutGrid, List, Search } from "lucide-react";
import { motion } from "framer-motion";

import { DocumentViewerModal } from "@/components/artifacts";
import { sessionPath } from "@/lib/app-paths";
import { LibraryFileCard } from "@/components/library/library-file-card";
import { LibrarySkeleton } from "@/components/library/library-skeleton";
import { PillTab, PillTabList } from "@/components/base/tabs/pill-tab";
import {
  LIBRARY_FILTERS,
  filterLibraryItems,
  formatLibraryTimestamp,
  groupLibraryItems,
  type LibraryFilterId,
} from "@/lib/library";
import type { RunArtifact } from "@/lib/message-types";
import { useLibraryInfiniteQuery } from "@/lib/queries/library";
import { cx } from "@/utils/cx";

export function LibraryView() {
  const router = useRouter();
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [category, setCategory] = useState<LibraryFilterId>("all");
  const [view, setView] = useState<"grid" | "list">("grid");
  const [viewerArtifact, setViewerArtifact] = useState<RunArtifact | null>(null);
  const [viewerUrl, setViewerUrl] = useState<string | null>(null);
  const libraryQuery = useLibraryInfiniteQuery(searchQuery);
  const items = useMemo(
    () => libraryQuery.data?.pages.flatMap((page) => page.items) ?? [],
    [libraryQuery.data],
  );
  const nextCursor = libraryQuery.hasNextPage
    ? (libraryQuery.data?.pages.at(-1)?.nextCursor ?? null)
    : null;
  const loading = libraryQuery.isLoading;
  const loadingMore = libraryQuery.isFetchingNextPage;
  const error = libraryQuery.error instanceof Error ? libraryQuery.error.message : null;

  useEffect(() => {
    const handle = window.setTimeout(() => setSearchQuery(searchInput.trim()), 400);
    return () => window.clearTimeout(handle);
  }, [searchInput]);

  const groups = useMemo(
    () => groupLibraryItems(filterLibraryItems(items, category)),
    [category, items],
  );

  const openViewer = (artifact: RunArtifact, url: string | null) => {
    setViewerArtifact(artifact);
    setViewerUrl(url);
  };

  const emptyMessage = searchQuery
    ? "No files match your search"
    : category !== "all"
      ? "No files in this category yet"
      : "No files in your library yet";

  return (
    <div className="mx-auto flex h-full max-w-7xl flex-col space-y-6 p-4 pb-20 text-zinc-900 md:p-8 dark:text-zinc-100">
      <div className="flex shrink-0 flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="font-serif text-3xl leading-none tracking-tight text-zinc-900 sm:text-4xl dark:text-white">
            Library
          </h1>
          <p className="mt-2 text-sm text-zinc-500">
            Files and artifacts from your sessions, grouped by conversation.
          </p>
        </div>
      </div>

      <div className="flex shrink-0 flex-col gap-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <div className="min-w-0 flex-1 overflow-x-auto">
            <PillTabList className="min-w-max">
              {LIBRARY_FILTERS.map((filter) => (
                <PillTab
                  key={filter.id}
                  variant="gray"
                  isSelected={category === filter.id}
                  onSelect={() => setCategory(filter.id)}
                >
                  {filter.label}
                </PillTab>
              ))}
            </PillTabList>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative min-w-0 flex-1 lg:w-72 lg:flex-none">
              <Search className="pointer-events-none absolute top-1/2 left-4 size-4 -translate-y-1/2 text-zinc-500" />
              <input
                type="search"
                placeholder="Search files"
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                className="w-full rounded-3xl border border-zinc-200 bg-[#f4f4f5] py-2.5 pr-4 pl-11 text-sm text-zinc-900 placeholder-zinc-500 shadow-sm transition-colors focus:ring-1 focus:ring-zinc-400 focus:outline-none dark:border-[#2f2f35] dark:bg-[#212126] dark:text-zinc-100 dark:focus:ring-zinc-600"
              />
            </div>
            <div className="flex shrink-0 rounded-full border border-zinc-200 p-1 dark:border-zinc-800">
              <button
                type="button"
                aria-label="Grid view"
                aria-pressed={view === "grid"}
                onClick={() => setView("grid")}
                className={cx(
                  "flex size-8 items-center justify-center rounded-full transition-colors",
                  view === "grid"
                    ? "bg-zinc-200 text-zinc-900 dark:bg-zinc-700 dark:text-white"
                    : "text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200",
                )}
              >
                <LayoutGrid className="size-4" />
              </button>
              <button
                type="button"
                aria-label="List view"
                aria-pressed={view === "list"}
                onClick={() => setView("list")}
                className={cx(
                  "flex size-8 items-center justify-center rounded-full transition-colors",
                  view === "list"
                    ? "bg-zinc-200 text-zinc-900 dark:bg-zinc-700 dark:text-white"
                    : "text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200",
                )}
              >
                <List className="size-4" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {error ? (
        <div className="flex items-center gap-3 rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-600 dark:text-red-400">
          <AlertCircle className="size-5" />
          <p>{error}</p>
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        {loading ? (
          <LibrarySkeleton view={view} />
        ) : groups.length === 0 ? (
          <div className="flex h-64 items-center justify-center rounded-2xl border border-dashed border-zinc-300 font-mono text-sm text-zinc-500 uppercase dark:border-white/10">
            {emptyMessage}
          </div>
        ) : (
          <div className="space-y-10">
            {groups.map((group, index) => (
              <motion.section
                key={group.session_id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(index * 0.04, 0.24) }}
              >
                <div className="mb-4 flex items-baseline justify-between gap-4">
                  <h2 className="truncate text-base font-semibold text-zinc-900 dark:text-zinc-100">
                    {group.session_title}
                  </h2>
                  <span className="shrink-0 text-xs text-zinc-500">
                    {formatLibraryTimestamp(group.timestamp)}
                  </span>
                </div>
                <div
                  className={
                    view === "grid"
                      ? "grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
                      : "flex flex-col gap-2"
                  }
                >
                  {group.items.map((item) => (
                    <LibraryFileCard
                      key={item.artifact.artifact_id}
                      item={item}
                      view={view}
                      onPreview={(url) => openViewer(item.artifact, url)}
                      onOpenSession={() => router.push(sessionPath(item.session_id))}
                    />
                  ))}
                </div>
              </motion.section>
            ))}

            {loadingMore ? (
              <LibrarySkeleton view={view} groups={1} />
            ) : nextCursor ? (
              <div className="flex justify-center pt-2">
                <button
                  type="button"
                  onClick={() => void libraryQuery.fetchNextPage()}
                  disabled={loadingMore}
                  className="rounded-full border border-zinc-200 bg-zinc-50 px-4 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
                >
                  {loadingMore ? "Loading…" : "Load more"}
                </button>
              </div>
            ) : null}
          </div>
        )}
      </div>

      <DocumentViewerModal
        artifact={viewerArtifact}
        url={viewerUrl}
        onClose={() => {
          setViewerArtifact(null);
          setViewerUrl(null);
        }}
      />
    </div>
  );
}
