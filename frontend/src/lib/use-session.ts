/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";

import { useToast } from "@/components/toast-provider";
import { useSettings } from "./settings-context";

import { authenticatedFetch, parseApiError, readApiError } from "./api-client";
import { invalidateSessionLists } from "./queries/invalidate";
import type {
  ArchivedMessage,
  HistoryReuseMode,
  RecentSession,
  RunArtifact,
  RunInfo,
  RunStep,
  SessionCreateMode,
  SessionData,
  SessionInfo,
  WorkspaceResumeState,
} from "./message-types";
import type { DurableReplayEvent } from "./use-websocket";

type CreateSessionOptions = {
  mode?: SessionCreateMode;
  sourceSessionId?: string;
};

export type DurableTaskEventsPage = {
  events: DurableReplayEvent[];
  last_seq: number;
  has_more: boolean;
};

export type DurableTaskEventsResult = {
  events: DurableReplayEvent[];
  last_seq: number;
};

const DURABLE_EVENTS_PAGE_LIMIT = 200;
const DURABLE_EVENTS_MAX_PAGES = 50;

export interface UseSessionReturn {
  createSession: (options?: CreateSessionOptions) => Promise<SessionData | null>;
  continueSession: (sessionId: string) => Promise<SessionData | null>;
  getSession: (sessionId: string) => Promise<SessionInfo | null>;
  getSessionMessages: (sessionId: string) => Promise<ArchivedMessage[]>;
  getSessionRun: (sessionId: string) => Promise<RunInfo | null>;
  getSessionRunSteps: (sessionId: string) => Promise<RunStep[]>;
  getSessionArtifacts: (sessionId: string) => Promise<RunArtifact[]>;
  /** Fetch one page of durable task events. */
  getDurableTaskEvents: (
    taskId: string,
    options?: { afterSeq?: number; limit?: number },
  ) => Promise<DurableTaskEventsPage | null>;
  /** Paginate durable task events from after_seq=0 until exhausted. */
  listDurableTaskEvents: (taskId: string) => Promise<DurableTaskEventsResult | null>;
  getResumeWorkspace: () => Promise<WorkspaceResumeState | null>;
  listSessions: (limit?: number) => Promise<RecentSession[]>;
  reuseHistorySession: (sessionId: string, mode: HistoryReuseMode) => Promise<SessionData | null>;
  refreshTicket: (sessionId: string) => Promise<string | null>;
  destroySession: (sessionId: string) => Promise<boolean>;
  isLoading: boolean;
  error: string | null;
}

