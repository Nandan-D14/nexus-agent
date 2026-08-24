/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AlertCircle, ChevronDown, Search, Trash2 } from "lucide-react";
import { motion } from "framer-motion";

import { HistorySessionRow } from "@/components/history/history-session-row";
import { APP_HOME } from "@/lib/app-paths";
import { HistorySkeleton } from "@/components/history/history-skeleton";
import { WorkflowTemplateEditorModal } from "@/components/workflow-template-editor-modal";
import {
  Dropdown,
  DropdownGroup,
  DropdownItem,
  DropdownPopover,
  DropdownTrigger,
} from "@/components/base/dropdown/dropdown";
import {
  HISTORY_FILTERS,
  filterHistorySessions,
  groupHistorySessions,
  type HistoryFilterId,
} from "@/lib/history";
import type { RecentSession, WorkflowTemplateInputField } from "@/lib/message-types";
import {
  useDeleteHistorySessionMutation,
  useDeleteHistorySessionsMutation,
  useHistoryQuery,
} from "@/lib/queries/history";
import { useWorkflowTemplates } from "@/lib/use-workflow-templates";
import { cx } from "@/utils/cx";

type TemplateFormValue = {
  name: string;
  description: string;
  instructions: string;
  inputFields: WorkflowTemplateInputField[];
};

const EMPTY_TEMPLATE: TemplateFormValue = {
  name: "",
  description: "",
  instructions: "",
  inputFields: [],
};

const toolbarControl =
  "inline-flex h-9 cursor-pointer items-center justify-center gap-1.5 rounded-lg bg-zinc-100 px-3 text-sm text-zinc-800 transition-colors hover:bg-zinc-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400 dark:bg-zinc-800 dark:text-zinc-100 dark:hover:bg-zinc-700 dark:focus-visible:ring-zinc-600";

const toolbarIconControl =
  "inline-flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-lg bg-zinc-100 text-zinc-800 transition-colors hover:bg-zinc-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400 dark:bg-zinc-800 dark:text-zinc-100 dark:hover:bg-zinc-700 dark:focus-visible:ring-zinc-600";

function buildTemplateSeed(session: RecentSession): TemplateFormValue {
  const headline = session.handoff_summary?.headline || session.title || "Workflow template";
  const description =
    session.handoff_summary?.preview ||
    session.summary ||
    session.context_packet?.summary ||
    "";
  const instructions =
    session.handoff_summary?.preview ||
    session.context_packet?.summary ||
    session.summary ||
    "Describe the reusable workflow instructions here.";

  return {
    name: headline,
    description,
    instructions,
    inputFields: [],
  };
}

function syncHistoryQueryParam(query: string) {
  const url = new URL(window.location.href);
  const current = url.searchParams.get("q") || "";
  if (current === query) return;
  if (query) url.searchParams.set("q", query);
  else url.searchParams.delete("q");
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
}

