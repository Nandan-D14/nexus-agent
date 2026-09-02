/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { type FormEvent, useCallback, useMemo, useState } from "react";
import { AlertCircle, Search } from "lucide-react";

import { ConnectorDetailModal } from "@/components/connectors/connector-detail-modal";
import { ConnectorLogo } from "@/components/connectors/connector-logo";
import {
  ConnectorField,
  ConnectorModal,
  ConnectorSubmitButton,
} from "@/components/connectors/connector-modal";
import { ConnectorRow } from "@/components/connectors/connector-row";
import { ConnectorsSkeleton } from "@/components/connectors/connectors-skeleton";
import { authenticatedFetch, parseApiError } from "@/lib/api-client";
import {
  type CatalogItem,
  type IntegrationConnection,
  groupCatalogSections,
  installedConnections,
  isConnectorConnected,
  isGoogleProvider,
  isGoogleSuiteConnected,
  marketplaceCatalog,
  mcpItemsFromConnections,
  mergeCatalogDefaults,
  resolveConnection,
  searchCatalog,
} from "@/lib/connectors";
import { invalidateIntegrations } from "@/lib/queries/invalidate";
import {
  useConnectComposioMutation,
  useConnectGithubMutation,
  useConnectMcpMutation,
  useConnectOpenAIMutation,
  useConnectTavilyMutation,
  useConnectTinyfishMutation,
  useConnectVyoraMutation,
  useDeleteIntegrationMutation,
  useDisconnectGoogleMutation,
  useIntegrationsCatalogQuery,
  useIntegrationsConnectionsQuery,
  useToggleIntegrationMutation,
} from "@/lib/queries/integrations";
import { useQueryClient } from "@tanstack/react-query";

function rowId(item: CatalogItem): string {
  return `connector-${item.provider}-${item.connector_type}`.replace(/[^a-zA-Z0-9_-]/g, "-");
}

const MCP_OAUTH_PROVIDERS: Record<string, { windowName: string; messageType: string; failLabel: string }> = {
  exa: { windowName: "ExaAuth", messageType: "exa_connected", failLabel: "Failed to start Exa OAuth" },
  treg: { windowName: "TregAuth", messageType: "treg_connected", failLabel: "Failed to start Treg OAuth" },
  linear: { windowName: "LinearAuth", messageType: "linear_connected", failLabel: "Failed to start Linear OAuth" },
  vercel: { windowName: "VercelAuth", messageType: "vercel_connected", failLabel: "Failed to start Vercel OAuth" },
  cloudflare: {
    windowName: "CloudflareAuth",
    messageType: "cloudflare_connected",
    failLabel: "Failed to start Cloudflare OAuth",
  },
  apify: { windowName: "ApifyAuth", messageType: "apify_connected", failLabel: "Failed to start Apify OAuth" },
};

