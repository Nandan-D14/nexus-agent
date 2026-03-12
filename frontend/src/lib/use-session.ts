"use client";

import { useCallback, useState } from "react";

import { authenticatedFetch, parseApiError } from "./api-client";
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
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const createSession = useCallback(async (): Promise<SessionData | null> => {
    setIsLoading(true);
    setError(null);

    try {
      const res = await authenticatedFetch("/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      if (!res.ok) {
        throw new Error(await parseApiError(res));
      }

      return (await res.json()) as SessionData;
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Failed to create session";
      setError(msg);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const getSession = useCallback(async (sessionId: string) => {
    setIsLoading(true);
    setError(null);

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
      setError(msg);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const refreshTicket = useCallback(async (sessionId: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const res = await authenticatedFetch(
        `/sessions/${encodeURIComponent(sessionId)}/ticket`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
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
      setError(msg);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const destroySession = useCallback(async (sessionId: string) => {
    setIsLoading(true);
    setError(null);

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
      setError(msg);
      return false;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return {
    createSession,
    getSession,
    refreshTicket,
    destroySession,
    isLoading,
    error,
  };
}
