/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { useAuth } from "@/lib/auth-context";
import { authenticatedFetch, parseApiError } from "@/lib/api-client";

type Props = {
  name: string;
  exchangePath: string;
  messageType: string;
};

/**
 * Shared popup OAuth callback: exchange code+state, then postMessage to the opener.
 */
export function OauthCallbackPage({ name, exchangePath, messageType }: Props) {
  const hydrated = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
  const { user, isLoading } = useAuth();
  const [exchangeStatus, setExchangeStatus] = useState<"pending" | "success" | "error">("pending");
  const connectingLabel = `Connecting ${name}...`;
  const [exchangeMessage, setExchangeMessage] = useState(connectingLabel);

  const { code, state, oauthError } = useMemo(() => {
    if (!hydrated) {
      return {
        code: null,
        state: null,
        oauthError: null,
      };
    }
    const params = new URLSearchParams(window.location.search);
    return {
      code: params.get("code"),
      state: params.get("state"),
      oauthError: params.get("error"),
    };
  }, [hydrated]);

  const preflight = useMemo(() => {
    if (isLoading) {
      return {
        canExchange: false,
        status: "pending" as const,
        message: connectingLabel,
      };
    }
    if (oauthError) {
      return {
        canExchange: false,
        status: "error" as const,
        message: `${name} refused access: ${oauthError}`,
      };
    }
    if (!code || !state) {
      return {
        canExchange: false,
        status: "error" as const,
        message: "Missing code or state in redirect URL.",
      };
    }
    if (!user) {
      return {
        canExchange: false,
        status: "error" as const,
        message: "Not authenticated. Please log in first.",
      };
    }
    return {
      canExchange: true,
      status: "pending" as const,
      message: connectingLabel,
    };
  }, [code, connectingLabel, isLoading, name, oauthError, state, user]);

  useEffect(() => {
    if (!preflight.canExchange || !code || !state) {
      return;
    }

    authenticatedFetch(exchangePath, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, state }),
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(await parseApiError(response));
        }
        setExchangeStatus("success");
        setExchangeMessage(`${name} connected!`);
        if (window.opener) {
          window.opener.postMessage({ type: messageType, connected: true }, window.location.origin);
          setTimeout(() => window.close(), 1200);
        }
      })
      .catch((err: unknown) => {
        setExchangeStatus("error");
        setExchangeMessage(`Connection failed: ${err instanceof Error ? err.message : "Unknown error"}`);
      });
  }, [code, exchangePath, messageType, name, preflight.canExchange, state]);

  const status = preflight.canExchange ? exchangeStatus : preflight.status;
  const message = preflight.canExchange ? exchangeMessage : preflight.message;

  const color =
    status === "success"
      ? "text-emerald-500"
      : status === "error"
        ? "text-red-400"
        : "text-cyan-400";

  const icon = status === "success" ? "✓" : status === "error" ? "✗" : "⋯";

  return (
    <div className="min-h-screen flex items-center justify-center bg-zinc-950">
      <div className="text-center space-y-4 px-8 max-w-sm">
        <p className="text-3xl font-mono">{icon}</p>
        <p className={`text-sm font-mono font-bold uppercase tracking-widest ${color}`}>
          {message}
        </p>
        {status === "error" && (
          <button
            onClick={() => window.close()}
            className="mt-4 px-4 py-2 text-xs text-zinc-400 border border-zinc-700 rounded-lg hover:border-zinc-500 transition-colors"
          >
            Close
          </button>
        )}
        {status === "pending" && (
          <div className="flex justify-center">
            <div className="h-4 w-4 rounded-full border-2 border-cyan-500 border-t-transparent animate-spin" />
          </div>
        )}
      </div>
    </div>
  );
}
