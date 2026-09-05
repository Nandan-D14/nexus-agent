/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertCircle, Pause, Play, Plus, Trash2 } from "lucide-react";
import { AnimatePresence } from "framer-motion";

import { ScheduleCalendar } from "@/components/schedule/schedule-calendar";
import { ScheduleEditor } from "@/components/schedule/schedule-editor";
import { sessionPath } from "@/lib/app-paths";
import {
  useAllScheduleFiringsQuery,
  useDeleteScheduleMutation,
  usePauseScheduleMutation,
  useResumeScheduleMutation,
  useRunScheduleNowMutation,
  useScheduleFiringsQuery,
  useSchedulesQuery,
  type ScheduledJob,
} from "@/lib/queries/schedule";

const toolbarControl =
  "inline-flex h-9 cursor-pointer items-center justify-center gap-1.5 rounded-lg bg-zinc-100 px-3 text-sm text-zinc-800 transition-colors hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-100 dark:hover:bg-zinc-700";

function formatWhen(value: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function cadenceLabel(schedule: ScheduledJob) {
  if (schedule.freq === "once") return `Once · ${formatWhen(schedule.once_at)}`;
  if (schedule.freq === "weekdays") return `Weekdays · ${schedule.time_of_day}`;
  if (schedule.freq === "weekly") return `Weekly · ${schedule.time_of_day}`;
  if (schedule.freq === "monthly") return `Monthly · ${schedule.time_of_day}`;
  if (schedule.freq === "custom") return `Custom · ${schedule.time_of_day}`;
  return `Daily · ${schedule.time_of_day}`;
}

export function ScheduleView() {
  const schedulesQuery = useSchedulesQuery();
  const schedules = schedulesQuery.data ?? [];
  const [tab, setTab] = useState<"list" | "calendar">("list");
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<ScheduledJob | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const pauseMutation = usePauseScheduleMutation();
  const resumeMutation = useResumeScheduleMutation();
  const deleteMutation = useDeleteScheduleMutation();
  const runNowMutation = useRunScheduleNowMutation();
  const firingsQuery = useScheduleFiringsQuery(selectedId);
  const calendarFiringsQuery = useAllScheduleFiringsQuery(
    schedules.map((schedule) => schedule.schedule_id),
    tab === "calendar",
  );

  return (
    <div className="mx-auto flex h-full max-w-4xl flex-col p-4 pb-20 text-zinc-900 md:p-8 dark:text-zinc-100">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-serif text-3xl leading-none tracking-tight text-zinc-900 sm:text-4xl dark:text-white">
            Schedule task
          </h1>
          <p className="mt-2 text-sm text-zinc-500">Run CoComputer later or on a cadence, like Manus scheduled tasks.</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className={toolbarControl}
            onClick={() => setTab((current) => (current === "list" ? "calendar" : "list"))}
          >
            {tab === "list" ? "Calendar" : "List"}
          </button>
          <button
            type="button"
            onClick={() => {
              setEditing(null);
              setEditorOpen(true);
            }}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-zinc-900 px-3 text-sm text-white dark:bg-white dark:text-zinc-900"
          >
            <Plus className="size-4" />
            New
          </button>
        </div>
      </div>

      {schedulesQuery.isError ? (
        <div className="mt-6 flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-600 dark:text-red-400">
          <AlertCircle className="size-4" />
          Could not load schedules.
        </div>
      ) : null}

      {tab === "calendar" ? (
        <div className="mt-8">
          <ScheduleCalendar schedules={schedules} firings={calendarFiringsQuery.data} />
        </div>
      ) : schedulesQuery.isLoading ? (
        <div className="mt-8 space-y-3">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-24 animate-pulse rounded-2xl bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : schedules.length === 0 ? (
        <div className="mt-8 rounded-2xl border border-dashed border-zinc-300 p-10 text-center font-mono text-xs uppercase tracking-wider text-zinc-500 dark:border-white/10">
          No scheduled tasks yet
        </div>
      ) : (
        <ul className="mt-8 space-y-3">
          {schedules.map((schedule) => {
            const selected = selectedId === schedule.schedule_id;
            return (
              <li
                key={schedule.schedule_id}
                className="rounded-2xl border border-zinc-200 bg-white p-4 dark:border-white/10 dark:bg-[#1a1a1c]"
              >
                <button type="button" className="w-full text-left" onClick={() => setSelectedId(schedule.schedule_id)}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-medium text-zinc-900 dark:text-white">{schedule.title}</div>
                      <div className="mt-1 text-sm text-zinc-500">{cadenceLabel(schedule)}</div>
                      <div className="mt-1 text-xs text-zinc-400">
                        Next {formatWhen(schedule.next_run_at)} · {schedule.status}
                      </div>
                    </div>
                  </div>
                </button>
                <div className="mt-3 flex flex-wrap gap-2">
                  {schedule.status === "paused" ? (
                    <button
                      type="button"
                      className={toolbarControl}
                      onClick={() => resumeMutation.mutate(schedule.schedule_id)}
                    >
                      <Play className="size-3.5" />
                      Resume
                    </button>
                  ) : (
                    <button
                      type="button"
                      className={toolbarControl}
                      onClick={() => pauseMutation.mutate(schedule.schedule_id)}
                    >
                      <Pause className="size-3.5" />
                      Pause
                    </button>
                  )}
                  <button
                    type="button"
                    className={toolbarControl}
                    onClick={() => runNowMutation.mutate(schedule.schedule_id)}
                  >
                    Run now
                  </button>
                  <button
                    type="button"
                    className={toolbarControl}
                    onClick={() => {
                      setEditing(schedule);
                      setEditorOpen(true);
                    }}
                  >
                    Edit
                  </button>
                  {schedule.last_session_id ? (
                    <Link href={sessionPath(schedule.last_session_id)} className={toolbarControl}>
                      Open last run
                    </Link>
                  ) : null}
                  <button
                    type="button"
                    className={toolbarControl}
                    onClick={() => deleteMutation.mutate(schedule.schedule_id)}
                  >
                    <Trash2 className="size-3.5" />
                    Delete
                  </button>
                </div>
                {selected ? (
                  <div className="mt-4 border-t border-zinc-200 pt-3 text-sm dark:border-white/10">
                    <div className="text-xs uppercase tracking-wide text-zinc-500">Recent runs</div>
                    {(firingsQuery.data ?? []).length === 0 ? (
                      <p className="mt-2 text-zinc-500">No firings yet.</p>
                    ) : (
                      <ul className="mt-2 space-y-1">
                        {(firingsQuery.data ?? []).slice(0, 8).map((firing) => (
                          <li key={firing.firing_id} className="flex items-center justify-between gap-2">
                            <span className="text-zinc-600 dark:text-zinc-300">
                              {formatWhen(firing.created_at)} · {firing.status}
                            </span>
                            {firing.session_id ? (
                              <Link href={sessionPath(firing.session_id)} className="text-xs text-zinc-500 underline">
                                Open
                              </Link>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}

      <AnimatePresence>
        {editorOpen ? <ScheduleEditor schedule={editing} onClose={() => setEditorOpen(false)} /> : null}
      </AnimatePresence>
    </div>
  );
}
