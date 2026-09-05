/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { keepPreviousData, useInfiniteQuery } from "@tanstack/react-query";

import { apiJson } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import type { LibraryItem } from "@/lib/message-types";
import { queryKeys } from "@/lib/query-keys";

export type LibraryPage = {
  items: LibraryItem[];
  nextCursor: string | null;
};

export async function fetchLibraryPage(q: string, cursor: string | null): Promise<LibraryPage> {
  const params = new URLSearchParams();
  params.set("limit", "100");
  if (cursor) params.set("cursor", cursor);
  if (q) params.set("q", q);
  const data = await apiJson<{ items?: LibraryItem[]; next_cursor?: string | null }>(
    `/api/v1/library?${params.toString()}`,
  );
  return {
    items: data.items ?? [],
    nextCursor: data.next_cursor ?? null,
  };
}

export function useLibraryInfiniteQuery(q: string) {
  const { user } = useAuth();
  return useInfiniteQuery({
    queryKey: queryKeys.library(q),
    queryFn: ({ pageParam }) => fetchLibraryPage(q, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.nextCursor ?? undefined,
    enabled: Boolean(user),
    placeholderData: keepPreviousData,
  });
}
