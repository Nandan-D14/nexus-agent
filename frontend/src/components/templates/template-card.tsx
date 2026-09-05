/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { Pencil, Play, Trash2 } from "lucide-react";
import { motion } from "framer-motion";

import type { WorkflowTemplateData } from "@/lib/message-types";
import {
  formatTemplateDate,
  isPublishedTemplate,
  templateDisplayDescription,
  templateDisplayTitle,
  templateInputCount,
} from "@/lib/templates";
import { cx } from "@/utils/cx";

type TemplateCardProps = {
  template: WorkflowTemplateData;
  index?: number;
  onRun: () => void;
  onEdit: () => void;
  onDelete: () => void;
};

export function TemplateCard({
  template,
  index = 0,
  onRun,
  onEdit,
  onDelete,
}: TemplateCardProps) {
  const title = templateDisplayTitle(template);
  const description = templateDisplayDescription(template);
  const inputCount = templateInputCount(template);
  const dated = formatTemplateDate(template.updated_at || template.created_at);
  const published = isPublishedTemplate(template);

  return (
    <motion.article
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index * 0.03, 0.24) }}
      className="group relative flex h-full flex-col rounded-2xl border border-zinc-200/70 p-4 transition-colors hover:border-zinc-300 dark:border-zinc-800/80 dark:hover:border-zinc-700"
    >
      <div
        className={cx(
          "absolute top-3 right-3 z-10 flex items-center",
          "opacity-100 [@media(hover:hover)]:pointer-events-none [@media(hover:hover)]:opacity-0",
          "[@media(hover:hover)]:group-hover:pointer-events-auto [@media(hover:hover)]:group-hover:opacity-100",
          "[@media(hover:hover)]:group-focus-within:pointer-events-auto [@media(hover:hover)]:group-focus-within:opacity-100",
        )}
      >
        <button
          type="button"
          onClick={onEdit}
          className="rounded-md p-1.5 text-zinc-400 hover:bg-zinc-200 hover:text-zinc-800 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
          title="Edit template"
          aria-label={`Edit ${title}`}
        >
          <Pencil className="size-4" />
        </button>
        <button
          type="button"
          onClick={onDelete}
          className="rounded-md p-1.5 text-red-500 hover:bg-red-500/10"
          title="Delete template"
          aria-label={`Delete ${title}`}
        >
          <Trash2 className="size-4" />
        </button>
      </div>

      <div
        className={cx(
          "flex items-start gap-2 pr-16",
          "[@media(hover:hover)]:pr-0 [@media(hover:hover)]:group-hover:pr-16 [@media(hover:hover)]:group-focus-within:pr-16",
        )}
      >
        <h3
          className="min-w-0 truncate text-base font-semibold text-zinc-900 dark:text-zinc-100"
          title={title}
        >
          {title}
        </h3>
        {!published ? (
          <span className="mt-0.5 shrink-0 rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:text-amber-300">
            Draft
          </span>
        ) : null}
      </div>

      {description ? (
        <p className="mt-1.5 line-clamp-2 text-sm leading-5 text-zinc-500">{description}</p>
      ) : null}

      <div className="mt-auto flex items-end justify-between gap-3 pt-5">
        <p className="min-w-0 text-sm text-zinc-500">
          {dated}
          {dated && inputCount > 0 ? " · " : null}
          {inputCount > 0 ? `${inputCount} input${inputCount === 1 ? "" : "s"}` : null}
        </p>
        <button
          type="button"
          onClick={onRun}
          disabled={!published}
          title={published ? "Run template" : "Publish this template before running it"}
          className="inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-lg bg-linear-to-b from-blue-500 to-blue-600 px-3 text-sm font-medium text-white shadow-nav-selected transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Play className="size-3.5" aria-hidden />
          Run
        </button>
      </div>
    </motion.article>
  );
}
