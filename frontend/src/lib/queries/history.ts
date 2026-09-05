/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiJson } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import type { RecentSession } from "@/lib/message-types";
import { queryKeys } from "@/lib/query-keys";
import { invalidateSessionLists } from "@/lib/queries/invalidate";

export async function fetchHistory(q: string): Promise<RecentSession[]> {
  const params = new URLSearchParams();
  params.set("limit", "100");
  if (q) params.set("q", q);
  const data = await apiJson<{ sessions?: RecentSession[] }>(`/api/v1/history?${params.toString()}`);
  return data.sessions ?? [];
}

export function useHistoryQuery(q: string) {
  const { user } = useAuth();
  return useQuery({
    queryKey: queryKeys.history(q),
    queryFn: () => fetchHistory(q),
    enabled: Boolean(user),
    placeholderData: keepPreviousData,
  });
}

export function useDeleteHistorySessionMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (sessionId: string) => {
      await apiJson(`/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
      return sessionId;
    },
    onSuccess: () => invalidateSessionLists(queryClient),
  });
}

export function useDeleteHistorySessionsMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (sessionIds: string[]) => {
      const results = await Promise.allSettled(
        sessionIds.map(async (sessionId) => {
          await apiJson(`/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
          return sessionId;
        }),
      );
      const succeeded: string[] = [];
      let failed = 0;
      for (const result of results) {
        if (result.status === "fulfilled") succeeded.push(result.value);
        else failed += 1;
      }
      return { succeeded, failed };
    },
    onSuccess: () => invalidateSessionLists(queryClient),
  });
}
