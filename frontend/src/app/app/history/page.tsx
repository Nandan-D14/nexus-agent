/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { Suspense } from "react";

import { HistorySkeleton } from "@/components/history/history-skeleton";
import { HistoryView } from "@/components/history/history-view";

export default function HistoryPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto flex h-full max-w-4xl flex-col p-4 pb-20 text-zinc-900 md:p-8 dark:text-zinc-100">
          <div className="flex shrink-0 flex-wrap items-center justify-between gap-x-4 gap-y-3">
            <h1 className="font-serif text-3xl leading-none tracking-tight text-zinc-900 sm:text-4xl dark:text-white">
              Chats and tasks
            </h1>
            <div className="flex items-center gap-2.5">
              <div className="size-9 rounded-lg bg-zinc-100 dark:bg-zinc-800" />
              <div className="h-9 w-32 rounded-lg bg-zinc-100 dark:bg-zinc-800" />
              <div className="h-9 w-[4.5rem] rounded-lg bg-zinc-100 dark:bg-zinc-800" />
              <div className="h-9 w-14 rounded-lg bg-zinc-900 dark:bg-white" />
            </div>
          </div>
          <div className="mt-10 min-h-0 flex-1">
            <HistorySkeleton />
          </div>
        </div>
      }
    >
      <HistoryView />
    </Suspense>
  );
}
