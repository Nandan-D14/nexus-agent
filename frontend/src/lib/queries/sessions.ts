/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useQuery } from "@tanstack/react-query";

import { apiJson } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import type { RecentSession } from "@/lib/message-types";
import { queryKeys } from "@/lib/query-keys";

export async function fetchRecentSessions(limit: number): Promise<RecentSession[]> {
  const body = await apiJson<{ sessions?: RecentSession[] }>(
    `/api/v1/dashboard/sessions?limit=${limit}`,
  );
  return body.sessions ?? [];
}

export function useRecentSessionsQuery(limit: number) {
  const { user } = useAuth();
  return useQuery({
    queryKey: queryKeys.sessions.recent(limit),
    queryFn: () => fetchRecentSessions(limit),
    enabled: Boolean(user),
  });
}

export type ActiveSession = {
  session_id: string;
  title: string;
  status: string;
  created_at: string | null;
  last_active_at: string | null;
  stream_url: string | null;
  message_count: number;
  token_totals: {
    input: number;
    output: number;
    total: number;
    bySource?: Record<string, { input: number; output: number; total: number; model?: string }>;
  };
  token_tracking_started_at: string | null;
  token_coverage: "tracked" | "no_data";
};

export async function fetchActiveSessions(): Promise<ActiveSession[]> {
  const body = await apiJson<{ sessions?: ActiveSession[] }>("/api/v1/sessions/active");
  return body.sessions ?? [];
}

export function useActiveSessionsQuery() {
  const { user } = useAuth();
  return useQuery({
    queryKey: queryKeys.sessions.active(),
    queryFn: fetchActiveSessions,
    enabled: Boolean(user),
  });
}
