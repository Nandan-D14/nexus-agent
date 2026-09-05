/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

function Pulse({ className }: { className: string }) {
  return <div className={`animate-pulse rounded bg-zinc-200 dark:bg-zinc-800 ${className}`} />;
}

function RowSkeleton() {
  return (
    <div className="flex items-start justify-between gap-4 rounded-2xl px-3 py-4 sm:px-4">
      <div className="min-w-0 flex-1 space-y-2">
        <Pulse className="h-4 w-2/5" />
        <Pulse className="h-3 w-full" />
        <Pulse className="h-3 w-4/5" />
      </div>
      <Pulse className="mt-0.5 h-3.5 w-28 shrink-0" />
    </div>
  );
}

export function HistorySkeleton({ groups = 2 }: { groups?: number }) {
  const groupSizes = groups === 1 ? [4] : [4, 3];

  return (
    <div className="space-y-12" aria-busy="true" aria-label="Loading history">
      {groupSizes.map((rows, groupIndex) => (
        <section key={groupIndex}>
          <Pulse className="mb-5 h-3 w-20" />
          <div className="flex flex-col gap-1">
            {Array.from({ length: rows }, (_, index) => (
              <RowSkeleton key={index} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
