/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiJson } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { queryKeys } from "@/lib/query-keys";

export type ScheduleFreq = "once" | "daily" | "weekdays" | "weekly" | "monthly" | "custom";
export type ScheduleRunMode = "new_task" | "continue_task";

export type ScheduledJob = {
  schedule_id: string;
  owner_id: string;
  title: string;
  prompt: string;
  timezone: string;
  freq: ScheduleFreq | string;
  time_of_day: string;
  days_of_week: number[];
  once_at: string | null;
  day_of_month: number;
  next_run_at: string | null;
  last_run_at: string | null;
  status: "active" | "paused" | "completed" | string;
  run_mode: ScheduleRunMode | string;
  continue_task_id: string | null;
  connector_ids: string[];
  tool_ids: string[];
  autonomy_mode: string;
  skip_confirmations: boolean;
  allowed_unattended_tools: string[];
  current_run_id: string | null;
  last_task_id: string | null;
  last_session_id: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type ScheduleFiring = {
  firing_id: string;
  schedule_id: string;
  scheduled_for: string | null;
  task_id: string | null;
  run_id: string | null;
  session_id: string | null;
  status: string;
  error: string | null;
  created_at: string | null;
};

export type SchedulePayload = {
  title?: string;
  prompt: string;
  timezone?: string;
  freq?: string;
  time_of_day?: string;
  days_of_week?: number[];
  once_at?: string | null;
  day_of_month?: number;
  run_mode?: string;
  continue_task_id?: string | null;
  connector_ids?: string[];
  tool_ids?: string[];
  autonomy_mode?: string;
  skip_confirmations?: boolean;
  allowed_unattended_tools?: string[];
};

export const UNATTENDED_TOOL_OPTIONS = [
  { id: "gmail_send", label: "Send email (Gmail)" },
  { id: "create_drive_doc", label: "Create Google Docs" },
  { id: "create_drive_sheet", label: "Create Google Sheets" },
  { id: "upload_drive_file", label: "Upload to Drive" },
  { id: "tasks_create", label: "Create Google Tasks" },
  { id: "slack_post", label: "Post to Slack" },
] as const;

export async function fetchSchedules(): Promise<ScheduledJob[]> {
  const body = await apiJson<{ schedules?: ScheduledJob[] }>("/api/v1/schedules");
  return body.schedules ?? [];
}

export function useSchedulesQuery() {
  const { user } = useAuth();
  return useQuery({
    queryKey: queryKeys.schedule.list(),
    queryFn: fetchSchedules,
    enabled: Boolean(user),
  });
}

export async function fetchScheduleFirings(scheduleId: string): Promise<ScheduleFiring[]> {
  const body = await apiJson<{ firings?: ScheduleFiring[] }>(
    `/api/v1/schedules/${encodeURIComponent(scheduleId)}/firings`,
  );
  return body.firings ?? [];
}

export function useScheduleFiringsQuery(scheduleId: string | null) {
  const { user } = useAuth();
  return useQuery({
    queryKey: queryKeys.schedule.firings(scheduleId || ""),
    queryFn: () => fetchScheduleFirings(scheduleId || ""),
    enabled: Boolean(user && scheduleId),
  });
}

export function useAllScheduleFiringsQuery(scheduleIds: string[], enabled: boolean) {
  const { user } = useAuth();
  const queries = useQueries({
    queries: scheduleIds.map((scheduleId) => ({
      queryKey: queryKeys.schedule.firings(scheduleId),
      queryFn: () => fetchScheduleFirings(scheduleId),
      enabled: Boolean(user) && enabled && Boolean(scheduleId),
    })),
  });
  return {
    data: queries.flatMap((query) => query.data ?? []),
    isLoading: queries.some((query) => query.isLoading),
  };
}

function invalidateSchedules(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: queryKeys.schedule.list() });
}

export function useCreateScheduleMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SchedulePayload) =>
      apiJson<{ schedule: ScheduledJob }>("/api/v1/schedules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
    onSuccess: () => invalidateSchedules(queryClient),
  });
}

export function useUpdateScheduleMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ scheduleId, payload }: { scheduleId: string; payload: SchedulePayload }) =>
      apiJson<{ schedule: ScheduledJob }>(`/api/v1/schedules/${encodeURIComponent(scheduleId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
    onSuccess: () => invalidateSchedules(queryClient),
  });
}

export function usePauseScheduleMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (scheduleId: string) =>
      apiJson(`/api/v1/schedules/${encodeURIComponent(scheduleId)}/pause`, { method: "POST" }),
    onSuccess: () => invalidateSchedules(queryClient),
  });
}

export function useResumeScheduleMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (scheduleId: string) =>
      apiJson(`/api/v1/schedules/${encodeURIComponent(scheduleId)}/resume`, { method: "POST" }),
    onSuccess: () => invalidateSchedules(queryClient),
  });
}

export function useDeleteScheduleMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (scheduleId: string) =>
      apiJson(`/api/v1/schedules/${encodeURIComponent(scheduleId)}`, { method: "DELETE" }),
    onSuccess: () => invalidateSchedules(queryClient),
  });
}

export function useRunScheduleNowMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (scheduleId: string) =>
      apiJson(`/api/v1/schedules/${encodeURIComponent(scheduleId)}/run-now`, { method: "POST" }),
    onSuccess: (_data, scheduleId) => {
      invalidateSchedules(queryClient);
      void queryClient.invalidateQueries({ queryKey: queryKeys.schedule.firings(scheduleId) });
    },
  });
}

export type HistoryTaskOption = {
  task_id: string;
  title: string;
  status: string;
  current_session_id?: string | null;
};

export async function fetchTaskOptions(): Promise<HistoryTaskOption[]> {
  const body = await apiJson<{ tasks?: HistoryTaskOption[] }>("/api/v1/tasks?limit=50");
  return (body.tasks ?? []).filter((task) => task.task_id.startsWith("task_"));
}

export function useTaskOptionsQuery(enabled: boolean) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["schedule", "task-options"],
    queryFn: fetchTaskOptions,
    enabled: Boolean(user) && enabled,
  });
}
