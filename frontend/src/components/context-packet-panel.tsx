"use client";

import type { ContextPacket } from "@/lib/message-types";

type ContextMeta = {
  stage: string;
  action: string;
  estimated_tokens?: number;
  reasoning_model: string;
  vision_model: string;
};

type Props = {
  packet: ContextPacket | null;
  meta: ContextMeta | null;
  emptyState?: string;
};

function formatBuiltAt(value: string | null | undefined): string {
  if (!value) return "Not built yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function Section({
  title,
  items,
  empty = "Nothing captured yet.",
}: {
  title: string;
  items: string[];
  empty?: string;
}) {
  return (
    <div className="rounded-2xl border border-zinc-200 bg-white/80 p-4 dark:border-zinc-800 dark:bg-[#17171a]">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
        {title}
      </p>
      {items.length === 0 ? (
        <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">{empty}</p>
      ) : (
        <div className="mt-3 flex flex-col gap-2">
          {items.map((item, index) => (
            <div
              key={`${title}-${index}`}
              className="rounded-xl bg-zinc-50 px-3 py-2 text-sm leading-relaxed text-zinc-700 dark:bg-zinc-900/60 dark:text-zinc-300"
            >
              {item}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function ContextPacketPanel({
  packet,
  meta,
  emptyState = "Compact resume memory has not been captured for this session yet.",
}: Props) {
  if (!packet) {
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
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-4">
        <div className="rounded-2xl border border-zinc-200 bg-white/80 p-4 dark:border-zinc-800 dark:bg-[#17171a]">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="space-y-2">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Compact Context
                </p>
                <p className="mt-1 text-sm text-zinc-700 dark:text-zinc-200">
                  {packet.summary || "No summary recorded yet."}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <span className="rounded-full bg-zinc-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                  v{packet.version}
                </span>
                {packet.digest ? (
                  <span className="rounded-full bg-cyan-50 px-3 py-1 font-mono text-[11px] text-cyan-700 dark:bg-cyan-500/10 dark:text-cyan-300">
                    {packet.digest}
                  </span>
                ) : null}
                {meta?.stage ? (
                  <span className="rounded-full bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300">
                    {meta.stage.replace(/_/g, " ")}
                  </span>
                ) : null}
              </div>
            </div>
            <div className="min-w-[240px] space-y-2 text-sm text-zinc-600 dark:text-zinc-300">
              <div>
                <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  Built
                </span>
                <p className="mt-1">{formatBuiltAt(packet.built_at)}</p>
              </div>
              {meta ? (
                <>
                  <div>
                    <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      Reasoning Model
                    </span>
                    <p className="mt-1 font-mono text-xs">{meta.reasoning_model}</p>
                  </div>
                  <div>
                    <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                      Screen Model
                    </span>
                    <p className="mt-1 font-mono text-xs">{meta.vision_model}</p>
                  </div>
                  <div className="flex flex-wrap gap-3">
                    <div>
                      <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                        Compaction
                      </span>
                      <p className="mt-1">{meta.action.replace(/_/g, " ")}</p>
                    </div>
                    {typeof meta.estimated_tokens === "number" ? (
                      <div>
                        <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                          Estimated Tokens
                        </span>
                        <p className="mt-1">{meta.estimated_tokens.toLocaleString()}</p>
                      </div>
                    ) : null}
                  </div>
                </>
              ) : null}
            </div>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-2xl border border-zinc-200 bg-white/80 p-4 dark:border-zinc-800 dark:bg-[#17171a]">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
              Goal
            </p>
            <p className="mt-3 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
              {packet.goal || "No goal captured yet."}
            </p>
          </div>

          <div className="rounded-2xl border border-zinc-200 bg-white/80 p-4 dark:border-zinc-800 dark:bg-[#17171a]">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
              Workspace State
            </p>
            <p className="mt-3 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
              {packet.workspace_state || "No workspace state captured yet."}
            </p>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <Section title="Open Tasks" items={packet.open_tasks} />
          <Section title="Latest Artifacts" items={packet.artifact_refs} empty="No artifact references in the compact packet." />
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <Section title="Recent Turns" items={packet.recent_turns} />
          <Section title="Tool Memory" items={packet.tool_memory} empty="No compressed tool memory stored yet." />
        </div>

        <div className="rounded-2xl border border-zinc-200 bg-white/80 p-4 dark:border-zinc-800 dark:bg-[#17171a]">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
            Latest Run Summary
          </p>
          <p className="mt-3 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
            {packet.latest_run_summary || "No run summary stored yet."}
          </p>
        </div>
      </div>
    </div>
  );
}
