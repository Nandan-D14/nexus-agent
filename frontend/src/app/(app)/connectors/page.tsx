"use client";

import { type FormEvent, type ReactNode, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Cloud,
  Loader2,
  Plus,
  RefreshCw,
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

function providerLogo(provider: string) {
  switch (provider) {
    case "google_drive":
      return "https://www.gstatic.com/images/branding/product/2x/drive_2020q4_48dp.png";
    case "gmail":
      return "https://www.gstatic.com/images/branding/product/2x/gmail_2020q4_48dp.png";
    case "google_calendar":
      return "https://www.gstatic.com/images/branding/product/2x/calendar_2020q4_48dp.png";
    case "google_tasks":
      return "https://upload.wikimedia.org/wikipedia/commons/5/5f/Google_Tasks_2021.svg";
    case "github":
      return "https://upload.wikimedia.org/wikipedia/commons/9/91/Octicons-mark-github.svg";
    default:
      return null;
  }
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

  const isGoogleProvider = (provider: string) => 
    ["google_drive", "gmail", "google_calendar", "google_tasks"].includes(provider);

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
        authenticatedFetch("/api/v1/integrations/catalog"),
        authenticatedFetch("/api/v1/integrations/connections"),
      ]);
      if (!catalogResponse.ok) throw new Error(await parseApiError(catalogResponse));
      if (!connectionsResponse.ok) throw new Error(await parseApiError(connectionsResponse));
      
      const catalogBody = (await catalogResponse.json()) as { catalog?: CatalogItem[] };
      const connectionsBody = (await connectionsResponse.json()) as { connections?: IntegrationConnection[] };
      
      setCatalog(catalogBody.catalog ?? []);
      setConnections(connectionsBody.connections ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load integrations");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function startGoogleConnect() {
    setError("");
    try {
      const response = await authenticatedFetch("/api/v1/auth/google/url");
      if (!response.ok) throw new Error(await parseApiError(response));
      const body = await response.json();

      let popupClosedPoll: number | null = null;
      const handleMessage = (event: MessageEvent) => {
        if (event.origin !== window.location.origin) return;
        if (event.data?.type !== "google_drive_connected" && event.data?.type !== "google_connected") return;

        window.removeEventListener("message", handleMessage);
        if (popupClosedPoll !== null) {
          window.clearInterval(popupClosedPoll);
        }

        void load();
      };

      window.addEventListener("message", handleMessage);
      
      const width = 600;
      const height = 700;
      const left = window.screen.width / 2 - width / 2;
      const top = window.screen.height / 2 - height / 2;
      
      const popup = window.open(
        body.auth_url,
        "GoogleAuth",
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
      setError(err instanceof Error ? err.message : "Failed to start Google OAuth");
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
    if (isGoogleProvider(connection.provider)) return;

    setError("");
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
  }

  async function deleteConnection(connection: IntegrationConnection) {
    setError("");

    if (isGoogleProvider(connection.provider)) {
      const response = await authenticatedFetch("/api/v1/auth/google", {
        method: "DELETE",
      });
      if (!response.ok) {
        setError(await parseApiError(response));
        return;
      }
      await load();
      return;
    }

    const response = await authenticatedFetch(`/api/v1/integrations/${connection.connection_id}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      setError(await parseApiError(response));
      return;
    }
    await load();
  }

  return (
    <div className="mx-auto max-w-6xl space-y-12 p-6 pb-24 md:p-12">
      <div className="flex items-end justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight text-white">
            Connectors
          </h1>
          <p className="text-sm text-zinc-500">
            Link your accounts to expand agent capabilities.
          </p>
        </div>
        <button
          onClick={() => void load()}
          className="p-2 text-zinc-500 hover:text-white transition-colors"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {error ? (
        <div className="flex items-start gap-3 rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-3 text-xs text-red-400">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
        {catalog.filter(item => item.provider !== "system").map((item) => {
          const logo = providerLogo(item.provider);
          const connection = connectionByProvider.get(item.provider);
          const status = connection?.enabled === false ? "disabled" : connection?.status || item.status;
          const isConnected = status === "connected";
          
          const handleClick = () => {
            if (isGoogleProvider(item.provider)) {
              startGoogleConnect();
            } else if (item.provider === "github") {
              setShowGithub(true);
            } else if (item.provider === "mcp") {
              setShowMcp(true);
            }
          };

          return (
            <motion.button
              key={`${item.provider}-${item.connector_type}`}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleClick}
              className={`group relative flex flex-col items-center justify-center rounded-2xl border aspect-square transition-all duration-200 ${
                isConnected 
                  ? "border-emerald-500/20 bg-emerald-500/[0.02]" 
                  : "border-zinc-800 bg-[#0d0d0f] hover:border-zinc-700 hover:bg-[#121214]"
              }`}
            >
              <div className="relative mb-4 flex h-12 w-12 items-center justify-center">
                {logo ? (
                  <img 
                    src={logo} 
                    alt={item.name} 
                    className={`h-10 w-10 object-contain transition-all duration-300 ${item.provider === "github" ? "dark:invert" : ""} ${isConnected ? "" : "grayscale opacity-40 group-hover:grayscale-0 group-hover:opacity-100"}`} 
                  />
                ) : (
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-zinc-800 text-zinc-400">
                    <Cloud className="h-5 w-5" />
                  </div>
                )}
                {isConnected && (
                  <div className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-emerald-500 shadow-lg shadow-emerald-500/20">
                    <CheckCircle2 className="h-3 w-3 text-white" />
                  </div>
                )}
              </div>
              <span className={`text-[12px] font-bold ${isConnected ? "text-emerald-400" : "text-zinc-400 group-hover:text-white"}`}>
                {item.name}
              </span>
            </motion.button>
          );
        })}
        
        <button
          onClick={() => setShowMcp(true)}
          className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-zinc-800 aspect-square transition-all hover:border-zinc-600 hover:bg-zinc-800/10"
        >
          <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-zinc-900 border border-zinc-800">
            <Plus className="h-5 w-5 text-zinc-600" />
          </div>
          <span className="text-[12px] font-bold text-zinc-500">Add MCP</span>
        </button>
      </div>

      <section className="space-y-6 pt-8">
        <div className="flex items-center gap-3">
          <h2 className="text-[10px] font-bold uppercase tracking-widest text-zinc-600">Active Connections</h2>
          <div className="h-px flex-1 bg-zinc-800/30" />
        </div>
        
        <div className="grid grid-cols-1 gap-2">
          {connections.length === 0 ? (
            <p className="py-4 text-[12px] text-zinc-600 italic text-center">No active connections.</p>
          ) : (
            connections.map((connection) => (
              <div key={connection.connection_id} className="flex items-center justify-between rounded-xl border border-zinc-800/30 bg-[#070708] px-4 py-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-zinc-900 border border-zinc-800/50">
                    {providerLogo(connection.provider) ? (
                      <img 
                        src={providerLogo(connection.provider)!} 
                        alt="" 
                        className={`h-4 w-4 object-contain ${connection.provider === "github" ? "dark:invert" : ""}`} 
                      />
                    ) : (
                      <Cloud className="h-4 w-4 text-zinc-600" />
                    )}
                  </div>
                  <div>
                    <h3 className="text-[13px] font-semibold text-zinc-300">{connection.name}</h3>
                    <p className="text-[9px] text-zinc-600 uppercase font-bold">{connection.connector_type}</p>
                  </div>
                </div>
                
                <div className="flex items-center gap-4">
                  {!isGoogleProvider(connection.provider) && (
                    <button 
                      onClick={() => void toggleConnection(connection)} 
                      className="text-[10px] font-bold text-zinc-600 hover:text-zinc-300"
                    >
                      {connection.enabled ? "Disable" : "Enable"}
                    </button>
                  )}
                  <button 
                    onClick={() => void deleteConnection(connection)} 
                    className="text-zinc-600 hover:text-red-500 transition-colors"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      {showMcp ? (
        <ConnectorModal title="Add Remote MCP Server" onClose={() => setShowMcp(false)}>
          <form onSubmit={submitMcp} className="space-y-4 pt-2">
            <Field label="Server Name" value={mcpName} onChange={mcpName => setMcpName(mcpName)} placeholder="e.g. Postgres DB" />
            <Field label="Endpoint URL" value={mcpUrl} onChange={mcpUrl => setMcpUrl(mcpUrl)} placeholder="https://..." />
            <Field label="Bearer Token" value={mcpToken} onChange={mcpToken => setMcpToken(mcpToken)} placeholder="Optional" type="password" />
            <SubmitButton loading={submitting} label="Link Server" />
          </form>
        </ConnectorModal>
      ) : null}

      {showGithub ? (
        <ConnectorModal title="Connect GitHub" onClose={() => setShowGithub(false)}>
          <form onSubmit={submitGithub} className="space-y-4 pt-2">
            <Field label="Personal Access Token" value={githubToken} onChange={githubToken => setGithubToken(githubToken)} placeholder="github_pat_..." type="password" />
            <p className="text-[11px] leading-relaxed text-zinc-500 px-1">
              Token is encrypted and stored securely server-side.
            </p>
            <SubmitButton loading={submitting} label="Link GitHub" />
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="w-full max-w-md rounded-3xl border border-zinc-800 bg-[#0d0d0f] p-6 shadow-2xl">
        <div className="mb-6 flex items-center justify-between px-1">
          <h2 className="text-lg font-bold text-white">{title}</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-white transition-colors">
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
    <label className="block space-y-2 px-1">
      <span className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        type={type}
        className="w-full rounded-xl border border-zinc-800 bg-black px-4 py-2.5 text-sm text-white outline-none transition focus:border-zinc-600 placeholder:text-zinc-700"
      />
    </label>
  );
}

function SubmitButton({ loading, label }: { loading: boolean; label: string }) {
  return (
    <button
      disabled={loading}
      className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-white px-4 py-3 text-sm font-bold text-black transition-all hover:bg-zinc-200 disabled:opacity-50 active:scale-95 mt-2"
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
      {label}
    </button>
  );
}
