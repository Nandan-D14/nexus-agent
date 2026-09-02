/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { SessionLandingView } from "@/components/session/session-landing-view";
import { useToast } from "@/components/toast-provider";
import { sessionPath } from "@/lib/app-paths";
import { useAuth } from "@/lib/auth-context";
import type { IntegrationConnection } from "@/lib/connectors";
import { useIntegrationsConnectionsQuery } from "@/lib/queries/integrations";
import { useLandingChrome } from "@/lib/landing-chrome-context";
import { useSession } from "@/lib/use-session";
import { useSettings } from "@/lib/settings-context";
import { withSchedulingConnectors } from "@/lib/scheduling-intent";
import {
  SYSTEM_CONNECTOR,
  normalizePendingTurnInput,
  uploadedFilesForTransport,
  type PendingSessionAction,
  type PendingTurnInput,
  type SessionConnector,
} from "@/lib/session-utils";

function toSessionConnectors(connections: IntegrationConnection[]): SessionConnector[] {
  const usable = connections
    .filter((connection) => connection.enabled && connection.status === "connected")
    .map((connection) => ({
      connection_id: connection.connection_id,
      connector_type: connection.connector_type,
      provider: connection.provider,
      name: connection.name,
      enabled: connection.enabled,
      status: connection.status,
    }));
  return [SYSTEM_CONNECTOR, ...usable];
}

export function SessionStart() {
  const router = useRouter();
  const { toast } = useToast();
  const { user } = useAuth();
  const { createSession } = useSession();
  const { ensureByokReady } = useSettings();
  const { setLandingChrome } = useLandingChrome();
  const connectionsQuery = useIntegrationsConnectionsQuery();

  const [textInput, setTextInput] = useState("");
  const [selectedConnectorIds, setSelectedConnectorIds] = useState<string[]>([]);
  const [selectedToolIds, setSelectedToolIds] = useState<string[]>([]);
  const [pageError, setPageError] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const landingInputRef = useRef<HTMLDivElement | null>(null);
  const createThreadInFlightRef = useRef(false);

  useEffect(() => {
    setLandingChrome(true);
    return () => setLandingChrome(false);
  }, [setLandingChrome]);

  const availableConnectors = useMemo(
    () => toSessionConnectors(connectionsQuery.data ?? []),
    [connectionsQuery.data],
  );

  useEffect(() => {
    setSelectedConnectorIds((prev) =>
      prev.filter((id) => availableConnectors.some((connector) => connector.connection_id === id)),
    );
  }, [availableConnectors]);

  const createThreadFromAction = useCallback(
    async (action: PendingSessionAction): Promise<boolean> => {
      if (createThreadInFlightRef.current) {
        return false;
      }

      let nextAction = action;
      if (action.type === "prompt" || action.type === "demo") {
        const payload = normalizePendingTurnInput(action.payload);
        if (!payload) {
          return false;
        }
        nextAction = {
          ...action,
          payload: {
            ...payload,
            uploadedFiles: uploadedFilesForTransport(payload.uploadedFiles ?? []),
          },
        };
      }

      createThreadInFlightRef.current = true;
      setPageError(null);
      setIsStarting(true);
      let session = null;
      try {
        session = await createSession({ mode: "fresh" });
      } finally {
        createThreadInFlightRef.current = false;
        setIsStarting(false);
      }
      if (!session) {
        setPageError("Failed to create a new thread. Your message was not sent.");
        return false;
      }

      try {
        sessionStorage.setItem(
          `nexus.pendingSessionAction:${session.session_id}`,
          JSON.stringify(nextAction),
        );
      } catch {
        setPageError(
          "This browser blocked session storage, so the thread could not be started. Please retry.",
        );
        return false;
      }

      router.replace(sessionPath(session.session_id));
      return true;
    },
    [createSession, router],
  );

  const requireByok = useCallback(async () => {
    const result = await ensureByokReady();
    if (result.ok) return false;
    toast(result.message, "info");
    return true;
  }, [ensureByokReady, toast]);

  const handleTextSubmit = useCallback(async () => {
    const text = textInput.trim();
    if (!text || !user) return;
    if (await requireByok()) return;

    const payload: PendingTurnInput = {
      text,
      connectorIds: withSchedulingConnectors(
        text,
        selectedConnectorIds,
        selectedToolIds,
        availableConnectors,
      ),
      toolIds: selectedToolIds,
    };
    setTextInput("");
    void createThreadFromAction({ type: "prompt", payload }).then((started) => {
      if (!started) {
        setTextInput(payload.text);
      }
    });
  }, [
    availableConnectors,
    createThreadFromAction,
    requireByok,
    selectedConnectorIds,
    selectedToolIds,
    textInput,
    user,
  ]);

  const handleShowDesktop = useCallback(async () => {
    if (await requireByok()) return;
    void createThreadFromAction({ type: "openDesktop" });
  }, [createThreadFromAction, requireByok]);

  const handleToggleMic = useCallback(async () => {
    if (await requireByok()) return;
    void createThreadFromAction({ type: "startMic" });
  }, [createThreadFromAction, requireByok]);

  const toggleConnectorSelection = useCallback((connectionId: string) => {
    setSelectedConnectorIds((prev) =>
      prev.includes(connectionId)
        ? prev.filter((id) => id !== connectionId)
        : [...prev, connectionId],
    );
  }, []);

  const toggleToolSelection = useCallback((toolId: string) => {
    setSelectedToolIds((prev) =>
      prev.includes(toolId) ? prev.filter((id) => id !== toolId) : [...prev, toolId],
    );
  }, []);

  const toggleAllConnectors = useCallback((ids: string[]) => {
    setSelectedConnectorIds((prev) => {
      if (ids.every((id) => prev.includes(id))) {
        return prev.filter((id) => !ids.includes(id));
      }
      return Array.from(new Set([...prev, ...ids]));
    });
  }, []);

  const toggleAllTools = useCallback((ids: string[]) => {
    setSelectedToolIds((prev) => {
      if (ids.every((id) => prev.includes(id))) {
        return prev.filter((id) => !ids.includes(id));
      }
      return Array.from(new Set([...prev, ...ids]));
    });
  }, []);

  return (
    <SessionLandingView
      onShowDesktop={handleShowDesktop}
      textInput={textInput}
      onChangeText={setTextInput}
      onSubmitText={handleTextSubmit}
      onOpenFilePicker={() => toast("File upload is available in a live session.", "error")}
      uploadDisabled
      uploadedFiles={[]}
      onRemoveFile={() => undefined}
      onToggleMic={handleToggleMic}
      isRecording={false}
      voiceStatus="connected"
      phase="idle"
      isLoading={isStarting}
      isUploadingFile={false}
      onStopAgent={() => undefined}
      availableConnectors={availableConnectors}
      selectedConnectorIds={selectedConnectorIds}
      onToggleConnector={toggleConnectorSelection}
      onToggleAllConnectors={toggleAllConnectors}
      selectedToolIds={selectedToolIds}
      onToggleTool={toggleToolSelection}
      onToggleAllTools={toggleAllTools}
      connectorsLoading={connectionsQuery.isPending}
      onRefreshTools={() => {
        void connectionsQuery.refetch();
      }}
      pageError={pageError}
      error={null}
      landingInputRef={landingInputRef}
    />
  );
}
