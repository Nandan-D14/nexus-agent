/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useMemo, useState } from "react";

import type { ScheduleFiring, ScheduledJob } from "@/lib/queries/schedule";

function startOfMonth(date: Date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function addMonths(date: Date, count: number) {
  return new Date(date.getFullYear(), date.getMonth() + count, 1);
}

function sameDay(left: Date, right: Date) {
  return (
    left.getFullYear() === right.getFullYear() &&
    left.getMonth() === right.getMonth() &&
    left.getDate() === right.getDate()
  );
}

function parseInstant(value: string | null) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function ScheduleCalendar({
  schedules,
  firings,
}: {
  schedules: ScheduledJob[];
  firings: ScheduleFiring[];
}) {
  const [cursor, setCursor] = useState(() => startOfMonth(new Date()));
  const [selected, setSelected] = useState<Date | null>(null);

  const cells = useMemo(() => {
    const first = startOfMonth(cursor);
    const startOffset = (first.getDay() + 6) % 7;
    const daysInMonth = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0).getDate();
    const items: Array<{ date: Date; inMonth: boolean }> = [];
    for (let i = 0; i < startOffset; i += 1) {
      const date = new Date(first);
      date.setDate(date.getDate() - (startOffset - i));
      items.push({ date, inMonth: false });
    }
    for (let day = 1; day <= daysInMonth; day += 1) {
      items.push({ date: new Date(cursor.getFullYear(), cursor.getMonth(), day), inMonth: true });
    }
    while (items.length % 7 !== 0) {
      const last = items[items.length - 1]?.date ?? first;
      const next = new Date(last);
      next.setDate(next.getDate() + 1);
      items.push({ date: next, inMonth: false });
    }
    return items;
  }, [cursor]);

  const eventsByDay = useMemo(() => {
    const map = new Map<string, { upcoming: ScheduledJob[]; past: ScheduleFiring[] }>();
    const keyFor = (date: Date) => `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
    for (const schedule of schedules) {
      const next = parseInstant(schedule.next_run_at);
      if (!next) continue;
      const key = keyFor(next);
      const bucket = map.get(key) ?? { upcoming: [], past: [] };
      bucket.upcoming.push(schedule);
      map.set(key, bucket);
    }
    for (const firing of firings) {
      const when = parseInstant(firing.scheduled_for || firing.created_at);
      if (!when) continue;
      const key = keyFor(when);
      const bucket = map.get(key) ?? { upcoming: [], past: [] };
      bucket.past.push(firing);
      map.set(key, bucket);
    }
    return map;
  }, [firings, schedules]);

  const selectedKey = selected
    ? `${selected.getFullYear()}-${selected.getMonth()}-${selected.getDate()}`
    : "";
  const selectedEvents = eventsByDay.get(selectedKey);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => setCursor((current) => addMonths(current, -1))}
          className="rounded-lg bg-zinc-100 px-3 py-1.5 text-sm dark:bg-zinc-800"
        >
          Previous
        </button>
        <div className="text-sm font-medium text-zinc-900 dark:text-white">
          {cursor.toLocaleString(undefined, { month: "long", year: "numeric" })}
        </div>
        <button
          type="button"
          onClick={() => setCursor((current) => addMonths(current, 1))}
          className="rounded-lg bg-zinc-100 px-3 py-1.5 text-sm dark:bg-zinc-800"
        >
          Next
        </button>
      </div>
      <div className="grid grid-cols-7 gap-1 text-center text-[11px] uppercase tracking-wide text-zinc-500">
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day) => (
          <div key={day}>{day}</div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {cells.map((cell) => {
          const key = `${cell.date.getFullYear()}-${cell.date.getMonth()}-${cell.date.getDate()}`;
          const bucket = eventsByDay.get(key);
          const count = (bucket?.upcoming.length ?? 0) + (bucket?.past.length ?? 0);
          const isSelected = selected ? sameDay(cell.date, selected) : false;
          return (
            <button
              key={key + String(cell.inMonth)}
              type="button"
              onClick={() => setSelected(cell.date)}
              className={`min-h-16 rounded-xl border p-2 text-left text-sm ${
                isSelected
                  ? "border-zinc-900 dark:border-white"
                  : "border-zinc-200 dark:border-white/10"
              } ${cell.inMonth ? "bg-white dark:bg-[#1a1a1c]" : "bg-zinc-50 text-zinc-400 dark:bg-zinc-900/40"}`}
            >
              <div>{cell.date.getDate()}</div>
              {count > 0 ? (
                <div className="mt-2 h-1.5 w-1.5 rounded-full bg-emerald-500" />
              ) : null}
            </button>
          );
        })}
      </div>
      {selected ? (
        <div className="rounded-2xl border border-zinc-200 p-4 dark:border-white/10">
          <div className="text-sm font-medium text-zinc-900 dark:text-white">
            {selected.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
          </div>
          {!selectedEvents || (selectedEvents.upcoming.length === 0 && selectedEvents.past.length === 0) ? (
            <p className="mt-2 text-sm text-zinc-500">No scheduled work this day.</p>
          ) : (
            <ul className="mt-3 space-y-2 text-sm">
              {selectedEvents.upcoming.map((item) => (
                <li key={item.schedule_id} className="text-zinc-700 dark:text-zinc-200">
                  Upcoming: {item.title}
                </li>
              ))}
              {selectedEvents.past.map((item) => {
                const job = schedules.find((schedule) => schedule.schedule_id === item.schedule_id);
                return (
                  <li key={item.firing_id} className="text-zinc-500">
                    Ran: {job?.title || "Scheduled task"} · {item.status}
                    {item.error ? ` — ${item.error}` : ""}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
