/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

export function formatTimeAgo(dateStr: string | null | undefined): string {
  if (!dateStr) return "recently";
  const date = new Date(dateStr);
  const now = new Date();
  const diffSec = Math.floor((now.getTime() - date.getTime()) / 1000);
  if (diffSec < 60) return "just now";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}h ago`;
  const diffDays = Math.floor(diffHour / 24);
  if (diffDays === 1) return "yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

export function formatEventWhen(start: string | null | undefined): string {
  if (!start) return "No time set";
  const date = new Date(start);
  if (Number.isNaN(date.getTime())) return start;
  if (!start.includes("T")) {
    return date.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
  }
  return date.toLocaleString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function dateKey(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function eventDateKey(start: string | null | undefined): string | null {
  if (!start) return null;
  if (!start.includes("T")) return start.slice(0, 10);
  const date = new Date(start);
  if (Number.isNaN(date.getTime())) return null;
  return dateKey(date);
}

export function monthUtcBounds(year: number, monthIndex: number): { timeMin: string; timeMax: string } {
  const start = new Date(year, monthIndex, 1);
  const end = new Date(year, monthIndex + 1, 1);
  return { timeMin: start.toISOString(), timeMax: end.toISOString() };
}

export type MonthCell = {
  key: string;
  date: Date;
  inMonth: boolean;
  isToday: boolean;
};

export function buildMonthCells(year: number, monthIndex: number): MonthCell[] {
  const firstWeekday = new Date(year, monthIndex, 1).getDay();
  const daysInMonth = new Date(year, monthIndex + 1, 0).getDate();
  const prevMonthDays = new Date(year, monthIndex, 0).getDate();
  const todayKey = dateKey(new Date());
  const cells: MonthCell[] = [];

  for (let i = 0; i < 42; i += 1) {
    const dayNum = i - firstWeekday + 1;
    let date: Date;
    let inMonth = true;
    if (dayNum < 1) {
      date = new Date(year, monthIndex - 1, prevMonthDays + dayNum);
      inMonth = false;
    } else if (dayNum > daysInMonth) {
      date = new Date(year, monthIndex + 1, dayNum - daysInMonth);
      inMonth = false;
    } else {
      date = new Date(year, monthIndex, dayNum);
    }
    const key = dateKey(date);
    cells.push({ key, date, inMonth, isToday: key === todayKey });
  }

  return cells;
}
