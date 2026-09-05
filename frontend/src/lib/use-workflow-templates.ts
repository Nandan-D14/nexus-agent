/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useCallback, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { apiJson } from "./api-client";
import type {
  WorkflowTemplateData,
  WorkflowTemplateRunResult,
} from "./message-types";
import { queryKeys } from "./query-keys";
import {
  fetchTemplates,
  useCreateTemplateMutation,
  useDeleteTemplateMutation,
  useRunTemplateMutation,
  useSaveSessionAsTemplateMutation,
  useUpdateTemplateMutation,
  type CreateTemplateOptions,
  type TemplatePayload,
} from "./queries/templates";

type TemplatePayloadCompat = TemplatePayload;

export interface UseWorkflowTemplatesReturn {
  listTemplates: (query?: string) => Promise<WorkflowTemplateData[]>;
  getTemplate: (templateId: string) => Promise<WorkflowTemplateData | null>;
  createTemplate: (options: CreateTemplateOptions) => Promise<WorkflowTemplateData | null>;
  saveSessionAsTemplate: (sessionId: string, payload?: TemplatePayloadCompat) => Promise<WorkflowTemplateData | null>;
  updateTemplate: (templateId: string, payload: TemplatePayloadCompat) => Promise<WorkflowTemplateData | null>;
  deleteTemplate: (templateId: string) => Promise<boolean>;
  runTemplate: (templateId: string, inputs: Record<string, string>) => Promise<WorkflowTemplateRunResult | null>;
  isLoading: boolean;
  error: string | null;
}

export function useWorkflowTemplates(): UseWorkflowTemplatesReturn {
  const queryClient = useQueryClient();
  const createMutation = useCreateTemplateMutation();
  const saveSessionMutation = useSaveSessionAsTemplateMutation();
  const updateMutation = useUpdateTemplateMutation();
  const deleteMutation = useDeleteTemplateMutation();
  const runMutation = useRunTemplateMutation();

  const error =
    (createMutation.error instanceof Error ? createMutation.error.message : null) ??
    (saveSessionMutation.error instanceof Error ? saveSessionMutation.error.message : null) ??
    (updateMutation.error instanceof Error ? updateMutation.error.message : null) ??
    (deleteMutation.error instanceof Error ? deleteMutation.error.message : null) ??
    (runMutation.error instanceof Error ? runMutation.error.message : null);

  const listTemplates = useCallback(
    async (_query?: string) => {
      try {
        return await queryClient.fetchQuery({
          queryKey: queryKeys.templates(),
          queryFn: fetchTemplates,
        });
      } catch {
        return [];
      }
    },
    [queryClient],
  );

  const getTemplate = useCallback(async (templateId: string) => {
    try {
      return await apiJson<WorkflowTemplateData>(
        `/api/v1/templates/${encodeURIComponent(templateId)}`,
      );
    } catch {
      return null;
    }
  }, []);

  const createTemplate = useCallback(
    async (options: CreateTemplateOptions) => {
      try {
        return await createMutation.mutateAsync(options);
      } catch {
        return null;
      }
    },
    [createMutation.mutateAsync],
  );

  const saveSessionAsTemplate = useCallback(
    async (sessionId: string, payload?: TemplatePayloadCompat) => {
      try {
        return await saveSessionMutation.mutateAsync({ sessionId, payload });
      } catch {
        return null;
      }
    },
    [saveSessionMutation.mutateAsync],
  );

  const updateTemplate = useCallback(
    async (templateId: string, payload: TemplatePayloadCompat) => {
      try {
        return await updateMutation.mutateAsync({ templateId, payload });
      } catch {
        return null;
      }
    },
    [updateMutation.mutateAsync],
  );

  const deleteTemplate = useCallback(
    async (templateId: string) => {
      try {
        await deleteMutation.mutateAsync(templateId);
        return true;
      } catch {
        return false;
      }
    },
    [deleteMutation.mutateAsync],
  );

  const runTemplate = useCallback(
    async (templateId: string, inputs: Record<string, string>) => {
      try {
        return await runMutation.mutateAsync({ templateId, inputs });
      } catch {
        return null;
      }
    },
    [runMutation.mutateAsync],
  );

  return useMemo(
    () => ({
      listTemplates,
      getTemplate,
      createTemplate,
      saveSessionAsTemplate,
      updateTemplate,
      deleteTemplate,
      runTemplate,
      isLoading:
        createMutation.isPending ||
        saveSessionMutation.isPending ||
        updateMutation.isPending ||
        deleteMutation.isPending ||
        runMutation.isPending,
      error,
    }),
    [
      createMutation.isPending,
      createTemplate,
      deleteMutation.isPending,
      deleteTemplate,
      error,
      getTemplate,
      listTemplates,
      runMutation.isPending,
      runTemplate,
      saveSessionAsTemplate,
      saveSessionMutation.isPending,
      updateMutation.isPending,
      updateTemplate,
    ],
  );
}

export type { CreateTemplateOptions, TemplatePayload };
