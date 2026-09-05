/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { type FormEvent, useMemo, useState } from "react";
import { Loader2, X } from "lucide-react";
import { motion } from "framer-motion";

import { useIntegrationsConnectionsQuery } from "@/lib/queries/integrations";
import {
  UNATTENDED_TOOL_OPTIONS,
  useCreateScheduleMutation,
  useTaskOptionsQuery,
  useUpdateScheduleMutation,
  type SchedulePayload,
  type ScheduledJob,
} from "@/lib/queries/schedule";

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const FREQ_OPTIONS: { id: string; label: string }[] = [
  { id: "once", label: "One time" },
  { id: "daily", label: "Daily" },
  { id: "weekdays", label: "Weekdays" },
  { id: "weekly", label: "Weekly" },
  { id: "monthly", label: "Monthly" },
  { id: "custom", label: "Custom days" },
];

function defaultTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function toDatetimeLocal(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function fromDatetimeLocal(value: string) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString();
}

type FormState = {
  title: string;
  prompt: string;
  timezone: string;
  freq: string;
  timeOfDay: string;
  daysOfWeek: number[];
  onceAt: string;
  dayOfMonth: number;
  runMode: string;
  continueTaskId: string;
  connectorIds: string[];
  skipConfirmations: boolean;
  allowedTools: string[];
};

function formFromSchedule(schedule?: ScheduledJob | null): FormState {
  return {
    title: schedule?.title ?? "",
    prompt: schedule?.prompt ?? "",
    timezone: schedule?.timezone || defaultTimezone(),
    freq: schedule?.freq || "daily",
    timeOfDay: schedule?.time_of_day || "09:00",
    daysOfWeek: schedule?.days_of_week ?? [],
    onceAt: toDatetimeLocal(schedule?.once_at ?? null),
    dayOfMonth: schedule?.day_of_month || 1,
    runMode: schedule?.run_mode || "new_task",
    continueTaskId: schedule?.continue_task_id ?? "",
    connectorIds: schedule?.connector_ids ?? [],
    skipConfirmations: Boolean(schedule?.skip_confirmations),
    allowedTools: schedule?.allowed_unattended_tools ?? [],
  };
}

function toPayload(form: FormState): SchedulePayload {
  return {
    title: form.title.trim() || form.prompt.slice(0, 80),
    prompt: form.prompt.trim(),
    timezone: form.timezone,
    freq: form.freq,
    time_of_day: form.timeOfDay,
    days_of_week: form.daysOfWeek,
    once_at: form.freq === "once" ? fromDatetimeLocal(form.onceAt) : null,
    day_of_month: form.dayOfMonth,
    run_mode: form.runMode,
    continue_task_id: form.runMode === "continue_task" ? form.continueTaskId.trim() : null,
    connector_ids: form.connectorIds,
    autonomy_mode: form.skipConfirmations ? "auto" : "manual",
    skip_confirmations: form.skipConfirmations,
    allowed_unattended_tools: form.skipConfirmations ? form.allowedTools : [],
  };
}

const fieldClass =
  "w-full rounded-lg border border-zinc-200 bg-white px-3.5 py-2 text-sm text-zinc-900 outline-none placeholder:text-zinc-400 focus:border-zinc-400 dark:border-white/10 dark:bg-zinc-900 dark:text-zinc-100";

