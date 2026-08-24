/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

function Pulse({ className }: { className: string }) {
  return <div className={`animate-pulse rounded bg-zinc-200 dark:bg-zinc-800 ${className}`} />;
}

function TemplateCardSkeleton() {
  return (
    <div className="flex flex-col rounded-2xl border border-zinc-200/70 p-4 dark:border-zinc-800/80">
      <Pulse className="h-4 w-2/5" />
      <div className="mt-2 space-y-2">
        <Pulse className="h-3 w-full" />
        <Pulse className="h-3 w-4/5" />
      </div>
      <div className="mt-5 flex items-end justify-between gap-3">
        <Pulse className="h-3.5 w-28" />
        <Pulse className="h-8 w-16 shrink-0 rounded-lg" />
      </div>
    </div>
  );
}

export function TemplatesSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div aria-busy="true" aria-label="Loading templates">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-x-4 gap-y-3">
        <Pulse className="h-9 w-40 sm:h-10" />
        <div className="flex items-center gap-2.5">
          <Pulse className="size-9 shrink-0 rounded-lg" />
          <Pulse className="h-9 w-36 rounded-lg" />
          <Pulse className="h-9 w-16 rounded-lg" />
        </div>
      </div>
      <div className="mt-10 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: count }, (_, index) => (
          <TemplateCardSkeleton key={index} />
        ))}
      </div>
    </div>
  );
}
