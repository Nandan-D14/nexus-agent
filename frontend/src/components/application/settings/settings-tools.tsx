"use client";

import { type FormEvent, useState } from "react";
import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import { Switch } from "@/components/base/switch/switch";
import { APP_CONNECTORS } from "@/lib/app-paths";
import { isGoogleProvider } from "@/lib/connectors";
import {
  useConnectMcpMutation,
  useDeleteIntegrationMutation,
  useIntegrationsConnectionsQuery,
  useToggleIntegrationMutation,
} from "@/lib/queries/integrations";
import { SettingsCard, SettingsRow, SettingsSectionLabel } from "./settings-rows";

export function SettingsTools() {
  const connectionsQuery = useIntegrationsConnectionsQuery();
  const toggleMutation = useToggleIntegrationMutation();
  const deleteMutation = useDeleteIntegrationMutation();
  const connectMcpMutation = useConnectMcpMutation();
  const connections = connectionsQuery.data ?? [];
  const loading = connectionsQuery.isLoading;
  const [error, setError] = useState<string | null>(null);
  const [showMcp, setShowMcp] = useState(false);
  const [mcpName, setMcpName] = useState("");
  const [mcpUrl, setMcpUrl] = useState("");
  const [mcpToken, setMcpToken] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const displayError =
    error ||
    (connectionsQuery.error instanceof Error ? connectionsQuery.error.message : null);

  const toggleConnection = async (connection: (typeof connections)[number]) => {
    if (isGoogleProvider(connection.provider)) return;
    setError(null);
    try {
      await toggleMutation.mutateAsync(connection);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to update tool.");
    }
  };

  const deleteConnection = async (connection: (typeof connections)[number]) => {
    setError(null);
    try {
      await deleteMutation.mutateAsync(connection);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to remove tool.");
    }
  };

  const submitMcp = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await connectMcpMutation.mutateAsync({
        name: mcpName,
        url: mcpUrl,
        bearerToken: mcpToken,
      });
      setShowMcp(false);
      setMcpName("");
      setMcpUrl("");
      setMcpToken("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to add MCP server.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      {displayError ? (
        <div
          role="alert"
          className="rounded-2lg border border-status-rose-text/20 bg-status-rose-background px-3 py-2 text-body-2-regular text-status-rose-text"
        >
          {displayError}
        </div>
      ) : null}

      <div className="flex w-full flex-col gap-2">
        <SettingsSectionLabel>Connected tools</SettingsSectionLabel>
        <SettingsCard>
          {loading ? (
            <div className="py-6 pr-2.5 text-body-2-regular text-text-secondary">Loading…</div>
          ) : connections.length === 0 ? (
            <div className="py-6 pr-2.5 text-body-2-regular text-text-secondary">
              No connectors yet. Add an MCP server below or manage Google accounts from Connectors.
            </div>
          ) : (
            connections.map((connection) => (
              <SettingsRow
                key={connection.connection_id}
                label={connection.name}
                description={
                  connection.last_error
                    ? connection.last_error
                    : `${connection.status} · ${connection.tool_count || connection.tools?.length || 0} tools`
                }
              >
                <div className="flex items-center gap-2">
                  {!isGoogleProvider(connection.provider) ? (
                    <Switch
                      aria-label={`Enable ${connection.name}`}
                      isSelected={connection.enabled}
                      onChange={() => void toggleConnection(connection)}
                    />
                  ) : null}
                  <Button
                    variant="ghost"
                    size="small"
                    onClick={() => void deleteConnection(connection)}
                  >
                    Remove
                  </Button>
                </div>
              </SettingsRow>
            ))
          )}
        </SettingsCard>
      </div>

      <div className="flex items-center gap-2">
        <Button variant="secondary" size="small" onClick={() => setShowMcp((open) => !open)}>
          {showMcp ? "Cancel" : "Add MCP server"}
        </Button>
        <Button
          variant="secondary"
          size="small"
          onClick={() => {
            window.location.assign(APP_CONNECTORS);
          }}
        >
          Open connectors
        </Button>
      </div>

      {showMcp ? (
        <form className="flex w-full flex-col gap-3" onSubmit={(event) => void submitMcp(event)}>
          <Input
            size="small"
            label="Name"
            value={mcpName}
            onChange={setMcpName}
            isRequired
          />
          <Input
            size="small"
            label="URL"
            value={mcpUrl}
            onChange={setMcpUrl}
            isRequired
          />
          <Input
            size="small"
            label="Bearer token (optional)"
            type="password"
            value={mcpToken}
            onChange={setMcpToken}
          />
          <Button type="submit" variant="primary" size="small" className="w-fit" disabled={submitting}>
            {submitting ? "Adding…" : "Add server"}
          </Button>
        </form>
      ) : null}
    </div>
  );
}
