"use client";

import type { RunArtifact } from "@/lib/message-types";

type Props = {
  artifacts: RunArtifact[];
  emptyState?: string;
};

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "Unknown time";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown time";
  return date.toLocaleString();
}

export function OutputsPanel({
  artifacts,
  emptyState = "No outputs have been captured for this run yet.",
}: Props) {
  if (artifacts.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-4 py-6">
        <div className="flex min-h-[240px] w-full max-w-4xl items-center justify-center rounded-2xl border border-dashed border-zinc-300 bg-white/60 p-6 text-center text-sm text-zinc-500 dark:border-zinc-800 dark:bg-[#151518] dark:text-zinc-400">
          {emptyState}
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto custom-scrollbar px-4 py-6">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-3">
        {artifacts.map((artifact) => (
          <div
            key={artifact.artifact_id}
            className="rounded-2xl border border-zinc-200 bg-white/80 p-4 dark:border-zinc-800 dark:bg-[#17171a]"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                  {artifact.title || artifact.kind.replace(/_/g, " ")}
                </p>
                <p className="mt-1 text-[11px] uppercase tracking-[0.16em] text-zinc-500">
                  {artifact.kind.replace(/_/g, " ")}
                </p>
              </div>
              <span className="text-xs text-zinc-500">
                {formatTimestamp(artifact.created_at)}
              </span>
            </div>
            {artifact.preview ? (
              <p className="mt-3 text-sm leading-relaxed text-zinc-600 dark:text-zinc-300">
                {artifact.preview}
              </p>
            ) : null}
            {artifact.path ? (
              <p className="mt-3 text-xs text-zinc-500">
                Path: <span className="font-mono">{artifact.path}</span>
              </p>
            ) : null}
            {artifact.url ? (
              <p className="mt-3 text-xs text-zinc-500">
                Link:{" "}
                <a
                  href={artifact.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-cyan-600 hover:text-cyan-500 dark:text-cyan-300"
                >
                  {artifact.url}
                </a>
              </p>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
