"use client";

import { type FormEvent, type ReactNode, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Cable,
  CheckCircle2,
  Cloud,
  Database,
  Github,
  Loader2,
  Plus,
  RefreshCw,
  Shield,
  Trash2,
} from "lucide-react";
import { motion } from "framer-motion";

import { authenticatedFetch, parseApiError } from "@/lib/api-client";

type IntegrationTool = {
  name: string;
  description?: string;
  input_schema?: Record<string, unknown>;
};

type IntegrationConnection = {
  connection_id: string;
  connector_type: string;
  provider: string;
  name: string;
  enabled: boolean;
  status: string;
  tools: IntegrationTool[];
  resources: Record<string, unknown>[];
  tool_count: number;
  last_checked_at?: string | null;
  last_error?: string | null;
};

type CatalogItem = {
  provider: string;
  connector_type: string;
  name: string;
  description: string;
  status: string;
};

function statusClasses(status: string) {
  switch (status) {
    case "connected":
      return "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400";
    case "error":
      return "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400";
    case "disabled":
      return "border-zinc-300 bg-zinc-100 text-zinc-500 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-400";
    default:
      return "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400";
  }
}

function providerIcon(provider: string) {
  if (provider === "github") return Github;
  if (provider === "google_drive") return Cloud;
  if (provider === "mcp") return Cable;
  return Database;
}