export function HistoryView() {
  const searchParams = useSearchParams();
  const { saveSessionAsTemplate, isLoading: templateLoading, error: templateError } =
    useWorkflowTemplates();
  const initialQuery = searchParams.get("q") || "";
  const [searchOpen, setSearchOpen] = useState(() => Boolean(initialQuery));
  const [searchInput, setSearchInput] = useState(initialQuery);
  const [searchQuery, setSearchQuery] = useState(initialQuery.trim());
  const [statusFilter, setStatusFilter] = useState<HistoryFilterId>("all");
  const [filterOpen, setFilterOpen] = useState(false);
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [templateSource, setTemplateSource] = useState<RecentSession | null>(null);
  const [templateSeed, setTemplateSeed] = useState<TemplateFormValue>(EMPTY_TEMPLATE);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const historyQuery = useHistoryQuery(searchQuery);
  const deleteSessionMutation = useDeleteHistorySessionMutation();
  const deleteSessionsMutation = useDeleteHistorySessionsMutation();
  const sessions = historyQuery.data ?? [];
  const loading = historyQuery.isLoading;
  const error =
    mutationError ||
    (historyQuery.error instanceof Error ? historyQuery.error.message : null);

  useEffect(() => {
    const q = searchParams.get("q") || "";
    setSearchInput((prev) => (prev.trim() === q ? prev : q));
    if (q) setSearchOpen(true);
  }, [searchParams]);

  useEffect(() => {
    const handle = window.setTimeout(() => setSearchQuery(searchInput.trim()), 400);
    return () => window.clearTimeout(handle);
  }, [searchInput]);

  useEffect(() => {
    syncHistoryQueryParam(searchQuery);
  }, [searchQuery]);

  useEffect(() => {
    if (searchOpen) searchInputRef.current?.focus();
  }, [searchOpen]);

  const groups = useMemo(
    () => groupHistorySessions(filterHistorySessions(sessions, statusFilter)),
    [sessions, statusFilter],
  );

  const filterLabel = HISTORY_FILTERS.find((filter) => filter.id === statusFilter)?.label ?? "All";
  const selectedCount = selectedIds.size;

  const dropSelected = (sessionId: string) => {
    setSelectedIds((prev) => {
      if (!prev.has(sessionId)) return prev;
      const next = new Set(prev);
      next.delete(sessionId);
      return next;
    });
  };

  const deleteSession = async (sessionId: string) => {
    if (!confirm("Are you sure you want to delete this session?")) return;
    setMutationError(null);
    try {
      await deleteSessionMutation.mutateAsync(sessionId);
      dropSelected(sessionId);
    } catch (requestError) {
      setMutationError(
        requestError instanceof Error ? requestError.message : "Failed to delete session",
      );
    }
  };

  const deleteSelected = async () => {
    const ids = [...selectedIds];
    if (ids.length === 0) return;
    const label = ids.length === 1 ? "this session" : `${ids.length} sessions`;
    if (!confirm(`Are you sure you want to delete ${label}?`)) return;
    setBulkDeleting(true);
    setMutationError(null);
    try {
      const { succeeded, failed } = await deleteSessionsMutation.mutateAsync(ids);
      if (succeeded.length > 0) {
        setSelectedIds((prev) => {
          const next = new Set(prev);
          for (const id of succeeded) next.delete(id);
          return next;
        });
      }
      if (failed > 0) {
        setMutationError(`Failed to delete ${failed} session${failed === 1 ? "" : "s"}`);
      } else {
        setSelectMode(false);
        setSelectedIds(new Set());
      }
    } finally {
      setBulkDeleting(false);
    }
  };

  const toggleSelect = (sessionId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(sessionId)) next.delete(sessionId);
      else next.add(sessionId);
      return next;
    });
  };

  const toggleSelectMode = () => {
    setSelectMode((prev) => {
      if (prev) setSelectedIds(new Set());
      return !prev;
    });
  };

  const openTemplateModal = (session: RecentSession) => {
    setTemplateSource(session);
    setTemplateSeed(buildTemplateSeed(session));
  };

  const closeTemplateModal = () => {
    setTemplateSource(null);
    setTemplateSeed(EMPTY_TEMPLATE);
  };

  const handleTemplateSubmit = async (value: TemplateFormValue) => {
    if (!templateSource) return;
    const saved = await saveSessionAsTemplate(templateSource.session_id, {
      name: value.name,
      description: value.description,
      instructions: value.instructions,
      inputFields: value.inputFields,
    });
    if (saved) {
      closeTemplateModal();
    }
  };

  const emptyMessage = searchQuery
    ? "No conversations match your search"
    : statusFilter !== "all"
      ? "No conversations in this filter"
      : "No conversations yet";

  return (
    <div className="mx-auto flex h-full max-w-4xl flex-col p-4 pb-20 text-zinc-900 md:p-8 dark:text-zinc-100">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-x-4 gap-y-3">
        <h1 className="min-w-0 font-serif text-3xl leading-none tracking-tight text-zinc-900 sm:text-4xl dark:text-white">
          Chats and tasks
        </h1>
        <div className="flex items-center gap-2.5">
          {searchOpen ? (
            <div className="relative">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-zinc-500" />
              <input
                ref={searchInputRef}
                type="search"
                placeholder="Search"
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key !== "Escape") return;
                  if (searchInput) {
                    setSearchInput("");
                    return;
                  }
                  setSearchOpen(false);
                }}
                className="h-9 w-44 rounded-lg border-0 bg-zinc-100 py-0 pr-3 pl-8 text-sm text-zinc-900 placeholder-zinc-500 outline-none ring-0 focus:ring-2 focus:ring-zinc-400 sm:w-56 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder-zinc-500 dark:focus:ring-zinc-600"
              />
            </div>
          ) : (
            <button
              type="button"
              aria-label="Search chats"
              onClick={() => setSearchOpen(true)}
              className={toolbarIconControl}
            >
              <Search className="size-4" />
            </button>
          )}

          <Dropdown isOpen={filterOpen} onOpenChange={setFilterOpen}>
            <DropdownTrigger aria-label={`Filter by ${filterLabel}`} className={toolbarControl}>
              <span className="text-zinc-500 dark:text-zinc-400">Filter by</span>
              <span className="font-medium text-zinc-900 dark:text-white">{filterLabel}</span>
              <ChevronDown className="size-3.5 text-zinc-500" />
            </DropdownTrigger>
            <DropdownPopover
              aria-label="Filter conversations"
              placement="bottom end"
              className="w-40"
            >
              <DropdownGroup>
                {HISTORY_FILTERS.map((filter) => (
                  <DropdownItem
                    key={filter.id}
                    selected={statusFilter === filter.id}
                    onSelect={() => {
                      setStatusFilter(filter.id);
                      setFilterOpen(false);
                    }}
                  >
                    {filter.label}
                  </DropdownItem>
                ))}
              </DropdownGroup>
            </DropdownPopover>
          </Dropdown>

          <button
            type="button"
            aria-pressed={selectMode}
            onClick={toggleSelectMode}
            className={cx(toolbarControl, selectMode && "bg-zinc-200 dark:bg-zinc-700")}
          >
            {selectMode ? "Done" : "Select"}
          </button>

          {selectMode && selectedCount > 0 ? (
            <>
              <span className="hidden text-sm text-zinc-500 sm:inline">
                {selectedCount} selected
              </span>
              <button
                type="button"
                disabled={bulkDeleting}
                onClick={() => void deleteSelected()}
                className={cx(
                  toolbarControl,
                  "gap-1.5 text-red-600 hover:bg-red-500/10 dark:text-red-400 dark:hover:bg-red-500/10",
                )}
              >
                <Trash2 className="size-3.5" />
                Delete
              </button>
            </>
          ) : null}

          <Link
            href={APP_HOME}
            className="inline-flex h-9 items-center justify-center rounded-lg bg-zinc-900 px-3.5 text-sm font-medium text-white transition-colors hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-100 dark:focus-visible:ring-zinc-500"
          >
            New
          </Link>
        </div>
      </div>

      {error ? (
        <div className="mt-6 flex items-center gap-3 rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-600 dark:text-red-400">
          <AlertCircle className="size-5" />
          <p>{error}</p>
        </div>
      ) : null}

      <div className="mt-10 min-h-0 flex-1 overflow-y-auto pr-1">
        {loading ? (
          <HistorySkeleton />
        ) : groups.length === 0 ? (
          <div className="flex h-64 items-center justify-center rounded-2xl border border-dashed border-zinc-300 font-mono text-sm text-zinc-500 uppercase dark:border-white/10">
            {emptyMessage}
          </div>
        ) : (
          <div className="space-y-12">
            {groups.map((group, index) => (
              <motion.section
                key={group.label}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(index * 0.04, 0.24) }}
              >
                <h2 className="px-3 pb-4 text-xs font-medium text-zinc-500">
                  {group.label}
                </h2>
                <div className="flex flex-col gap-1">
                  {group.sessions.map((session) => (
                    <HistorySessionRow
                      key={session.session_id}
                      session={session}
                      selectMode={selectMode}
                      selected={selectedIds.has(session.session_id)}
                      onToggleSelect={() => toggleSelect(session.session_id)}
                      onSaveAsTemplate={() => openTemplateModal(session)}
                      onDelete={() => void deleteSession(session.session_id)}
                    />
                  ))}
                </div>
              </motion.section>
            ))}
          </div>
        )}
      </div>

      <WorkflowTemplateEditorModal
        open={Boolean(templateSource)}
        title="Save as Template"
        subtitle="Save this successful session as a reusable workflow."
        submitLabel="Save Template"
        initialValue={templateSeed}
        isSubmitting={templateLoading}
        onClose={closeTemplateModal}
        onSubmit={(value) => void handleTemplateSubmit(value)}
      />

      {templateError ? (
        <div className="fixed right-4 bottom-4 max-w-md rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-600 shadow-lg dark:text-red-400">
          {templateError}
        </div>
      ) : null}
    </div>
  );
}