export function useSession(): UseSessionReturn {
  const { toast } = useToast();
  const { openSettings } = useSettings();
  const queryClient = useQueryClient();
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

  const getDurableTaskEvents = useCallback(
    async (
      taskId: string,
      options?: { afterSeq?: number; limit?: number },
    ): Promise<DurableTaskEventsPage | null> => {
      if (!taskId.startsWith("task_")) {
        return null;
      }
      const afterSeq = options?.afterSeq ?? 0;
      const limit = options?.limit ?? DURABLE_EVENTS_PAGE_LIMIT;
      try {
        const res = await authenticatedFetch(
          `/api/v1/tasks/${encodeURIComponent(taskId)}/events?after_seq=${afterSeq}&limit=${limit}`,
        );
        if (!res.ok) {
          // Soft-fail: caller falls back to full history mapping.
          console.warn(
            "[useSession] Durable task events unavailable:",
            await parseApiError(res).catch(() => res.statusText),
          );
          return null;
        }
        const body = (await res.json().catch(() => null)) as {
          events?: DurableReplayEvent[];
          last_seq?: number;
          has_more?: boolean;
        } | null;
        const events = Array.isArray(body?.events) ? body.events : [];
        const last_seq =
          typeof body?.last_seq === "number" && Number.isFinite(body.last_seq)
            ? body.last_seq
            : afterSeq;
        const has_more =
          typeof body?.has_more === "boolean"
            ? body.has_more
            : events.length >= limit;
        return { events, last_seq, has_more };
      } catch (err) {
        console.warn("[useSession] Durable task events fetch failed:", err);
        return null;
      }
    },
    [],
  );

  const listDurableTaskEvents = useCallback(
    async (taskId: string): Promise<DurableTaskEventsResult | null> => {
      if (!taskId.startsWith("task_")) {
        return null;
      }
      const allEvents: DurableReplayEvent[] = [];
      let afterSeq = 0;
      let lastSeq = 0;

      for (let page = 0; page < DURABLE_EVENTS_MAX_PAGES; page += 1) {
        const result = await getDurableTaskEvents(taskId, {
          afterSeq,
          limit: DURABLE_EVENTS_PAGE_LIMIT,
        });
        if (!result) {
          return allEvents.length > 0 ? { events: allEvents, last_seq: lastSeq } : null;
        }
        allEvents.push(...result.events);
        lastSeq = Math.max(lastSeq, result.last_seq);
        if (!result.has_more || result.events.length === 0) {
          return { events: allEvents, last_seq: lastSeq };
        }
        afterSeq = result.last_seq;
      }

      return { events: allEvents, last_seq: lastSeq };
    },
    [getDurableTaskEvents],
  );

  const listSessions = useCallback(async (limit: number = 20) => {
    setIsGetting(true);
    setGetError(null);

    try {
      const res = await authenticatedFetch(
        `/api/v1/dashboard/sessions?limit=${limit}`,
      );
      if (!res.ok) {
        throw new Error(await parseApiError(res));
      }
      const body = (await res.json()) as { sessions: RecentSession[] };
      return body.sessions || [];
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Failed to load session list";
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
        if (apiError.code === "BYOK_REQUIRED") {
          setCreateError(apiError.message);
          toast(apiError.message, "error");
          openSettings("api");
          return null;
        }
        throw new Error(apiError.message);
      }

      const session = (await res.json()) as SessionData;
      invalidateSessionLists(queryClient);
      return session;
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Failed to create session";
      setCreateError(msg);
      return null;
    } finally {
      setIsCreating(false);
    }
  }, [openSettings, queryClient, toast]);

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
        if (apiError.code === "BYOK_REQUIRED") {
          setCreateError(apiError.message);
          toast(apiError.message, "error");
          openSettings("api");
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
  }, [openSettings, toast]);

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
          role: "user" | "agent" | "tool_call" | "tool_result" | "thinking" | "agent_thinking";
          source?: string;
          text: string;
          createdAt?: string | null;
          turnIndex?: number;
        }>;
      };

      return (body.messages || []).map((message) => {
        return {
          id: message.id,
          role: message.role,
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
        if (apiError.code === "BYOK_REQUIRED") {
          toast(apiError.message, "error");
          openSettings("api");
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
  }, [openSettings, toast]);

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
        if (apiError.code === "BYOK_REQUIRED") {
          setRefreshError(apiError.message);
          toast(apiError.message, "error");
          openSettings("api");
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
  }, [openSettings, toast]);

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

      invalidateSessionLists(queryClient);
      return true;
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Failed to destroy session";
      setDestroyError(msg);
      return false;
    } finally {
      setIsDestroying(false);
    }
  }, [queryClient]);

  const result = {
    createSession,
    continueSession,
    getSession,
    getSessionMessages,
    getSessionRun,
    getSessionRunSteps,
    getSessionArtifacts,
    getDurableTaskEvents,
    listDurableTaskEvents,
    getResumeWorkspace,
    listSessions,
    reuseHistorySession,
    refreshTicket,
    destroySession,
    isLoading: isCreating || isGetting || isRefreshing || isDestroying,
    error: createError ?? getError ?? resumeError ?? reuseError ?? refreshError ?? destroyError,
  };
  return result;
}
