"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";

import { useToast } from "@/components/toast-provider";

import { authenticatedFetch, parseApiError, readApiError } from "./api-client";
import type {
  WorkflowTemplateData,
  WorkflowTemplateInputField,
  WorkflowTemplateRunResult,
} from "./message-types";

type TemplatePayload = {
  name?: string;
  description?: string;
  instructions?: string;
  inputFields?: WorkflowTemplateInputField[];
};

type CreateTemplateOptions = TemplatePayload & {
  sourceSessionId: string;
};

export interface UseWorkflowTemplatesReturn {
  listTemplates: (query?: string) => Promise<WorkflowTemplateData[]>;
  getTemplate: (templateId: string) => Promise<WorkflowTemplateData | null>;
  createTemplate: (options: CreateTemplateOptions) => Promise<WorkflowTemplateData | null>;
  saveSessionAsTemplate: (sessionId: string, payload?: TemplatePayload) => Promise<WorkflowTemplateData | null>;
  updateTemplate: (templateId: string, payload: TemplatePayload) => Promise<WorkflowTemplateData | null>;
  deleteTemplate: (templateId: string) => Promise<boolean>;
  runTemplate: (templateId: string, inputs: Record<string, string>) => Promise<WorkflowTemplateRunResult | null>;
  isLoading: boolean;
  error: string | null;
}

function buildTemplateBody(payload?: TemplatePayload) {
  return {
    name: payload?.name ?? null,
    description: payload?.description ?? null,
    instructions: payload?.instructions ?? null,
    input_fields: payload?.inputFields ?? [],
  };
}

export function useWorkflowTemplates(): UseWorkflowTemplatesReturn {
  const router = useRouter();
  const { toast } = useToast();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleTemplateError = useCallback(async (response: Response) => {
    const apiError = await readApiError(response);
    if (apiError.code === "BYOK_REQUIRED") {
      toast(apiError.message, "error");
      router.push("/settings/api?setup=1");
      return apiError.message;
    }
    return apiError.message;
  }, [router, toast]);

  const listTemplates = useCallback(async (query?: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const path = query?.trim()
        ? `/api/v1/templates?q=${encodeURIComponent(query.trim())}`
        : "/api/v1/templates";
      const res = await authenticatedFetch(path);
      if (!res.ok) {
        throw new Error(await parseApiError(res));
      }
      const body = (await res.json()) as { templates: WorkflowTemplateData[] };
      return body.templates ?? [];
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load templates";
      setError(message);
      return [];
    } finally {
      setIsLoading(false);
    }
  }, []);

  const getTemplate = useCallback(async (templateId: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await authenticatedFetch(`/api/v1/templates/${encodeURIComponent(templateId)}`);
      if (!res.ok) {
        throw new Error(await parseApiError(res));
      }
      return (await res.json()) as WorkflowTemplateData;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load template";
      setError(message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const createTemplate = useCallback(async (options: CreateTemplateOptions) => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await authenticatedFetch("/api/v1/templates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_session_id: options.sourceSessionId,
          ...buildTemplateBody(options),
        }),
      });
      if (!res.ok) {
        throw new Error(await handleTemplateError(res));
      }
      return (await res.json()) as WorkflowTemplateData;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to create template";
      setError(message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [handleTemplateError]);

  const saveSessionAsTemplate = useCallback(async (sessionId: string, payload?: TemplatePayload) => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await authenticatedFetch(
        `/api/v1/sessions/${encodeURIComponent(sessionId)}/template`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(buildTemplateBody(payload)),
        },
      );
      if (!res.ok) {
        throw new Error(await handleTemplateError(res));
      }
      return (await res.json()) as WorkflowTemplateData;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to save session as template";
      setError(message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [handleTemplateError]);

  const updateTemplate = useCallback(async (templateId: string, payload: TemplatePayload) => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await authenticatedFetch(
        `/api/v1/templates/${encodeURIComponent(templateId)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: payload.name ?? null,
            description: payload.description ?? null,
            instructions: payload.instructions ?? null,
            input_fields: payload.inputFields ?? null,
          }),
        },
      );
      if (!res.ok) {
        throw new Error(await handleTemplateError(res));
      }
      return (await res.json()) as WorkflowTemplateData;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to update template";
      setError(message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [handleTemplateError]);

  const deleteTemplate = useCallback(async (templateId: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await authenticatedFetch(`/api/v1/templates/${encodeURIComponent(templateId)}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        throw new Error(await parseApiError(res));
      }
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to delete template";
      setError(message);
      return false;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const runTemplate = useCallback(async (templateId: string, inputs: Record<string, string>) => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await authenticatedFetch(
        `/api/v1/templates/${encodeURIComponent(templateId)}/run`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ inputs }),
        },
      );
      if (!res.ok) {
        throw new Error(await handleTemplateError(res));
      }
      return (await res.json()) as WorkflowTemplateRunResult;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to run template";
      setError(message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [handleTemplateError]);

  return {
    listTemplates,
    getTemplate,
    createTemplate,
    saveSessionAsTemplate,
    updateTemplate,
    deleteTemplate,
    runTemplate,
    isLoading,
    error,
  };
}
