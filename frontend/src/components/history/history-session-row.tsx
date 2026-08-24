/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FileText, MoreHorizontal, Play, Trash2, Workflow } from "lucide-react";

import {
  Dropdown,
  DropdownGroup,
  DropdownItem,
  DropdownPopover,
  DropdownTrigger,
} from "@/components/base/dropdown/dropdown";
import {
  formatHistoryDate,
  historyActivityAt,
  historyPreview,
  parseHistoryPreview,
} from "@/lib/history";
import { sessionPath } from "@/lib/app-paths";
import type { RecentSession } from "@/lib/message-types";
import { cx } from "@/utils/cx";

type Props = {
  session: RecentSession;
  onSaveAsTemplate: () => void;
  onDelete: () => void;
  selectMode?: boolean;
  selected?: boolean;
  onToggleSelect?: () => void;
};

function HistoryPreview({ text }: { text: string }) {
  const parts = parseHistoryPreview(text);
  if (parts.length === 0) return null;

  return (
    <span className="mt-1.5 block line-clamp-2 text-sm leading-5 text-zinc-500">
      {parts.map((part, index) =>
        part.type === "text" ? (
          <span key={index}>{part.value}</span>
        ) : (
          <strong key={index} className="font-semibold text-zinc-500">
            {part.value}
          </strong>
        ),
      )}
    </span>
  );
}

export function HistorySessionRow({
  session,
  onSaveAsTemplate,
  onDelete,
  selectMode = false,
  selected = false,
  onToggleSelect,
}: Props) {
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const title = session.title || "Untitled session";
  const preview = historyPreview(session);
  const continueHref = sessionPath(session.session_id, { continue: "1" });
  const transcriptHref = sessionPath(session.session_id);
  const dateLabel = formatHistoryDate(historyActivityAt(session));
  const actionsVisible = menuOpen;

  return (
    <div
      className={cx(
        "group relative flex items-start gap-3 rounded-2xl border border-transparent px-3 py-4 transition-colors sm:px-4",
        "hover:border-zinc-200 dark:hover:border-zinc-700",
        menuOpen && "border-zinc-200 dark:border-zinc-700",
        selectMode && selected && "bg-zinc-100/80 dark:bg-zinc-800/50",
      )}
    >
      {selectMode ? (
        <input
          type="checkbox"
          checked={selected}
          aria-label={`Select ${title}`}
          onChange={() => onToggleSelect?.()}
          onClick={(event) => event.stopPropagation()}
          className="mt-1 size-4 shrink-0 rounded border-zinc-300 accent-zinc-900 dark:border-zinc-600 dark:accent-white"
        />
      ) : null}
      <Link
        href={continueHref}
        onClick={(event) => {
          if (!selectMode) return;
          event.preventDefault();
          onToggleSelect?.();
        }}
        className={cx(
          "block min-w-0 flex-1 text-left",
          selectMode && "cursor-default",
          actionsVisible
            ? "pr-16"
            : "pr-10 [@media(hover:hover)]:pr-0 [@media(hover:hover)]:group-hover:pr-16 [@media(hover:hover)]:group-focus-within:pr-16",
        )}
      >
        <span className="flex min-w-0 items-baseline justify-between gap-4">
          <span className="flex min-w-0 items-center gap-2">
            <span className="truncate text-base font-semibold text-zinc-900 dark:text-zinc-100">
              {title}
            </span>
            {session.status === "error" ? (
              <span className="shrink-0 rounded bg-red-500/10 px-1.5 py-0.5 text-[10px] font-medium tracking-wide text-red-600 uppercase dark:text-red-400">
                Error
              </span>
            ) : null}
          </span>
          {dateLabel ? (
            <span className="shrink-0 text-sm text-zinc-500">{dateLabel}</span>
          ) : null}
        </span>
        {preview ? <HistoryPreview text={preview} /> : null}
      </Link>

      <div
        className={cx(
          "absolute top-3 right-2 z-10 flex items-center sm:right-3",
          actionsVisible
            ? "opacity-100"
            : "opacity-100 [@media(hover:hover)]:pointer-events-none [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:pointer-events-auto [@media(hover:hover)]:group-hover:opacity-100 [@media(hover:hover)]:group-focus-within:pointer-events-auto [@media(hover:hover)]:group-focus-within:opacity-100",
        )}
        onClick={(event) => event.stopPropagation()}
        onPointerDown={(event) => event.stopPropagation()}
      >
        <Dropdown isOpen={menuOpen} onOpenChange={setMenuOpen}>
          <DropdownTrigger
            aria-label={`Actions for ${title}`}
            className="rounded-md p-1.5 text-zinc-400 hover:bg-zinc-200 hover:text-zinc-800 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
          >
            <MoreHorizontal className="size-4" />
          </DropdownTrigger>
          <DropdownPopover aria-label="Conversation actions" placement="bottom end" className="w-[200px]">
            <DropdownGroup>
              <DropdownItem
                onSelect={() => {
                  setMenuOpen(false);
                  router.push(continueHref);
                }}
              >
                <Play className="size-4" />
                <span>Continue</span>
              </DropdownItem>
              <DropdownItem
                onSelect={() => {
                  setMenuOpen(false);
                  router.push(transcriptHref);
                }}
              >
                <FileText className="size-4" />
                <span>View transcript</span>
              </DropdownItem>
              <DropdownItem
                onSelect={() => {
                  setMenuOpen(false);
                  onSaveAsTemplate();
                }}
              >
                <Workflow className="size-4" />
                <span>Save as template</span>
              </DropdownItem>
              <DropdownItem
                onSelect={() => {
                  setMenuOpen(false);
                  onDelete();
                }}
                className="text-red-500 hover:bg-red-500/10 focus-visible:bg-red-500/10"
              >
                <Trash2 className="size-4" />
                <span>Delete</span>
              </DropdownItem>
            </DropdownGroup>
          </DropdownPopover>
        </Dropdown>
        <button
          type="button"
          aria-label={`Delete ${title}`}
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            onDelete();
          }}
          className="rounded-md p-1.5 text-red-500 hover:bg-red-500/10"
        >
          <Trash2 className="size-4" />
        </button>
      </div>
    </div>
  );
}
