"use client";

import { type FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import { Switch } from "@/components/base/switch/switch";
import { authenticatedFetch, parseApiError } from "@/lib/api-client";
import { SettingsCard, SettingsRow, SettingsSectionLabel } from "./settings-rows";

type IntegrationTool = {
  name: string;
};

type IntegrationConnection = {
  connection_id: string;
  connector_type: string;
  provider: string;
  name: string;
  enabled: boolean;
  status: string;
  tools: IntegrationTool[];
  tool_count: number;
  last_error?: string | null;
};

function isGoogleProvider(provider: string) {
  return ["google_drive", "gmail", "google_calendar", "google_tasks"].includes(provider);
}

export function SettingsTools() {
  const [connections, setConnections] = useState<IntegrationConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showMcp, setShowMcp] = useState(false);
  const [mcpName, setMcpName] = useState("");
  const [mcpUrl, setMcpUrl] = useState("");
  const [mcpToken, setMcpToken] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await authenticatedFetch("/api/v1/integrations/connections");
      if (!response.ok) throw new Error(await parseApiError(response));
      const body = (await response.json()) as { connections?: IntegrationConnection[] };
      setConnections(body.connections ?? []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load tools.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const toggleConnection = async (connection: IntegrationConnection) => {
    if (isGoogleProvider(connection.provider)) return;
    setError(null);
    const response = await authenticatedFetch(`/api/v1/integrations/${connection.connection_id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !connection.enabled }),
    });
    if (!response.ok) {
      setError(await parseApiError(response));
      return;
    }
    await load();
  };

  const deleteConnection = async (connection: IntegrationConnection) => {
    setError(null);
    const path = isGoogleProvider(connection.provider)
      ? "/api/v1/auth/google"
      : `/api/v1/integrations/${connection.connection_id}`;
    const response = await authenticatedFetch(path, { method: "DELETE" });
    if (!response.ok) {
      setError(await parseApiError(response));
      return;
    }
    await load();
  };

  const submitMcp = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const response = await authenticatedFetch("/api/v1/integrations/mcp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: mcpName,
          url: mcpUrl,
          bearer_token: mcpToken || null,
          enabled: true,
        }),
      });
      if (!response.ok) throw new Error(await parseApiError(response));
      setShowMcp(false);
      setMcpName("");
      setMcpUrl("");
      setMcpToken("");
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to add MCP server.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      {error ? (
        <div
          role="alert"
          className="rounded-2lg border border-status-rose-text/20 bg-status-rose-background px-3 py-2 text-body-2-regular text-status-rose-text"
        >
          {error}
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
            window.location.assign("/connectors");
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
