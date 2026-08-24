/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

function Pulse({ className }: { className: string }) {
  return <div className={`animate-pulse rounded bg-zinc-200 dark:bg-zinc-800 ${className}`} />;
}

function GridCardSkeleton() {
  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800 dark:bg-[#141414]">
      <div className="flex items-center gap-2 border-b border-zinc-200 px-3 py-2 dark:border-zinc-800">
        <Pulse className="size-4 shrink-0" />
        <Pulse className="h-3.5 flex-1" />
        <Pulse className="size-4 shrink-0" />
      </div>
      <Pulse className="aspect-[16/10] w-full rounded-none" />
    </div>
  );
}

function ListRowSkeleton() {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2.5 dark:border-zinc-800 dark:bg-[#141414]">
      <Pulse className="size-9 shrink-0 rounded-lg" />
      <div className="min-w-0 flex-1 space-y-2">
        <Pulse className="h-3.5 w-2/3" />
        <Pulse className="h-2.5 w-1/2" />
      </div>
    </div>
  );
}

export function LibrarySkeleton({
  view,
  groups = 2,
}: {
  view: "grid" | "list";
  groups?: number;
}) {
  const groupSizes = groups === 1 ? [3] : [3, 2];

  return (
    <div className="space-y-10" aria-busy="true" aria-label="Loading library">
      {groupSizes.map((cards, groupIndex) => (
        <section key={groupIndex}>
          <div className="mb-4 flex items-baseline justify-between gap-4">
            <Pulse className="h-5 w-48" />
            <Pulse className="h-3 w-24" />
          </div>
          <div
            className={
              view === "grid"
                ? "grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
                : "flex flex-col gap-2"
            }
          >
            {Array.from({ length: cards }, (_, index) =>
              view === "grid" ? (
                <GridCardSkeleton key={index} />
              ) : (
                <ListRowSkeleton key={index} />
              ),
            )}
          </div>
        </section>
      ))}
    </div>
  );
}