export function ScheduleEditor({
  schedule,
  onClose,
}: {
  schedule?: ScheduledJob | null;
  onClose: () => void;
}) {
  const [form, setForm] = useState<FormState>(() => formFromSchedule(schedule));
  const [error, setError] = useState("");
  const createMutation = useCreateScheduleMutation();
  const updateMutation = useUpdateScheduleMutation();
  const connectionsQuery = useIntegrationsConnectionsQuery();
  const taskOptionsQuery = useTaskOptionsQuery(form.runMode === "continue_task");
  const connections = connectionsQuery.data ?? [];
  const tasks = taskOptionsQuery.data ?? [];
  const saving = createMutation.isPending || updateMutation.isPending;

  const weekdayToggles = useMemo(() => DAY_LABELS.map((label, index) => ({ label, index })), []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!form.prompt.trim()) {
      setError("Prompt is required.");
      return;
    }
    if (form.runMode === "continue_task" && !form.continueTaskId.trim()) {
      setError("Pick a task to continue.");
      return;
    }
    try {
      const payload = toPayload(form);
      if (schedule) {
        await updateMutation.mutateAsync({ scheduleId: schedule.schedule_id, payload });
      } else {
        await createMutation.mutateAsync(payload);
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save schedule");
    }
  }

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
      />
      <motion.form
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 10 }}
        onSubmit={submit}
        className="relative flex max-h-[min(880px,calc(100dvh-32px))] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-2xl dark:border-white/10 dark:bg-[#1a1a1c]"
      >
        <div className="flex items-center justify-between border-b border-zinc-200 px-5 py-4 dark:border-white/10">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
            {schedule ? "Edit schedule" : "New schedule"}
          </h2>
          <button type="button" onClick={onClose} className="rounded-lg p-1 text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800">
            <X className="size-5" />
          </button>
        </div>
        <div className="custom-scrollbar space-y-4 overflow-y-auto px-5 py-4">
          <label className="block space-y-1.5">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">Title</span>
            <input
              className={fieldClass}
              value={form.title}
              onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
              placeholder="Weekly competitor scan"
            />
          </label>
          <label className="block space-y-1.5">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">Prompt</span>
            <textarea
              className={`${fieldClass} min-h-28 resize-y`}
              value={form.prompt}
              onChange={(event) => setForm((current) => ({ ...current, prompt: event.target.value }))}
              placeholder="Every weekday at 9 AM, summarize AI news from the past 24 hours."
            />
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block space-y-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">Frequency</span>
              <select
                className={fieldClass}
                value={form.freq}
                onChange={(event) => setForm((current) => ({ ...current, freq: event.target.value }))}
              >
                {FREQ_OPTIONS.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block space-y-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">Timezone</span>
              <input
                className={fieldClass}
                value={form.timezone}
                onChange={(event) => setForm((current) => ({ ...current, timezone: event.target.value }))}
              />
            </label>
            {form.freq === "once" ? (
              <label className="block space-y-1.5 sm:col-span-2">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">Run at</span>
                <input
                  type="datetime-local"
                  className={fieldClass}
                  value={form.onceAt}
                  onChange={(event) => setForm((current) => ({ ...current, onceAt: event.target.value }))}
                />
              </label>
            ) : (
              <label className="block space-y-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">Time</span>
                <input
                  type="time"
                  className={fieldClass}
                  value={form.timeOfDay}
                  onChange={(event) => setForm((current) => ({ ...current, timeOfDay: event.target.value }))}
                />
              </label>
            )}
            {form.freq === "monthly" ? (
              <label className="block space-y-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">Day of month</span>
                <input
                  type="number"
                  min={1}
                  max={31}
                  className={fieldClass}
                  value={form.dayOfMonth}
                  onChange={(event) =>
                    setForm((current) => ({ ...current, dayOfMonth: Number(event.target.value) || 1 }))
                  }
                />
              </label>
            ) : null}
          </div>
          {form.freq === "weekly" || form.freq === "custom" ? (
            <div className="flex flex-wrap gap-2">
              {weekdayToggles.map((day) => {
                const selected = form.daysOfWeek.includes(day.index);
                return (
                  <button
                    key={day.index}
                    type="button"
                    onClick={() =>
                      setForm((current) => ({
                        ...current,
                        daysOfWeek: selected
                          ? current.daysOfWeek.filter((value) => value !== day.index)
                          : [...current.daysOfWeek, day.index],
                      }))
                    }
                    className={`rounded-full px-3 py-1 text-xs ${
                      selected
                        ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900"
                        : "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
                    }`}
                  >
                    {day.label}
                  </button>
                );
              })}
            </div>
          ) : null}
          <label className="block space-y-1.5">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">Run mode</span>
            <select
              className={fieldClass}
              value={form.runMode}
              onChange={(event) => setForm((current) => ({ ...current, runMode: event.target.value }))}
            >
              <option value="new_task">New task each run</option>
              <option value="continue_task">Continue the same task</option>
            </select>
          </label>
          {form.runMode === "continue_task" ? (
            <label className="block space-y-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">Continue task</span>
              <select
                className={fieldClass}
                value={form.continueTaskId}
                onChange={(event) => setForm((current) => ({ ...current, continueTaskId: event.target.value }))}
              >
                <option value="">Select a task</option>
                {form.continueTaskId && !tasks.some((task) => task.task_id === form.continueTaskId) ? (
                  <option value={form.continueTaskId}>{form.continueTaskId}</option>
                ) : null}
                {tasks.map((task) => (
                  <option key={task.task_id} value={task.task_id}>
                    {task.title || task.task_id}
                  </option>
                ))}
              </select>
              <span className="block text-xs text-zinc-500">
                Only durable CoComputer tasks can be continued on a schedule.
              </span>
            </label>
          ) : null}
          {connections.length > 0 ? (
            <div className="space-y-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">Connectors</span>
              <div className="flex flex-wrap gap-2">
                {connections.map((connection) => {
                  const selected = form.connectorIds.includes(connection.connection_id);
                  return (
                    <button
                      key={connection.connection_id}
                      type="button"
                      onClick={() =>
                        setForm((current) => ({
                          ...current,
                          connectorIds: selected
                            ? current.connectorIds.filter((id) => id !== connection.connection_id)
                            : [...current.connectorIds, connection.connection_id],
                        }))
                      }
                      className={`rounded-full px-3 py-1 text-xs ${
                        selected
                          ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900"
                          : "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
                      }`}
                    >
                      {connection.name}
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}
          <label className="flex items-start gap-3 rounded-xl border border-zinc-200 p-3 dark:border-white/10">
            <input
              type="checkbox"
              checked={form.skipConfirmations}
              onChange={(event) =>
                setForm((current) => ({ ...current, skipConfirmations: event.target.checked }))
              }
              className="mt-1"
            />
            <span>
              <span className="block text-sm font-medium text-zinc-900 dark:text-zinc-100">Skip confirmations & Auto-approve</span>
              <span className="text-xs text-zinc-500">
                Run unattended without asking questions. Automatically approves tool actions and permissions so the scheduled task runs completely hands-free.
              </span>
            </span>
          </label>
          {form.skipConfirmations ? (
            <div className="space-y-2 pl-1">
              {UNATTENDED_TOOL_OPTIONS.map((option) => {
                const checked = form.allowedTools.includes(option.id);
                return (
                  <label key={option.id} className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-200">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() =>
                        setForm((current) => ({
                          ...current,
                          allowedTools: checked
                            ? current.allowedTools.filter((id) => id !== option.id)
                            : [...current.allowedTools, option.id],
                        }))
                      }
                    />
                    {option.label}
                  </label>
                );
              })}
            </div>
          ) : null}
          {error ? <p className="text-sm text-red-600 dark:text-red-400">{error}</p> : null}
        </div>
        <div className="flex justify-end gap-2 border-t border-zinc-200 px-5 py-4 dark:border-white/10">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-2 text-sm text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm text-white dark:bg-white dark:text-zinc-900"
          >
            {saving ? <Loader2 className="size-4 animate-spin" /> : null}
            Save schedule
          </button>
        </div>
      </motion.form>
    </div>
  );
}
