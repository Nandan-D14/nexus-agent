/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

/**
 * Static pulse shell shown while auth resolves before the real
 * AppShell + session landing mount. Matches sidebar + landing layout.
 */
export function AppShellSkeleton() {
  return (
    <div
      className="flex h-screen min-h-screen overflow-hidden bg-background-full text-foreground supports-[height:100dvh]:h-[100dvh]"
      aria-busy="true"
      aria-label="Loading"
    >
      {/* Sidebar placeholder — expanded desktop width */}
      <aside className="hidden md:flex sticky top-3 m-3 h-[calc(100dvh-24px)] w-[260px] shrink-0 flex-col gap-3 overflow-hidden rounded-xl border border-input-border bg-input-bg p-3 shadow-sidebar">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="size-7 shrink-0 animate-pulse rounded-lg bg-background-tertiary-default" />
            <div className="h-4 w-28 animate-pulse rounded bg-background-tertiary-default" />
          </div>
          <div className="size-9 shrink-0 animate-pulse rounded-lg bg-background-tertiary-default" />
        </div>

        <div className="h-10 w-full animate-pulse rounded-full bg-background-tertiary-default" />
        <div className="h-10 w-full animate-pulse rounded-2lg bg-background-tertiary-default" />

        <div className="mt-2 flex min-h-0 flex-1 flex-col gap-1">
          <div className="mb-1 h-3 w-20 animate-pulse rounded bg-background-tertiary-default" />
          {[0, 1, 2, 3, 4].map((item) => (
            <div
              key={item}
              className="h-10 animate-pulse rounded-2lg bg-background-tertiary-default"
            />
          ))}
        </div>

        <div className="mt-auto flex items-center gap-2 pt-2">
          <div className="size-9 shrink-0 animate-pulse rounded-full bg-background-tertiary-default" />
          <div className="flex flex-1 flex-col gap-1.5">
            <div className="h-3 w-24 animate-pulse rounded bg-background-tertiary-default" />
            <div className="h-2 w-16 animate-pulse rounded bg-background-tertiary-default" />
          </div>
        </div>
      </aside>

      {/* Main session-landing placeholder */}
      <div className="relative flex h-full min-w-0 flex-1 flex-col overflow-hidden">
        <main className="flex min-h-0 flex-1 flex-col pt-16 md:pt-0">
          <div className="relative flex flex-1 flex-col items-center p-6 pt-[25vh]">
            <div className="flex w-full max-w-3xl flex-col items-center gap-4">
              <div className="flex flex-col items-center gap-2 py-2">
                <div className="h-2.5 w-16 animate-pulse rounded bg-background-tertiary-default" />
                <div className="h-10 w-48 animate-pulse rounded-lg bg-background-tertiary-default md:h-12 md:w-56" />
                <div className="mt-6 h-4 w-40 animate-pulse rounded bg-background-tertiary-default" />
              </div>

              <div className="mt-4 w-full max-w-3xl px-4">
                <div className="h-28 w-full animate-pulse rounded-2xl border border-border-button-white bg-background-tertiary-default/80 md:h-32" />
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
