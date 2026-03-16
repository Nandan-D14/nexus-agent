"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";

import { useToast } from "@/components/toast-provider";

import { authenticatedFetch, parseApiError, readApiError } from "./api-client";
import type { SessionData, SessionInfo } from "./message-types";

export interface UseSessionReturn {
  createSession: () => Promise<SessionData | null>;
  getSession: (sessionId: string) => Promise<SessionInfo | null>;
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
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [destroyError, setDestroyError] = useState<string | null>(null);

  const createSession = useCallback(async (): Promise<SessionData | null> => {
    setIsCreating(true);
    setCreateError(null);

    try {
      const res = await authenticatedFetch("/sessions", {
        method: "POST",
      });

      if (!res.ok) {
        const apiError = await readApiError(res);
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
        throw new Error(await parseApiError(res));
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
  }, []);

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
    getSession,
    refreshTicket,
    destroySession,
    isLoading: isCreating || isGetting || isRefreshing || isDestroying,
    error: createError ?? getError ?? refreshError ?? destroyError,
  };
}
