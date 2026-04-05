"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";

import { useToast } from "@/components/toast-provider";

import { authenticatedFetch, parseApiError, readApiError } from "./api-client";
import { isBetaBlockedCode } from "./beta-access";
import type {
  ArchivedMessage,
  HistoryReuseMode,
  RunArtifact,
  RunInfo,
  RunStep,
  SessionCreateMode,
  SessionData,
  SessionInfo,
  WorkspaceResumeState,
} from "./message-types";

type CreateSessionOptions = {
  mode?: SessionCreateMode;
  sourceSessionId?: string;
};

export interface UseSessionReturn {
  createSession: (options?: CreateSessionOptions) => Promise<SessionData | null>;
  continueSession: (sessionId: string) => Promise<SessionData | null>;
  getSession: (sessionId: string) => Promise<SessionInfo | null>;
  getSessionMessages: (sessionId: string) => Promise<ArchivedMessage[]>;
  getSessionRun: (sessionId: string) => Promise<RunInfo | null>;
  getSessionRunSteps: (sessionId: string) => Promise<RunStep[]>;
  getSessionArtifacts: (sessionId: string) => Promise<RunArtifact[]>;
  getResumeWorkspace: () => Promise<WorkspaceResumeState | null>;
  reuseHistorySession: (sessionId: string, mode: HistoryReuseMode) => Promise<SessionData | null>;
  refreshTicket: (sessionId: string) => Promise<string | null>;
  destroySession: (sessionId: string) => Promise<boolean>;
  isLoading: boolean;
  error: string | null;
}

