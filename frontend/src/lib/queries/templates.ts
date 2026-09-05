/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useToast } from "@/components/toast-provider";
import { apiJson, getApiErrorCode } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import type {
  WorkflowTemplateData,
  WorkflowTemplateInputField,
  WorkflowTemplateRunResult,
} from "@/lib/message-types";
import { queryKeys } from "@/lib/query-keys";
import { invalidateSessionLists } from "@/lib/queries/invalidate";
import { useSettings } from "@/lib/settings-context";

export type TemplatePayload = {
  name?: string;
  description?: string;
  instructions?: string;
  inputFields?: WorkflowTemplateInputField[];
  status?: "draft" | "published";
};

export type CreateTemplateOptions = TemplatePayload & {
  sourceSessionId?: string;
};

function buildTemplateBody(payload?: TemplatePayload) {
  return {
    name: payload?.name ?? null,
    description: payload?.description ?? null,
    instructions: payload?.instructions ?? null,
    input_fields: payload?.inputFields ?? [],
  };
}

export async function fetchTemplates(): Promise<WorkflowTemplateData[]> {
  const body = await apiJson<{ templates?: WorkflowTemplateData[] }>("/api/v1/templates");
  return body.templates ?? [];
}

export function useTemplatesQuery() {
  const { user } = useAuth();
  return useQuery({
    queryKey: queryKeys.templates(),
    queryFn: fetchTemplates,
    enabled: Boolean(user),
  });
}

function useTemplateByokHandler() {
  const { toast } = useToast();
  const { openSettings } = useSettings();
  return useCallback(
    (error: unknown) => {
      if (getApiErrorCode(error) === "BYOK_REQUIRED") {
        const message = error instanceof Error ? error.message : "API keys required";
        toast(message, "error");
        openSettings("api");
      }
    },
    [openSettings, toast],
  );
}

export function useCreateTemplateMutation() {
  const queryClient = useQueryClient();
  const handleByok = useTemplateByokHandler();
  return useMutation({
    mutationFn: async (options: CreateTemplateOptions) => {
      return apiJson<WorkflowTemplateData>("/api/v1/templates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...(options.sourceSessionId ? { source_session_id: options.sourceSessionId } : {}),
          ...buildTemplateBody(options),
        }),
      });
    },
    onError: handleByok,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.templates() });
    },
  });
}

export function useSaveSessionAsTemplateMutation() {
  const queryClient = useQueryClient();
  const handleByok = useTemplateByokHandler();
  return useMutation({
    mutationFn: async ({
      sessionId,
      payload,
    }: {
      sessionId: string;
      payload?: TemplatePayload;
    }) => {
      return apiJson<WorkflowTemplateData>(
        `/api/v1/sessions/${encodeURIComponent(sessionId)}/template`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(buildTemplateBody(payload)),
        },
      );
    },
    onError: handleByok,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.templates() });
    },
  });
}

export function useUpdateTemplateMutation() {
  const queryClient = useQueryClient();
  const handleByok = useTemplateByokHandler();
  return useMutation({
    mutationFn: async ({
      templateId,
      payload,
    }: {
      templateId: string;
      payload: TemplatePayload;
    }) => {
      return apiJson<WorkflowTemplateData>(`/api/v1/templates/${encodeURIComponent(templateId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: payload.name ?? null,
          description: payload.description ?? null,
          instructions: payload.instructions ?? null,
          input_fields: payload.inputFields ?? null,
          status: payload.status ?? null,
        }),
      });
    },
    onError: handleByok,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.templates() });
    },
  });
}

export function useDeleteTemplateMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (templateId: string) => {
      await apiJson(`/api/v1/templates/${encodeURIComponent(templateId)}`, {
        method: "DELETE",
      });
      return templateId;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.templates() });
    },
  });
}

export function useRunTemplateMutation() {
  const queryClient = useQueryClient();
  const handleByok = useTemplateByokHandler();
  return useMutation({
    mutationFn: async ({
      templateId,
      inputs,
    }: {
      templateId: string;
      inputs: Record<string, string>;
    }) => {
      return apiJson<WorkflowTemplateRunResult>(
        `/api/v1/templates/${encodeURIComponent(templateId)}/run`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ inputs }),
        },
      );
    },
    onError: handleByok,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.templates() });
      invalidateSessionLists(queryClient);
    },
  });
}
