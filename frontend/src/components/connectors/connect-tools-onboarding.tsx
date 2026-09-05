/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";

import { ConnectToolsModal } from "@/components/connectors/connect-tools-modal";
import { APP_CONNECTORS } from "@/lib/app-paths";
import { useAuth } from "@/lib/auth-context";
import {
  isConnectorConnected,
  isGoogleProvider,
  quickConnectItems,
  resolveConnection,
} from "@/lib/connectors";
import {
  startGithubConnect,
  startGoogleConnect,
  startSlackConnect,
} from "@/lib/connect-oauth";
import {
  useIntegrationsCatalogQuery,
  useIntegrationsConnectionsQuery,
} from "@/lib/queries/integrations";
import { invalidateIntegrations } from "@/lib/queries/invalidate";

const DISMISSED_KEY = "co-connect-tools-dismissed";
export const OPEN_CONNECT_TOOLS_EVENT = "open-connect-tools";

/**
 * Session-scoped dismissal flag. sessionStorage survives a page refresh in
 * the same tab but is cleared when the tab closes — so the modal shows on
 * every fresh app open (until something is connected) but never reappears
 * after a mere refresh once dismissed.
 */
function readDismissed(): boolean {
  if (typeof window === "undefined") return true;
  try {
    return window.sessionStorage.getItem(DISMISSED_KEY) === "1";
  } catch {
    return true;
  }
}

/**
 * First-run "Connect your tools" onboarding modal. Auto-shows on every fresh
 * app open while the signed-in user has no connected integrations. Dismissal
 * lasts for the tab session only. Also re-opens on
 * `window.dispatchEvent(new CustomEvent("open-connect-tools"))`.
 */
export function ConnectToolsOnboarding() {
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const { user, isLoading: authLoading } = useAuth();
  const catalogQuery = useIntegrationsCatalogQuery();
  const connectionsQuery = useIntegrationsConnectionsQuery();

  const [dismissed, setDismissed] = useState(true);
  const [connectingProvider, setConnectingProvider] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setDismissed(readDismissed());
    const reopen = () => {
      setError("");
      setDismissed(false);
    };
    window.addEventListener(OPEN_CONNECT_TOOLS_EVENT, reopen);
    return () => window.removeEventListener(OPEN_CONNECT_TOOLS_EVENT, reopen);
  }, []);

  const connections = useMemo(
    () => connectionsQuery.data ?? [],
    [connectionsQuery.data],
  );
  const catalog = useMemo(() => catalogQuery.data ?? [], [catalogQuery.data]);
  const queriesSettled = !catalogQuery.isLoading && !connectionsQuery.isLoading;

  const hasConnected = useMemo(
    () => connections.some((c) => c.enabled !== false && c.status === "connected"),
    [connections],
  );

  const tiles = useMemo(() => {
    const items = quickConnectItems(catalog);
    return items.map((item) => {
      if (isGoogleProvider(item.provider)) {
        const googleConnected = catalog.some(
          (entry) => isGoogleProvider(entry.provider) && entry.status === "connected",
        )
          || connections.some(
            (c) => isGoogleProvider(c.provider) && c.enabled !== false && c.status === "connected",
          );
        return { item, connected: googleConnected };
      }
      const connection = resolveConnection(item, connections);
      return { item, connected: isConnectorConnected(item, connection, false) };
    });
  }, [catalog, connections]);

  const dismiss = useCallback(() => {
    setDismissed(true);
    try {
      window.sessionStorage.setItem(DISMISSED_KEY, "1");
    } catch {
      // Storage unavailable (private mode) — modal simply shows again next visit.
    }
  }, []);

  const handleBrowseAll = useCallback(() => {
    dismiss();
    router.push(APP_CONNECTORS);
  }, [dismiss, router]);

  const handleConnect = useCallback(
    async (provider: string) => {
      setError("");
      setConnectingProvider(provider);
      try {
        const awaitingGithubFallback = provider === "github";
        const result = isGoogleProvider(provider)
          ? await startGoogleConnect()
          : provider === "github"
            ? await startGithubConnect(() => {
                dismiss();
                router.push(APP_CONNECTORS);
              })
            : await startSlackConnect();
        if (result === "not-configured" && awaitingGithubFallback) return;
        invalidateIntegrations(queryClient);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to start connect flow");
      } finally {
        setConnectingProvider(null);
      }
    },
    [dismiss, queryClient, router],
  );

  const show =
    !dismissed &&
    Boolean(user) &&
    !authLoading &&
    queriesSettled &&
    !hasConnected &&
    pathname !== APP_CONNECTORS &&
    tiles.length > 0;

  return (
    <ConnectToolsModal
      open={show}
      tiles={tiles}
      connectingProvider={connectingProvider}
      error={error}
      onConnect={(provider) => void handleConnect(provider)}
      onBrowseAll={handleBrowseAll}
      onClose={dismiss}
    />
  );
}