export function useSession(): UseSessionReturn {
  const router = useRouter();
  const { toast } = useToast();
  const [isCreating, setIsCreating] = useState(false);
  const [isGetting, setIsGetting] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isDestroying, setIsDestroying] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [getError, setGetError] = useState<string | null>(null);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const [reuseError, setReuseError] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [destroyError, setDestroyError] = useState<string | null>(null);

  const getSessionRun = useCallback(async (sessionId: string) => {
    setIsGetting(true);
    setGetError(null);

    try {
      const res = await authenticatedFetch(
        `/api/v1/sessions/${encodeURIComponent(sessionId)}/run`,
      );
      if (!res.ok) {
        throw new Error(await parseApiError(res));
      }
      const body = (await res.json()) as { run: RunInfo | null };
      return body.run;
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Failed to load session run";
      setGetError(msg);
      return null;
    } finally {
      setIsGetting(false);
    }
  }, []);

  const getSessionRunSteps = useCallback(async (sessionId: string) => {
    setIsGetting(true);
    setGetError(null);

    try {
      const res = await authenticatedFetch(
        `/api/v1/sessions/${encodeURIComponent(sessionId)}/run/steps`,
      );
      if (!res.ok) {
        throw new Error(await parseApiError(res));
      }
      const body = (await res.json()) as { steps: RunStep[] };
      return body.steps;
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Failed to load run steps";
      setGetError(msg);
      return [];
    } finally {
      setIsGetting(false);
    }
  }, []);

  const getSessionArtifacts = useCallback(async (sessionId: string) => {
    setIsGetting(true);
    setGetError(null);

    try {
      const res = await authenticatedFetch(
        `/api/v1/sessions/${encodeURIComponent(sessionId)}/artifacts`,
      );
      if (!res.ok) {
        throw new Error(await parseApiError(res));
      }
      const body = (await res.json()) as { artifacts: RunArtifact[] };
      return body.artifacts;
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Failed to load session artifacts";
      setGetError(msg);
      return [];
    } finally {
      setIsGetting(false);
    }
  }, []);

  const createSession = useCallback(async (options?: CreateSessionOptions): Promise<SessionData | null> => {
    setIsCreating(true);
    setCreateError(null);

    try {
      const res = await authenticatedFetch("/sessions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          mode: options?.mode ?? "fresh",
          source_session_id: options?.sourceSessionId ?? null,
        }),
      });

      if (!res.ok) {
        const apiError = await readApiError(res);
        if (isBetaBlockedCode(apiError.code)) {
          setCreateError(apiError.message);
          toast(apiError.message, "error");
          router.push("/beta");
          return null;
        }
        if (apiError.code === "BYOK_REQUIRED") {
          setCreateError(apiError.message);
          toast(apiError.message, "error");
          router.push("/settings/api?setup=1");
          return null;
        }
        throw new Error(apiError.message);
      }

      return (await res.json()) as SessionData;
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Failed to create session";
      setCreateError(msg);
      return null;
    } finally {
      setIsCreating(false);
    }
  }, [router, toast]);

  const continueSession = useCallback(async (sessionId: string): Promise<SessionData | null> => {
    setIsCreating(true);
    setCreateError(null);

    try {
      const res = await authenticatedFetch(
        `/sessions/${encodeURIComponent(sessionId)}/continue`,
        {
          method: "POST",
        },
      );

      if (!res.ok) {
        const apiError = await readApiError(res);
        if (isBetaBlockedCode(apiError.code)) {
          setCreateError(apiError.message);
          toast(apiError.message, "error");
          router.push("/beta");
          return null;
        }
        if (apiError.code === "BYOK_REQUIRED") {
          setCreateError(apiError.message);
          toast(apiError.message, "error");
          router.push("/settings/api?setup=1");
          return null;
        }
        throw new Error(apiError.message);
      }

      return (await res.json()) as SessionData;
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Failed to continue session";
      setCreateError(msg);
      return null;
    } finally {
      setIsCreating(false);
    }
  }, [router, toast]);

  const getSession = useCallback(async (sessionId: string) => {
    setIsGetting(true);
    setGetError(null);

    try {
      const res = await authenticatedFetch(
        `/sessions/${encodeURIComponent(sessionId)}`,
      );

      if (!res.ok) {
        throw new Error(await parseApiError(res));
      }

      return (await res.json()) as SessionInfo;
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Failed to load session";
      setGetError(msg);
      return null;
    } finally {
      setIsGetting(false);
    }
  }, []);

  const getSessionMessages = useCallback(async (sessionId: string) => {
    setIsGetting(true);
    setGetError(null);

    try {
      const res = await authenticatedFetch(
        `/api/v1/history/${encodeURIComponent(sessionId)}/messages`,
      );

      if (!res.ok) {
        throw new Error(await parseApiError(res));
      }

      const body = (await res.json()) as {
        messages: Array<{
          id: string;
          role: "user" | "agent";
          source?: string;
          text: string;
          createdAt?: string | null;
          turnIndex?: number;
        }>;
      };

      return (body.messages || []).map((message) => {
        const role: ArchivedMessage["role"] =
          message.role === "user" ? "user" : "agent";
        return {
          id: message.id,
          role,
          source: message.source,
          text: typeof message.text === "string" ? message.text : "",
          turn_index: typeof message.turnIndex === "number" ? message.turnIndex : 0,
          created_at:
            typeof message.createdAt === "string" ? message.createdAt : null,
        };
      });
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Failed to load session messages";
      setGetError(msg);
      return [];
    } finally {
      setIsGetting(false);
    }
  }, []);

  const getResumeWorkspace = useCallback(async () => {
    setIsGetting(true);
    setResumeError(null);

    try {
      const res = await authenticatedFetch("/api/v1/workspace/resume");
      if (!res.ok) {
        throw new Error(await parseApiError(res));
      }
      return (await res.json()) as WorkspaceResumeState;
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Failed to load workspace state";
      setResumeError(msg);
      return null;
    } finally {
      setIsGetting(false);
    }
  }, []);

  const reuseHistorySession = useCallback(async (sessionId: string, mode: HistoryReuseMode) => {
    setIsCreating(true);
    setReuseError(null);

    try {
      const endpoint =
        mode === "continue"
          ? `/sessions/${encodeURIComponent(sessionId)}/continue`
          : `/api/v1/history/${encodeURIComponent(sessionId)}/reuse`;
      const res = await authenticatedFetch(endpoint, {
        method: "POST",
        headers:
          mode === "continue"
            ? undefined
            : {
                "Content-Type": "application/json",
              },
        body: mode === "continue" ? undefined : JSON.stringify({ mode }),
      });

      if (!res.ok) {
        const apiError = await readApiError(res);
        if (isBetaBlockedCode(apiError.code)) {
          setReuseError(apiError.message);
          toast(apiError.message, "error");
          router.push("/beta");
          return null;
        }
        if (apiError.code === "BYOK_REQUIRED") {
          setReuseError(apiError.message);
          toast(apiError.message, "error");
          router.push("/settings/api?setup=1");
          return null;
        }
        throw new Error(apiError.message);
      }

      return (await res.json()) as SessionData;
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Failed to reuse history session";
      setReuseError(msg);
      return null;
    } finally {
      setIsCreating(false);
    }
  }, [router, toast]);

  const refreshTicket = useCallback(async (sessionId: string) => {
    setIsRefreshing(true);
    setRefreshError(null);

    try {
      const res = await authenticatedFetch(
        `/sessions/${encodeURIComponent(sessionId)}/ticket`,
        {
          method: "POST",
        },
      );

      if (!res.ok) {
        const apiError = await readApiError(res);
        if (isBetaBlockedCode(apiError.code)) {
          setRefreshError(apiError.message);
          toast(apiError.message, "error");
          router.push("/beta");
          return null;
        }
        if (apiError.code === "BYOK_REQUIRED") {
          setRefreshError(apiError.message);
          toast(apiError.message, "error");
          router.push("/settings/api?setup=1");
          return null;
        }
        throw new Error(apiError.message);
      }

      const body = (await res.json()) as { ws_ticket: string };
      return body.ws_ticket;
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Failed to refresh session ticket";
      setRefreshError(msg);
      return null;
    } finally {
      setIsRefreshing(false);
    }
  }, [router, toast]);

  const destroySession = useCallback(async (sessionId: string) => {
    setIsDestroying(true);
    setDestroyError(null);

    try {
      const res = await authenticatedFetch(
        `/sessions/${encodeURIComponent(sessionId)}`,
        {
          method: "DELETE",
        },
      );

      if (!res.ok) {
        throw new Error(await parseApiError(res));
      }

      return true;
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Failed to destroy session";
      setDestroyError(msg);
      return false;
    } finally {
      setIsDestroying(false);
    }
  }, []);

  return {
    createSession,
    continueSession,
    getSession,
    getSessionMessages,
    getSessionRun,
    getSessionRunSteps,
    getSessionArtifacts,
    getResumeWorkspace,
    reuseHistorySession,
    refreshTicket,
    destroySession,
    isLoading: isCreating || isGetting || isRefreshing || isDestroying,
    error: createError ?? getError ?? resumeError ?? reuseError ?? refreshError ?? destroyError,
  };
}
