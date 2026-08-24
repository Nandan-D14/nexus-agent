/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useQuery } from "@tanstack/react-query";

import { apiJson } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import type { UsageChartPoint } from "@/components/usage-chart";
import { queryKeys } from "@/lib/query-keys";

export type TokenTotals = {
  input: number;
  output: number;
  total: number;
  bySource?: Record<
    string,
    { input: number; output: number; total: number; model?: string }
  >;
};

export type DashboardStats = {
  total_sessions: number;
  total_messages: number;
  active_sessions: number;
  sessions_this_week: number;
  avg_session_duration_mins: number;
  token_totals: TokenTotals;
  tracked_sources: string[];
  untracked_sources: string[];
};

export type DashboardSessionUsage = {
  session_id: string;
  title: string;
  status: string;
  created_at: string | null;
  message_count: number;
  token_totals: TokenTotals;
  token_tracking_started_at: string | null;
  token_coverage: "tracked" | "no_data";
};

export const EMPTY_TOKEN_TOTALS: TokenTotals = {
  input: 0,
  output: 0,
  total: 0,
  bySource: {},
};

export async function fetchDashboardStats(): Promise<DashboardStats> {
  const statsBody = await apiJson<DashboardStats>("/api/v1/dashboard/stats");
  return {
    ...statsBody,
    token_totals: statsBody.token_totals || EMPTY_TOKEN_TOTALS,
  };
}

export async function fetchDashboardUsage(days: number): Promise<UsageChartPoint[]> {
  const body = await apiJson<{ chart?: UsageChartPoint[] }>(
    `/api/v1/dashboard/usage?days=${days}`,
  );
  return body.chart ?? [];
}

export async function fetchDashboardSessions(limit: number): Promise<DashboardSessionUsage[]> {
  const body = await apiJson<{ sessions?: DashboardSessionUsage[] }>(
    `/api/v1/dashboard/sessions?limit=${limit}`,
  );
  return body.sessions ?? [];
}

export function useDashboardStatsQuery() {
  const { user } = useAuth();
  return useQuery({
    queryKey: queryKeys.dashboard.stats(),
    queryFn: fetchDashboardStats,
    enabled: Boolean(user),
  });
}

export function useDashboardUsageQuery(days: number) {
  const { user } = useAuth();
  return useQuery({
    queryKey: queryKeys.dashboard.usage(days),
    queryFn: () => fetchDashboardUsage(days),
    enabled: Boolean(user),
  });
}

export function useDashboardSessionsQuery(limit: number) {
  const { user } = useAuth();
  return useQuery({
    queryKey: queryKeys.sessions.recent(limit),
    queryFn: () => fetchDashboardSessions(limit),
    enabled: Boolean(user),
  });
}
