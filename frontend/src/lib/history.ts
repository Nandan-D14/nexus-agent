/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import type { RecentSession } from "@/lib/message-types";

export type HistoryFilterId = "all" | "active" | "ended";

export const HISTORY_FILTERS: Array<{ id: HistoryFilterId; label: string }> = [
  { id: "all", label: "All" },
  { id: "active", label: "Active" },
  { id: "ended", label: "Ended" },
];

const NAMED_BUCKETS = ["Today", "Yesterday", "This Month", "This Year"] as const;
const NAMED_BUCKET_SET = new Set<string>(NAMED_BUCKETS);

export type HistoryGroup = {
  label: string;
  sessions: RecentSession[];
};

export type HistoryPreviewPart = {
  type: "text" | "bold" | "heading";
  value: string;
};

export function historyActivityAt(
  session: Pick<RecentSession, "updated_at" | "created_at">,
): string | null {
  return session.updated_at || session.created_at || null;
}

export function filterHistorySessions(
  sessions: RecentSession[],
  filter: HistoryFilterId,
): RecentSession[] {
  if (filter === "all") return sessions;
  return sessions.filter((session) => {
    const status = session.status;
    if (filter === "active") return status === "ready" || status === "active";
    return status === "ended" || status === "error";
  });
}

export function historyPreview(session: RecentSession): string {
  const preview = session.handoff_summary?.preview || session.summary;
  return typeof preview === "string" ? preview.trim() : "";
}

function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function calendarDaysAgo(date: Date, now: Date): number {
  const startOfToday = startOfDay(now);
  const startOfDate = startOfDay(date);
  return Math.round((startOfToday.getTime() - startOfDate.getTime()) / 86_400_000);
}

function bucketLabel(date: Date, now: Date): string {
  const days = calendarDaysAgo(date, now);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth()) {
    return "This Month";
  }
  if (date.getFullYear() === now.getFullYear()) return "This Year";
  return String(date.getFullYear());
}

export function groupHistorySessions(
  sessions: RecentSession[],
  now = new Date(),
): HistoryGroup[] {
  const groups = new Map<string, RecentSession[]>();
  const order: string[] = [];

  const sorted = [...sessions].sort((left, right) => {
    const leftTime = Date.parse(historyActivityAt(left) || "") || 0;
    const rightTime = Date.parse(historyActivityAt(right) || "") || 0;
    return rightTime - leftTime;
  });

  for (const session of sorted) {
    const raw = historyActivityAt(session);
    const date = raw ? new Date(raw) : now;
    const label = Number.isNaN(date.getTime()) ? "Today" : bucketLabel(date, now);
    if (!groups.has(label)) {
      groups.set(label, []);
      order.push(label);
    }
    groups.get(label)!.push(session);
  }

  const named = NAMED_BUCKETS.filter((label) => groups.has(label));
  const older = order.filter((label) => !NAMED_BUCKET_SET.has(label));

  return [...named, ...older].map((label) => ({
    label,
    sessions: groups.get(label) ?? [],
  }));
}

export function formatHistoryDate(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

function softenMarkdown(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/^>\s?/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/^\s*\d+\.\s+/gm, "");
}

function tokenizeInline(text: string, heading: boolean): HistoryPreviewPart[] {
  const parts: HistoryPreviewPart[] = [];
  const bold = /\*\*([^*]+)\*\*/g;
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = bold.exec(text)) !== null) {
    if (match.index > last) {
      parts.push({ type: heading ? "heading" : "text", value: text.slice(last, match.index) });
    }
    parts.push({ type: "bold", value: match[1] });
    last = match.index + match[0].length;
  }
  if (last < text.length) {
    parts.push({ type: heading ? "heading" : "text", value: text.slice(last) });
  }
  return parts;
}

export function parseHistoryPreview(raw: string): HistoryPreviewPart[] {
  const text = softenMarkdown(raw.trim());
  if (!text) return [];

  const parts: HistoryPreviewPart[] = [];
  const lines = text.split(/\n+/);
  lines.forEach((line, index) => {
    if (index > 0) parts.push({ type: "text", value: " " });
    const headingMatch = line.match(/^#{1,6}\s+(.*)$/);
    const content = headingMatch ? headingMatch[1] : line;
    parts.push(...tokenizeInline(content, Boolean(headingMatch)));
  });
  return parts.filter((part) => part.value.length > 0);
}
