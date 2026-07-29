/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useState, memo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ListTodo,
  Check,
  CircleDashed,
  ChevronDown,
  ChevronUp,
  ArrowRight,
} from "lucide-react";
import { Badge } from "@/components/base/badges/badge";
import { cx } from "@/utils/cx";

export type TodoItem = {
  title: string;
  status: "pending" | "in_progress" | "done";
  note?: string;
};

interface TodoListProps {
  items: TodoItem[];
  defaultExpanded?: boolean;
}

/** AICSS Task List look — driven by live todo_list_updated WS items. */
export const TodoList = memo(function TodoList({
  items,
  defaultExpanded = false,
}: TodoListProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  if (!items || items.length === 0) return null;

  const total = items.length;
  const completed = items.filter((i) => i.status === "done").length;
  const inProgress = items.filter((i) => i.status === "in_progress").length;
  const progress = Math.round((completed / total) * 100);
  const allDone = completed === total && total > 0;

  return (
    <div className="mb-6 w-full select-none border-t border-separator-border pt-2">
      <div className="rounded-lg px-2 py-2 transition-colors hover:bg-background-secondary-hover/50">
        <button
          type="button"
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex w-full flex-1 items-center gap-2 text-left"
          aria-expanded={isExpanded}
          aria-label="Toggle to-dos"
        >
          <div className="flex size-6 items-center justify-center rounded-md border border-separator-border bg-background-primary-default">
            {allDone ? (
              <Check className="size-3.5 text-emerald-500" strokeWidth={3} />
            ) : (
              <ListTodo className="size-3.5 text-blue-500" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-body-medium text-text-primary">To-dos</span>
              <Badge color="neutral">
                {completed}/{total}
              </Badge>
              {inProgress > 0 ? (
                <Badge color="primary">{inProgress} active</Badge>
              ) : null}
            </div>
            <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-background-tertiary-default">
              <motion.div
                className={cx(
                  "h-full rounded-full",
                  progress === 100 ? "bg-emerald-500" : "bg-blue-500",
                )}
                initial={{ width: 0 }}
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.5 }}
              />
            </div>
          </div>
          {isExpanded ? (
            <ChevronUp className="size-4 text-foreground-icon-tertiary" />
          ) : (
            <ChevronDown className="size-4 text-foreground-icon-tertiary" />
          )}
        </button>
      </div>

      <AnimatePresence>
        {isExpanded ? (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <ul className="mt-1 space-y-0.5 pr-2 pl-8">
              {items.map((item, index) => {
                const done = item.status === "done";
                const active = item.status === "in_progress";
                return (
                  <motion.li
                    key={`${item.title}-${index}`}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: index * 0.03 }}
                    className="flex items-start gap-2.5 rounded-md px-2 py-1.5 transition-colors hover:bg-background-tertiary-hover/50"
                  >
                    <div className="mt-0.5 shrink-0">
                      {done ? (
                        <Check
                          className="size-3.5 text-emerald-500"
                          strokeWidth={3}
                        />
                      ) : active ? (
                        <ArrowRight className="size-3.5 text-blue-500" />
                      ) : (
                        <CircleDashed className="size-3.5 text-foreground-icon-tertiary" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <span
                        className={cx(
                          "text-body-2-regular",
                          done && "text-text-tertiary line-through",
                          active && "text-text-primary",
                          !done && !active && "text-text-secondary",
                        )}
                      >
                        {item.title}
                      </span>
                      {item.note ? (
                        <div className="mt-0.5 line-clamp-2 text-caption-1-regular text-text-tertiary">
                          {item.note}
                        </div>
                      ) : null}
                    </div>
                  </motion.li>
                );
              })}
            </ul>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
});