export default function ConnectorsPage() {
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [connections, setConnections] = useState<IntegrationConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showMcp, setShowMcp] = useState(false);
  const [showGithub, setShowGithub] = useState(false);
  const [mcpName, setMcpName] = useState("");
  const [mcpUrl, setMcpUrl] = useState("");
  const [mcpToken, setMcpToken] = useState("");
  const [githubToken, setGithubToken] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const connectionByProvider = useMemo(() => {
    const map = new Map<string, IntegrationConnection>();
    for (const connection of connections) {
      if (connection.provider !== "mcp") map.set(connection.provider, connection);
    }
    return map;
  }, [connections]);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [catalogResponse, connectionsResponse] = await Promise.all([
        authenticatedFetch("/v1/integrations/catalog"),
        authenticatedFetch("/v1/integrations/connections"),
      ]);
      if (!catalogResponse.ok) throw new Error(await parseApiError(catalogResponse));
      if (!connectionsResponse.ok) throw new Error(await parseApiError(connectionsResponse));
      
      const catalogBody = await catalogResponse.json();
      const connectionsBody = await connectionsResponse.json();
      
      const loadedCatalog = catalogBody.catalog ?? [];
      const loadedConnections = connectionsBody.connections ?? [];
      
      const driveCat = loadedCatalog.find((c: any) => c.provider === "google_drive");
      if (
        driveCat
        && driveCat.status === "connected"
        && !loadedConnections.some((connection: IntegrationConnection) => connection.provider === "google_drive")
      ) {
        loadedConnections.push({
          connection_id: "google_drive",
          connector_type: "native",
          provider: "google_drive",
          name: "Google Drive",
          enabled: true,
          status: "connected",
          tools: [],
          resources: [],
          tool_count: 0,
        });
      }

      setCatalog(loadedCatalog);
      setConnections(loadedConnections);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load integrations");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function startGoogleDriveConnect() {
    setError("");
    try {
      const response = await authenticatedFetch("/v1/auth/google-drive/url");
      if (!response.ok) throw new Error(await parseApiError(response));
      const body = await response.json();

      let popupClosedPoll: number | null = null;
      const handleMessage = (event: MessageEvent) => {
        if (event.origin !== window.location.origin) return;
        if (event.data?.type !== "google_drive_connected") return;

        window.removeEventListener("message", handleMessage);
        if (popupClosedPoll !== null) {
          window.clearInterval(popupClosedPoll);
        }

        setCatalog((current) =>
          current.map((item) =>
            item.provider === "google_drive"
              ? { ...item, status: "connected" }
              : item,
          ),
        );
        setConnections((current) => {
          const hasGoogleDrive = current.some((connection) => connection.provider === "google_drive");
          if (hasGoogleDrive) {
            return current.map((connection) =>
              connection.provider === "google_drive"
                ? { ...connection, enabled: true, status: "connected" }
                : connection,
            );
          }
          return [
            ...current,
            {
              connection_id: "google_drive",
              connector_type: "native",
              provider: "google_drive",
              name: "Google Drive",
              enabled: true,
              status: "connected",
              tools: [],
              resources: [],
              tool_count: 0,
            },
          ];
        });
        void load();
      };

      window.addEventListener("message", handleMessage);
      
      const width = 600;
      const height = 700;
      const left = window.screen.width / 2 - width / 2;
      const top = window.screen.height / 2 - height / 2;
      
      const popup = window.open(
        body.auth_url,
        "GoogleDriveAuth",
        `width=${width},height=${height},top=${top},left=${left},scrollbars=yes`
      );

      if (!popup) {
        window.removeEventListener("message", handleMessage);
        window.location.href = body.auth_url;
        return;
      }

      popupClosedPoll = window.setInterval(() => {
        if (popup.closed) {
          window.clearInterval(popupClosedPoll as number);
          popupClosedPoll = null;
          window.removeEventListener("message", handleMessage);
          void load();
        }
      }, 500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start Google Drive OAuth");
    }
  }

  async function submitMcp(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const response = await authenticatedFetch("/v1/integrations/mcp", {
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
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add MCP server");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitGithub(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const response = await authenticatedFetch("/v1/integrations/github", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: githubToken, enabled: true }),
      });
      if (!response.ok) throw new Error(await parseApiError(response));
      setShowGithub(false);
      setGithubToken("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to connect GitHub");
    } finally {
      setSubmitting(false);
    }
  }

  async function toggleConnection(connection: IntegrationConnection) {
    if (connection.provider === "google_drive") return;

    setError("");
    const response = await authenticatedFetch(`/v1/integrations/${connection.connection_id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !connection.enabled }),
    });
    if (!response.ok) {
      setError(await parseApiError(response));
      return;
    }
    await load();
  }

  async function testMcp(connection: IntegrationConnection) {
    setError("");
    const response = await authenticatedFetch(`/v1/integrations/mcp/${connection.connection_id}/test`, {
      method: "POST",
    });
    if (!response.ok) {
      setError(await parseApiError(response));
      return;
    }
    await load();
  }

  async function deleteConnection(connection: IntegrationConnection) {
    setError("");

    if (connection.provider === "google_drive") {
      const response = await authenticatedFetch("/v1/auth/google-drive", {
        method: "DELETE",
      });
      if (!response.ok) {
        setError(await parseApiError(response));
        return;
      }
      await load();
      return;
    }

    const response = await authenticatedFetch(`/v1/integrations/${connection.connection_id}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      setError(await parseApiError(response));
      return;
    }
    await load();
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-4 pb-20 md:p-8">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="space-y-2">
          <div className="inline-flex items-center gap-2 rounded-full border border-blue-500/20 bg-blue-500/10 px-3 py-1 text-xs font-bold uppercase tracking-widest text-blue-500">
            <Shield className="h-3.5 w-3.5" />
            Enterprise Tool Layer
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-zinc-950 dark:text-zinc-100">
            Connectors
          </h1>
          <p className="max-w-2xl text-sm text-zinc-500">
            Connect private tools, remote MCP servers, and native SaaS systems so the cloud computer can act with visible progress and scoped credentials.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setShowMcp(true)}
            className="inline-flex items-center gap-2 rounded-lg bg-zinc-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-zinc-800 dark:bg-white dark:text-zinc-950 dark:hover:bg-zinc-200"
          >
            <Plus className="h-4 w-4" />
            Add MCP Server
          </button>
          <button
            onClick={() => void load()}
            className="inline-flex items-center gap-2 rounded-lg border border-zinc-200 px-4 py-2 text-sm font-semibold text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-800 dark:text-zinc-200 dark:hover:bg-white/5"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </div>
      </div>

      {error ? (
        <div className="flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-300">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          {error}
        </div>
      ) : null}

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {catalog.map((item, index) => {
          const Icon = providerIcon(item.provider);
          const connection = connectionByProvider.get(item.provider);
          const status = connection?.enabled === false ? "disabled" : connection?.status || item.status;
          return (
            <motion.div
              key={`${item.provider}-${item.connector_type}`}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.03 }}
              className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-[#1a1a1c]"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-zinc-100 dark:bg-zinc-900">
                    <Icon className="h-5 w-5 text-zinc-700 dark:text-zinc-200" />
                  </div>
                  <div>
                    <h2 className="font-semibold text-zinc-950 dark:text-white">{item.name}</h2>
                    <p className="text-xs uppercase tracking-widest text-zinc-400">{item.connector_type}</p>
                  </div>
                </div>
                <span className={`rounded-full border px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider ${statusClasses(status)}`}>
                  {status.replace("_", " ")}
                </span>
              </div>
              <p className="mt-4 min-h-10 text-sm leading-6 text-zinc-500">{item.description}</p>
              <div className="mt-5 flex gap-2">
                {item.provider === "google_drive" ? (
                  <button onClick={startGoogleDriveConnect} className="rounded-lg border border-zinc-200 px-3 py-2 text-sm font-semibold dark:border-zinc-800">
                    {status === "connected" ? "Reconnect" : "Connect"}
                  </button>
                ) : item.provider === "github" ? (
                  <button onClick={() => setShowGithub(true)} className="rounded-lg border border-zinc-200 px-3 py-2 text-sm font-semibold dark:border-zinc-800">
                    {connection ? "Update token" : "Connect"}
                  </button>
                ) : item.provider === "mcp" ? (
                  <button onClick={() => setShowMcp(true)} className="rounded-lg border border-zinc-200 px-3 py-2 text-sm font-semibold dark:border-zinc-800">
                    Add server
                  </button>
                ) : null}
              </div>
            </motion.div>
          );
        })}
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-zinc-950 dark:text-white">Active Connections</h2>
          {loading ? <Loader2 className="h-4 w-4 animate-spin text-zinc-400" /> : null}
        </div>
        <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-[#1a1a1c]">
          {connections.length === 0 ? (
            <div className="p-6 text-sm text-zinc-500">No user connectors are configured yet.</div>
          ) : (
            connections.map((connection) => (
              <div key={connection.connection_id} className="border-b border-zinc-100 p-4 last:border-b-0 dark:border-zinc-800">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div className="min-w-0 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold text-zinc-950 dark:text-white">{connection.name}</h3>
                      <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${statusClasses(connection.enabled ? connection.status : "disabled")}`}>
                        {connection.enabled ? connection.status : "disabled"}
                      </span>
                      <span className="text-xs text-zinc-400">{connection.connector_type}</span>
                    </div>
                    {connection.last_error ? <p className="text-sm text-red-500">{connection.last_error}</p> : null}
                    <div className="flex flex-wrap gap-2">
                      {connection.tools.slice(0, 8).map((tool) => (
                        <span key={tool.name} className="rounded border border-zinc-200 px-2 py-1 text-xs text-zinc-600 dark:border-zinc-800 dark:text-zinc-300">
                          {tool.name}
                        </span>
                      ))}
                      {connection.tool_count > 8 ? <span className="px-2 py-1 text-xs text-zinc-400">+{connection.tool_count - 8} more</span> : null}
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    {connection.provider === "mcp" ? (
                      <button onClick={() => void testMcp(connection)} className="rounded-lg border border-zinc-200 px-3 py-2 text-sm font-semibold dark:border-zinc-800">
                        Test
                      </button>
                    ) : null}
                    {connection.provider !== "google_drive" && (
                      <button onClick={() => void toggleConnection(connection)} className="rounded-lg border border-zinc-200 px-3 py-2 text-sm font-semibold dark:border-zinc-800">
                        {connection.enabled ? "Disable" : "Enable"}
                      </button>
                    )}
                    <button onClick={() => void deleteConnection(connection)} className="rounded-lg border border-red-500/20 px-3 py-2 text-sm font-semibold text-red-500">
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      {showMcp ? (
        <ConnectorModal title="Add Remote MCP Server" onClose={() => setShowMcp(false)}>
          <form onSubmit={submitMcp} className="space-y-4">
            <Field label="Server name" value={mcpName} onChange={setMcpName} placeholder="Production Postgres MCP" />
            <Field label="Streamable HTTP URL" value={mcpUrl} onChange={setMcpUrl} placeholder="https://example.com/mcp" />
            <Field label="Bearer token" value={mcpToken} onChange={setMcpToken} placeholder="Optional" type="password" />
            <SubmitButton loading={submitting} label="Test and Add Server" />
          </form>
        </ConnectorModal>
      ) : null}

      {showGithub ? (
        <ConnectorModal title="Connect GitHub" onClose={() => setShowGithub(false)}>
          <form onSubmit={submitGithub} className="space-y-4">
            <Field label="Personal access token" value={githubToken} onChange={setGithubToken} placeholder="github_pat_..." type="password" />
            <p className="text-xs leading-5 text-zinc-500">
              The token is stored server-side in private user storage and is never returned to the browser.
            </p>
            <SubmitButton loading={submitting} label="Connect GitHub" />
          </form>
        </ConnectorModal>
      ) : null}
    </div>
  );
}

function ConnectorModal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-lg border border-zinc-200 bg-white p-5 shadow-xl dark:border-zinc-800 dark:bg-[#1a1a1c]">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-emerald-500" />
            <h2 className="text-lg font-semibold text-zinc-950 dark:text-white">{title}</h2>
          </div>
          <button onClick={onClose} className="rounded-lg px-3 py-1 text-sm text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-900">
            Close
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        type={type}
        className="w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm outline-none transition focus:border-blue-500 dark:border-zinc-800 dark:bg-zinc-950"
      />
    </label>
  );
}

function SubmitButton({ loading, label }: { loading: boolean; label: string }) {
  return (
    <button
      disabled={loading}
      className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-zinc-950 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-zinc-800 disabled:opacity-60 dark:bg-white dark:text-zinc-950"
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
      {label}
    </button>
  );
}
