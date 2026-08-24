/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

function Pulse({ className }: { className: string }) {
  return <div className={`animate-pulse rounded bg-zinc-200 dark:bg-zinc-800 ${className}`} />;
}

function RowSkeleton() {
  return (
    <div className="flex items-center gap-3 rounded-2xl px-3 py-2.5">
      <Pulse className="size-11 shrink-0 rounded-xl" />
      <div className="min-w-0 flex-1 space-y-2">
        <Pulse className="h-3.5 w-1/3" />
        <Pulse className="h-3 w-3/4" />
      </div>
      <Pulse className="size-8 shrink-0 rounded-lg" />
    </div>
  );
}

export function ConnectorsSkeleton() {
  return (
    <div className="space-y-10" aria-busy="true" aria-label="Loading connectors">
      <section>
        <Pulse className="mb-4 h-3 w-20" />
        <div className="flex gap-3">
          {Array.from({ length: 4 }, (_, index) => (
            <Pulse key={index} className="size-10 rounded-xl" />
          ))}
        </div>
      </section>
      {["a", "b"].map((key) => (
        <section key={key}>
          <Pulse className="mb-3 h-3 w-16" />
          <div className="grid grid-cols-1 gap-1 md:grid-cols-2">
            <RowSkeleton />
            <RowSkeleton />
            <RowSkeleton />
            <RowSkeleton />
          </div>
        </section>
      ))}
    </div>
  );
}