export function ConnectorsView() {
  const queryClient = useQueryClient();
  const catalogQuery = useIntegrationsCatalogQuery();
  const connectionsQuery = useIntegrationsConnectionsQuery();
  const toggleMutation = useToggleIntegrationMutation();
  const deleteMutation = useDeleteIntegrationMutation();
  const disconnectGoogleMutation = useDisconnectGoogleMutation();
  const connectMcpMutation = useConnectMcpMutation();
  const connectComposioMutation = useConnectComposioMutation();
  const connectGithubMutation = useConnectGithubMutation();
  const connectTavilyMutation = useConnectTavilyMutation();
  const connectTinyfishMutation = useConnectTinyfishMutation();
  const connectVyoraMutation = useConnectVyoraMutation();
  const connectOpenAIMutation = useConnectOpenAIMutation();
  const connections = connectionsQuery.data ?? [];
  const loading = catalogQuery.isLoading || connectionsQuery.isLoading;
  const [error, setError] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [showMcp, setShowMcp] = useState(false);
  const [showComposio, setShowComposio] = useState(false);
  const [showGithub, setShowGithub] = useState(false);
  const [showTavily, setShowTavily] = useState(false);
  const [showTinyfish, setShowTinyfish] = useState(false);
  const [showVyora, setShowVyora] = useState(false);
  const [showOpenai, setShowOpenai] = useState(false);
  const [mcpName, setMcpName] = useState("");
  const [mcpUrl, setMcpUrl] = useState("");
  const [mcpToken, setMcpToken] = useState("");
  const [composioKey, setComposioKey] = useState("");
  const [githubToken, setGithubToken] = useState("");
  const [tavilyKey, setTavilyKey] = useState("");
  const [tinyfishKey, setTinyfishKey] = useState("");
  const [vyoraKey, setVyoraKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [selectedItem, setSelectedItem] = useState<CatalogItem | null>(null);
  const [connecting, setConnecting] = useState(false);

  const queryError =
    catalogQuery.error instanceof Error
      ? catalogQuery.error.message
      : connectionsQuery.error instanceof Error
        ? connectionsQuery.error.message
        : "";
  const displayError = error || queryError;

  const refreshIntegrations = useCallback(() => {
    invalidateIntegrations(queryClient);
  }, [queryClient]);

  const catalog = useMemo(
    () => mergeCatalogDefaults(catalogQuery.data ?? []),
    [catalogQuery.data],
  );

  const googleConnected = useMemo(
    () => isGoogleSuiteConnected(connections, catalog),
    [catalog, connections],
  );

  const market = useMemo(() => marketplaceCatalog(catalog), [catalog]);
  const extraMcp = useMemo(() => mcpItemsFromConnections(connections), [connections]);
  const visibleCatalog = useMemo(() => searchCatalog(market, searchInput), [market, searchInput]);
  const sections = useMemo(
    () => groupCatalogSections(visibleCatalog, searchCatalog(extraMcp, searchInput)),
    [extraMcp, visibleCatalog, searchInput],
  );
  const installed = useMemo(
    () => installedConnections(catalog, connections),
    [catalog, connections],
  );

  const startOauthPopup = async (opts: {
    urlPath: string;
    messageTypes: string[];
    windowName: string;
    failLabel: string;
    onNotConfigured?: () => void;
  }) => {
    setError("");
    setConnecting(true);
    try {
      const response = await authenticatedFetch(opts.urlPath);
      if (response.status === 501 && opts.onNotConfigured) {
        setConnecting(false);
        opts.onNotConfigured();
        return;
      }
      if (!response.ok) throw new Error(await parseApiError(response));
      const body = await response.json();

      let popupClosedPoll: number | null = null;
      const handleMessage = (event: MessageEvent) => {
        if (event.origin !== window.location.origin) return;
        if (!opts.messageTypes.includes(event.data?.type)) return;

        window.removeEventListener("message", handleMessage);
        if (popupClosedPoll !== null) window.clearInterval(popupClosedPoll);
        setSelectedItem(null);
        setConnecting(false);
        refreshIntegrations();
      };

      window.addEventListener("message", handleMessage);

      const width = 600;
      const height = 700;
      const left = window.screen.width / 2 - width / 2;
      const top = window.screen.height / 2 - height / 2;
      const popup = window.open(
        body.auth_url,
        opts.windowName,
        `width=${width},height=${height},top=${top},left=${left},scrollbars=yes`,
      );

      if (!popup) {
        window.removeEventListener("message", handleMessage);
        setConnecting(false);
        window.location.href = body.auth_url;
        return;
      }

      popupClosedPoll = window.setInterval(() => {
        if (popup.closed) {
          window.clearInterval(popupClosedPoll as number);
          window.removeEventListener("message", handleMessage);
          setConnecting(false);
          refreshIntegrations();
        }
      }, 500);
    } catch (err) {
      setError(err instanceof Error ? err.message : opts.failLabel);
      setConnecting(false);
    }
  };

  const startGoogleConnect = async () => {
    await startOauthPopup({
      urlPath: "/api/v1/auth/google/url",
      messageTypes: ["google_drive_connected", "google_connected"],
      windowName: "GoogleAuth",
      failLabel: "Failed to start Google OAuth",
    });
  };

  const startGithubConnect = async () => {
    await startOauthPopup({
      urlPath: "/api/v1/auth/github/url",
      messageTypes: ["github_connected"],
      windowName: "GitHubAuth",
      failLabel: "Failed to start GitHub OAuth",
      onNotConfigured: () => {
        setSelectedItem(null);
        setShowGithub(true);
      },
    });
  };

  const startSlackConnect = async () => {
    await startOauthPopup({
      urlPath: "/api/v1/auth/slack/url",
      messageTypes: ["slack_connected"],
      windowName: "SlackAuth",
      failLabel: "Failed to start Slack OAuth",
    });
  };

  const startMcpOauthConnect = async (provider: string) => {
    const config = MCP_OAUTH_PROVIDERS[provider];
    if (!config) return;
    await startOauthPopup({
      urlPath: `/api/v1/auth/${provider}/url`,
      messageTypes: [config.messageType],
      windowName: config.windowName,
      failLabel: config.failLabel,
    });
  };

  const connectItem = (item: CatalogItem) => {
    if (isGoogleProvider(item.provider)) {
      void startGoogleConnect();
      return;
    }
    if (item.provider === "github") {
      void startGithubConnect();
      return;
    }
    if (item.provider === "slack") {
      void startSlackConnect();
      return;
    }
    if (item.provider in MCP_OAUTH_PROVIDERS) {
      void startMcpOauthConnect(item.provider);
      return;
    }
    setSelectedItem(null);
    if (item.provider === "tavily") setShowTavily(true);
    else if (item.provider === "tinyfish") setShowTinyfish(true);
    else if (item.provider === "vyora") setShowVyora(true);
    else if (item.provider === "openai") setShowOpenai(true);
    else if (item.provider === "composio") setShowComposio(true);
    else if (item.provider === "mcp") setShowMcp(true);
  };

  const openDetails = (item: CatalogItem) => setSelectedItem(item);

  const submitMcp = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
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
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add MCP server");
    } finally {
      setSubmitting(false);
    }
  };

  const submitComposio = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await connectComposioMutation.mutateAsync(composioKey);
      setShowComposio(false);
      setComposioKey("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to connect Composio");
    } finally {
      setSubmitting(false);
    }
  };

  const submitGithub = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await connectGithubMutation.mutateAsync(githubToken);
      setShowGithub(false);
      setGithubToken("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to connect GitHub");
    } finally {
      setSubmitting(false);
    }
  };

  const submitTavily = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await connectTavilyMutation.mutateAsync(tavilyKey);
      setShowTavily(false);
      setTavilyKey("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to connect Tavily");
    } finally {
      setSubmitting(false);
    }
  };

  const submitTinyfish = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await connectTinyfishMutation.mutateAsync(tinyfishKey);
      setShowTinyfish(false);
      setTinyfishKey("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to connect Tinyfish");
    } finally {
      setSubmitting(false);
    }
  };

  const submitVyora = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await connectVyoraMutation.mutateAsync(vyoraKey);
      setShowVyora(false);
      setVyoraKey("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to connect Vyora");
    } finally {
      setSubmitting(false);
    }
  };

  const submitOpenai = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await connectOpenAIMutation.mutateAsync(openaiKey);
      setShowOpenai(false);
      setOpenaiKey("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to connect OpenAI");
    } finally {
      setSubmitting(false);
    }
  };

  const toggleConnection = async (connection: IntegrationConnection) => {
    if (isGoogleProvider(connection.provider)) return;
    setError("");
    try {
      await toggleMutation.mutateAsync(connection);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update connector");
    }
  };

  const deleteConnection = async (connection: IntegrationConnection) => {
    setError("");
    try {
      await deleteMutation.mutateAsync(connection);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove connector");
    }
  };

  const disconnectItem = async (item: CatalogItem, connection?: IntegrationConnection) => {
    if (isGoogleProvider(item.provider) || !connection) {
      if (isGoogleProvider(item.provider)) {
        setError("");
        try {
          await disconnectGoogleMutation.mutateAsync();
        } catch (err) {
          setError(err instanceof Error ? err.message : "Failed to disconnect Google");
        }
        return;
      }
      return;
    }
    await deleteConnection(connection);
  };

  const scrollToRow = (item: CatalogItem) => {
    document.getElementById(rowId(item))?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  const connection = selectedItem ? resolveConnection(selectedItem, connections) : undefined;
  const connected = selectedItem
    ? isConnectorConnected(selectedItem, connection, googleConnected)
    : false;

  return (
    <div className="mx-auto flex h-full max-w-4xl flex-col p-4 pb-20 text-zinc-900 md:p-8 dark:text-zinc-100">
      <div className="flex shrink-0 flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="font-serif text-3xl leading-none tracking-tight text-zinc-900 sm:text-4xl dark:text-white">
            Connectors
          </h1>
          <p className="mt-2 text-sm text-zinc-500">
            Work with CoComputer across your favorite tools.
          </p>
        </div>
        <div className="relative w-full shrink-0 sm:mt-1 sm:w-64">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-zinc-500" />
          <input
            type="search"
            placeholder="Search connectors"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            className="w-full rounded-full border border-zinc-200 bg-[#f4f4f5] py-2 pr-4 pl-10 text-sm text-zinc-900 placeholder-zinc-500 outline-none transition-colors focus:ring-1 focus:ring-zinc-400 dark:border-[#2f2f35] dark:bg-[#212126] dark:text-zinc-100 dark:focus:ring-zinc-600"
          />
        </div>
      </div>

      {displayError ? (
        <div className="mt-6 flex items-center gap-3 rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-600 dark:text-red-400">
          <AlertCircle className="size-5 shrink-0" />
          <p>{displayError}</p>
        </div>
      ) : null}

      <div className="mt-10 min-h-0 flex-1 overflow-y-auto pr-1 no-scrollbar">
        {loading ? (
          <ConnectorsSkeleton />
        ) : (
          <div className="space-y-10">
            {!searchInput.trim() ? (
              <section>
                <h2 className="mb-4 text-sm font-medium text-zinc-900 dark:text-zinc-100">Installed</h2>
                {installed.length === 0 ? (
                  <p className="text-sm text-zinc-500">No connectors installed yet.</p>
                ) : (
                  <div className="flex flex-wrap gap-3">
                    {installed.map((item) => (
                      <button
                        key={`${item.provider}-${item.connector_type}-${item.name}`}
                        type="button"
                        onClick={() => openDetails(item)}
                        className="rounded-xl transition-transform hover:scale-[1.03]"
                        aria-label={item.name}
                      >
                        <ConnectorLogo provider={item.provider} name={item.name} size="sm" />
                      </button>
                    ))}
                  </div>
                )}
              </section>
            ) : null}

            {sections.length === 0 ? (
              <div className="flex h-48 items-center justify-center rounded-2xl border border-dashed border-zinc-300 text-sm text-zinc-500 dark:border-white/10">
                No connectors match your search
              </div>
            ) : (
              sections.map((section) => (
                <section key={section.id}>
                  <h2 className="mb-2 px-3 text-sm text-zinc-500">{section.label}</h2>
                  <div className="grid grid-cols-1 md:grid-cols-2">
                    {section.items.map((item) => {
                      const connection = resolveConnection(item, connections);
                      const connected = isConnectorConnected(item, connection, googleConnected);
                      return (
                        <ConnectorRow
                          key={`${item.provider}-${item.connector_type}-${item.name}`}
                          item={item}
                          connected={connected}
                          connection={connection}
                          rowId={rowId(item)}
                          onOpen={() => openDetails(item)}
                          onToggle={connection && !isGoogleProvider(item.provider) ? () => void toggleConnection(connection) : undefined}
                          onDisconnect={
                            connected
                              ? () => void disconnectItem(item, connection)
                              : undefined
                          }
                        />
                      );
                    })}
                  </div>
                </section>
              ))
            )}
          </div>
        )}
      </div>

      {showMcp ? (
        <ConnectorModal title="Add Remote MCP Server" onClose={() => setShowMcp(false)}>
          <form onSubmit={submitMcp} className="space-y-4">
            <ConnectorField
              label="Server Name"
              value={mcpName}
              onChange={setMcpName}
              placeholder="e.g. Postgres DB"
            />
            <ConnectorField
              label="Endpoint URL"
              value={mcpUrl}
              onChange={setMcpUrl}
              placeholder="https://..."
            />
            <ConnectorField
              label="Bearer Token"
              value={mcpToken}
              onChange={setMcpToken}
              placeholder="Optional"
              type="password"
            />
            <ConnectorSubmitButton loading={submitting} label="Link Server" />
          </form>
        </ConnectorModal>
      ) : null}

      {showComposio ? (
        <ConnectorModal title="Connect Composio" onClose={() => setShowComposio(false)}>
          <form onSubmit={submitComposio} className="space-y-4">
            <ConnectorField
              label="Endpoint URL"
              value="https://connect.composio.dev/mcp"
              onChange={() => undefined}
              readOnly
            />
            <ConnectorField
              label="Consumer API key"
              value={composioKey}
              onChange={setComposioKey}
              placeholder="Optional — ck_..."
              type="password"
            />
            <p className="text-xs leading-relaxed text-zinc-500">
              Leave the key blank first. If connect fails with 401, paste a consumer API key from
              connect.composio.dev (Settings → Sessions & API Key).
            </p>
            {error ? <p className="text-xs leading-relaxed text-red-500">{error}</p> : null}
            <ConnectorSubmitButton loading={submitting} label="Link Composio" />
          </form>
        </ConnectorModal>
      ) : null}

      {selectedItem ? (
        <ConnectorDetailModal
          item={selectedItem}
          connected={connected}
          connection={connection}
          connecting={connecting}
          onClose={() => {
            if (!connecting) setSelectedItem(null);
          }}
          onConnect={() => connectItem(selectedItem)}
          onToggle={
            connection && !isGoogleProvider(selectedItem.provider)
              ? () => void toggleConnection(connection)
              : undefined
          }
          onDisconnect={
            connected
              ? () => {
                  void disconnectItem(selectedItem, connection);
                  setSelectedItem(null);
                }
              : undefined
          }
          secondaryAction={
            selectedItem.provider === "github" && !connected
              ? {
                  label: "Use a personal access token instead",
                  onClick: () => {
                    setSelectedItem(null);
                    setShowGithub(true);
                  },
                }
              : undefined
          }
        />
      ) : null}

      {showGithub ? (
        <ConnectorModal title="Connect GitHub" onClose={() => setShowGithub(false)}>
          <form onSubmit={submitGithub} className="space-y-4">
            <ConnectorField
              label="Personal Access Token"
              value={githubToken}
              onChange={setGithubToken}
              placeholder="github_pat_..."
              type="password"
            />
            <p className="text-xs leading-relaxed text-zinc-500">
              Create a classic PAT with repo and read:user. It is encrypted and stored securely
              server-side.
            </p>
            <ConnectorSubmitButton loading={submitting} label="Link GitHub" />
          </form>
        </ConnectorModal>
      ) : null}

      {showTavily ? (
        <ConnectorModal title="Connect Tavily" onClose={() => setShowTavily(false)}>
          <form onSubmit={submitTavily} className="space-y-4">
            <ConnectorField
              label="API Key"
              value={tavilyKey}
              onChange={setTavilyKey}
              placeholder="tvly-..."
              type="password"
            />
            <p className="text-xs leading-relaxed text-zinc-500">
              Get your key at tavily.com. It is encrypted and stored securely server-side.
            </p>
            <ConnectorSubmitButton loading={submitting} label="Link Tavily" />
          </form>
        </ConnectorModal>
      ) : null}

      {showTinyfish ? (
        <ConnectorModal title="Connect Tinyfish" onClose={() => setShowTinyfish(false)}>
          <form onSubmit={submitTinyfish} className="space-y-4">
            <ConnectorField
              label="API Key"
              value={tinyfishKey}
              onChange={setTinyfishKey}
              placeholder="..."
              type="password"
            />
            <p className="text-xs leading-relaxed text-zinc-500">
              Get your key at agent.tinyfish.ai/api-keys. It is encrypted and stored securely
              server-side.
            </p>
            <ConnectorSubmitButton loading={submitting} label="Link Tinyfish" />
          </form>
        </ConnectorModal>
      ) : null}

      {showVyora ? (
        <ConnectorModal title="Connect Vyora" onClose={() => setShowVyora(false)}>
          <form onSubmit={submitVyora} className="space-y-4">
            <ConnectorField
              label="API Key"
              value={vyoraKey}
              onChange={setVyoraKey}
              placeholder="vya_live_..."
              type="password"
            />
            <p className="text-xs leading-relaxed text-zinc-500">
              Get your key from Vyora Settings → Integrations. It is encrypted and stored securely
              server-side.
            </p>
            <ConnectorSubmitButton loading={submitting} label="Link Vyora" />
          </form>
        </ConnectorModal>
      ) : null}

      {showOpenai ? (
        <ConnectorModal title="Connect OpenAI" onClose={() => setShowOpenai(false)}>
          <form onSubmit={submitOpenai} className="space-y-4">
            <ConnectorField
              label="API Key"
              value={openaiKey}
              onChange={setOpenaiKey}
              placeholder="sk-..."
              type="password"
            />
            <p className="text-xs leading-relaxed text-zinc-500">
              Uses the Responses API for web search. This is separate from Gemini BYOK in Settings.
            </p>
            <ConnectorSubmitButton loading={submitting} label="Link OpenAI" />
          </form>
        </ConnectorModal>
      ) : null}
    </div>
  );
}
