"use client";

import type { RunInfo, RunStep } from "@/lib/message-types";

type Props = {
  run: RunInfo | null;
  steps: RunStep[];
  emptyState?: string;
};

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "Pending";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Pending";
  return date.toLocaleTimeString([], {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function statusClass(status: string): string {
  switch (status) {
    case "completed":
      return "bg-emerald-500/10 text-emerald-600 dark:text-emerald-300";
    case "failed":
      return "bg-red-500/10 text-red-600 dark:text-red-300";
    case "cancelled":
      return "bg-amber-500/10 text-amber-600 dark:text-amber-300";
    case "running":
      return "bg-cyan-500/10 text-cyan-600 dark:text-cyan-300";
    default:
      return "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300";
  }
}

export function RunLogPanel({
  run,
  steps,
  emptyState = "No run activity has been recorded yet.",
}: Props) {
  return (
    <div className="h-full overflow-y-auto custom-scrollbar px-4 py-6">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
        <div className="rounded-2xl border border-zinc-200 bg-white/80 p-4 dark:border-zinc-800 dark:bg-[#17171a]">
          <div className="flex flex-wrap items-center gap-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-zinc-500">
                Run Status
              </p>
              <p className="mt-1 text-sm text-zinc-700 dark:text-zinc-200">
                {run?.title || "Current run"}
              </p>
            </div>
            <span className={`rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] ${statusClass(run?.status || "queued")}`}>
              {run?.status || "queued"}
            </span>
            <span className="text-xs text-zinc-500">
              {run ? `${run.step_count} steps` : "Waiting for the first step"}
            </span>
          </div>
        </div>

        {steps.length === 0 ? (
          <div className="flex min-h-[240px] items-center justify-center rounded-2xl border border-dashed border-zinc-300 bg-white/60 p-6 text-center text-sm text-zinc-500 dark:border-zinc-800 dark:bg-[#151518] dark:text-zinc-400">
            {emptyState}
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {steps.map((step) => (
              <div
                key={step.step_id}
                className="rounded-2xl border border-zinc-200 bg-white/80 p-4 dark:border-zinc-800 dark:bg-[#17171a]"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                      {step.title || step.step_type.replace(/_/g, " ")}
                    </p>
                    <p className="mt-1 text-[11px] uppercase tracking-[0.16em] text-zinc-500">
                      {step.step_type.replace(/_/g, " ")}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] ${statusClass(step.status)}`}>
                      {step.status}
                    </span>
                    <span className="text-xs text-zinc-500">
                      {formatTimestamp(step.completed_at || step.updated_at || step.created_at)}
                    </span>
                  </div>
                </div>
                {step.detail ? (
                  <p className="mt-3 text-sm leading-relaxed text-zinc-600 dark:text-zinc-300">
                    {step.detail}
                  </p>
                ) : null}
                {step.error ? (
                  <p className="mt-2 text-sm text-red-500 dark:text-red-300">
                    {step.error}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
