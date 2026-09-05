/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import type { LibraryCategory, LibraryItem } from "@/lib/message-types";

export type LibraryFilterId = "all" | LibraryCategory;

export const LIBRARY_FILTERS: Array<{ id: LibraryFilterId; label: string }> = [
  { id: "all", label: "All" },
  { id: "slides", label: "Slides" },
  { id: "documents", label: "Documents" },
  { id: "spreadsheets", label: "Spreadsheets" },
  { id: "images", label: "Images" },
  { id: "media", label: "Audio & Video" },
  { id: "others", label: "Others" },
];

export function filterLibraryItems(
  items: LibraryItem[],
  category: LibraryFilterId,
): LibraryItem[] {
  if (category === "all") return items;
  return items.filter((item) => item.category === category);
}

export type LibraryGroup = {
  session_id: string;
  session_title: string;
  timestamp: string | null;
  items: LibraryItem[];
};

export function groupLibraryItems(items: LibraryItem[]): LibraryGroup[] {
  const order: string[] = [];
  const grouped = new Map<string, LibraryItem[]>();

  for (const item of items) {
    const key = item.session_id || "unknown";
    if (!grouped.has(key)) {
      order.push(key);
      grouped.set(key, []);
    }
    grouped.get(key)!.push(item);
  }

  return order.map((session_id) => {
    const groupItems = grouped.get(session_id) ?? [];
    return {
      session_id,
      session_title: groupItems[0]?.session_title || "Untitled session",
      timestamp: groupItems[0]?.artifact.created_at ?? null,
      items: groupItems,
    };
  });
}

export function formatLibraryTimestamp(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";

  const time = date.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const days = Math.round((startOfToday.getTime() - startOfDate.getTime()) / 86_400_000);

  if (days === 0) return `Today, ${time}`;
  if (days === 1) return `Yesterday, ${time}`;
  if (days > 1 && days < 7) {
    return `${date.toLocaleDateString(undefined, { weekday: "short" })}, ${time}`;
  }
  return `${date.toLocaleDateString(undefined, { month: "short", day: "numeric" })}, ${time}`;
}
