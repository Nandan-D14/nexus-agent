/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiJson } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import type { CatalogItem, IntegrationConnection } from "@/lib/connectors";
import { isGoogleProvider, mergeCatalogDefaults } from "@/lib/connectors";
import { queryKeys } from "@/lib/query-keys";
import { invalidateIntegrations } from "@/lib/queries/invalidate";

export async function fetchIntegrationsCatalog(): Promise<CatalogItem[]> {
  const body = await apiJson<{ catalog?: CatalogItem[] }>("/api/v1/integrations/catalog");
  return mergeCatalogDefaults(body.catalog ?? []);
}

export async function fetchIntegrationsConnections(): Promise<IntegrationConnection[]> {
  const body = await apiJson<{ connections?: IntegrationConnection[] }>(
    "/api/v1/integrations/connections",
  );
  return body.connections ?? [];
}

export function useIntegrationsCatalogQuery() {
  const { user } = useAuth();
  return useQuery({
    queryKey: queryKeys.integrations.catalog(),
    queryFn: fetchIntegrationsCatalog,
    enabled: Boolean(user),
  });
}

export function useIntegrationsConnectionsQuery() {
  const { user } = useAuth();
  return useQuery({
    queryKey: queryKeys.integrations.connections(),
    queryFn: fetchIntegrationsConnections,
    enabled: Boolean(user),
  });
}

export type CalendarEvent = {
  id: string;
  summary: string;
  start: string;
  end: string;
  htmlLink: string;
  status: string;
};

export type CalendarEventsRange = {
  maxResults?: number;
  timeMin?: string;
  timeMax?: string;
};

export async function fetchCalendarEvents(
  options: CalendarEventsRange = {},
): Promise<CalendarEvent[]> {
  const maxResults = options.maxResults ?? 10;
  const params = new URLSearchParams({ max_results: String(maxResults) });
  if (options.timeMin) params.set("time_min", options.timeMin);
  if (options.timeMax) params.set("time_max", options.timeMax);
  const body = await apiJson<{ events?: CalendarEvent[] }>(
    `/api/v1/calendar/events?${params.toString()}`,
  );
  return body.events ?? [];
}

export function useCalendarEventsQuery(enabled: boolean, options: CalendarEventsRange = {}) {
  const { user } = useAuth();
  return useQuery({
    queryKey: queryKeys.calendar.events(options),
    queryFn: () => fetchCalendarEvents(options),
    enabled: Boolean(user) && enabled,
    retry: false,
  });
}

export function useToggleIntegrationMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (connection: IntegrationConnection) => {
      if (isGoogleProvider(connection.provider)) {
        throw new Error("Google connections cannot be toggled from this control.");
      }
      await apiJson(`/api/v1/integrations/${encodeURIComponent(connection.connection_id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !connection.enabled }),
      });
    },
    onSuccess: () => invalidateIntegrations(queryClient),
  });
}

export function useDeleteIntegrationMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (connection: IntegrationConnection) => {
      const path = isGoogleProvider(connection.provider)
        ? "/api/v1/auth/google"
        : connection.provider === "github"
          ? "/api/v1/auth/github"
          : `/api/v1/integrations/${encodeURIComponent(connection.connection_id)}`;
      await apiJson(path, { method: "DELETE" });
    },
    onSuccess: () => invalidateIntegrations(queryClient),
  });
}

export function useDisconnectGoogleMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await apiJson("/api/v1/auth/google", { method: "DELETE" });
    },
    onSuccess: () => invalidateIntegrations(queryClient),
  });
}

export function useConnectMcpMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { name: string; url: string; bearerToken: string }) => {
      await apiJson("/api/v1/integrations/mcp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: payload.name,
          url: payload.url,
          bearer_token: payload.bearerToken || null,
          enabled: true,
        }),
      });
    },
    onSuccess: () => invalidateIntegrations(queryClient),
  });
}

export function useConnectGithubMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (token: string) => {
      await apiJson("/api/v1/integrations/github", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, enabled: true }),
      });
    },
    onSuccess: () => invalidateIntegrations(queryClient),
  });
}

export function useConnectSlackMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (token: string) => {
      await apiJson("/api/v1/integrations/slack", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, enabled: true }),
      });
    },
    onSuccess: () => invalidateIntegrations(queryClient),
  });
}

export function useConnectTavilyMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (apiKey: string) => {
      await apiJson("/api/v1/integrations/tavily", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: apiKey, enabled: true }),
      });
    },
    onSuccess: () => invalidateIntegrations(queryClient),
  });
}

export function useConnectComposioMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (consumerApiKey: string) => {
      await apiJson("/api/v1/integrations/composio", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          consumer_api_key: consumerApiKey.trim() || null,
          enabled: true,
        }),
      });
    },
    onSuccess: () => invalidateIntegrations(queryClient),
  });
}

export function useConnectTinyfishMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (apiKey: string) => {
      await apiJson("/api/v1/integrations/tinyfish", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: apiKey, enabled: true }),
      });
    },
    onSuccess: () => invalidateIntegrations(queryClient),
  });
}

export function useConnectVyoraMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (apiKey: string) => {
      await apiJson("/api/v1/integrations/vyora", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: apiKey, enabled: true }),
      });
    },
    onSuccess: () => invalidateIntegrations(queryClient),
  });
}

export function useConnectOpenAIMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (apiKey: string) => {
      await apiJson("/api/v1/integrations/openai", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: apiKey, enabled: true }),
      });
    },
    onSuccess: () => invalidateIntegrations(queryClient),
  });
}
