/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

export type IntegrationTool = {
  name: string;
  description?: string;
  input_schema?: Record<string, unknown>;
};

export type IntegrationConnection = {
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

export type CatalogItem = {
  provider: string;
  connector_type: string;
  name: string;
  description: string;
  status: string;
  auth_mode?: "oauth" | "token";
};

export type ConnectorSectionId = "featured" | "search" | "developer";

export type ConnectorSection = {
  id: ConnectorSectionId;
  label: string;
  items: CatalogItem[];
};

const GOOGLE_PROVIDERS = new Set(["google_drive", "gmail", "google_calendar", "google_tasks"]);

/** Quick-connect tiles shown in the first-run "Connect your tools" onboarding modal. */
export const QUICK_CONNECT_PROVIDERS = [
  "google_drive",
  "gmail",
  "github",
  "slack",
  "google_calendar",
] as const;

export type QuickConnectProvider = (typeof QUICK_CONNECT_PROVIDERS)[number];

export const QUICK_CONNECT_LABELS: Record<string, string> = {
  google_drive: "Google Drive",
  gmail: "Gmail",
  github: "GitHub",
  slack: "Slack",
  google_calendar: "Calendar",
};

const QUICK_CONNECT_FALLBACKS: Record<string, CatalogItem> = {
  google_drive: {
    provider: "google_drive",
    connector_type: "native",
    name: "Google Drive",
    description: "Search, read, and create files in Google Drive.",
    status: "available",
  },
  gmail: {
    provider: "gmail",
    connector_type: "native",
    name: "Gmail",
    description: "Search, read, and send email from Gmail.",
    status: "available",
  },
  github: {
    provider: "github",
    connector_type: "native",
    name: "GitHub",
    description: "Search repos, read files, and push with git.",
    status: "available",
  },
  slack: {
    provider: "slack",
    connector_type: "mcp_remote_http",
    name: "Slack",
    description: "Search, read, and post in Slack.",
    status: "available",
  },
  google_calendar: {
    provider: "google_calendar",
    connector_type: "native",
    name: "Calendar",
    description: "List, create, and manage calendar events.",
    status: "available",
  },
};

/** Resolve quick-connect tiles from the catalog, falling back to stubs if the backend omits one. */
export function quickConnectItems(catalog: CatalogItem[]): CatalogItem[] {
  const byProvider = new Map(catalog.map((item) => [item.provider, item]));
  return QUICK_CONNECT_PROVIDERS.map(
    (provider) => byProvider.get(provider) ?? QUICK_CONNECT_FALLBACKS[provider],
  );
}

const FEATURED_PROVIDERS = [
  "google_drive",
  "gmail",
  "google_calendar",
  "google_tasks",
  "github",
  "linear",
  "vercel",
];
const SEARCH_PROVIDERS = ["exa", "treg", "tavily", "tinyfish"];
const DEVELOPER_PROVIDERS = ["cloudflare", "apify", "slack", "openai", "vyora", "composio", "mcp"];

const CATALOG_DEFAULTS: CatalogItem[] = [
  {
    provider: "linear",
    connector_type: "mcp_remote_http",
    name: "Linear",
    description: "Issues, projects, and comments through Linear MCP.",
    status: "available",
  },
  {
    provider: "vercel",
    connector_type: "mcp_remote_http",
    name: "Vercel",
    description: "Projects, deployments, and logs through Vercel MCP.",
    status: "available",
  },
  {
    provider: "cloudflare",
    connector_type: "mcp_remote_http",
    name: "Cloudflare",
    description: "Workers, DNS, and account tools through Cloudflare MCP.",
    status: "available",
  },
  {
    provider: "apify",
    connector_type: "mcp_remote_http",
    name: "Apify",
    description: "Actors, datasets, and crawls through Apify MCP.",
    status: "available",
  },
  {
    provider: "slack",
    connector_type: "mcp_remote_http",
    name: "Slack",
    description: "Search, read, and post in Slack through Slack MCP.",
    status: "available",
  },
  {
    provider: "openai",
    connector_type: "native",
    name: "OpenAI",
    description: "Web search via the OpenAI Responses API.",
    status: "available",
  },
  {
    provider: "vyora",
    connector_type: "native",
    name: "Vyora",
    description: "List agents, numbers, and trigger AI voice calls.",
    status: "available",
  },
  {
    provider: "treg",
    connector_type: "mcp_remote_http",
    name: "Treg",
    description: "SEO, SERP, backlinks, enrichment, ads, and social APIs via Treg MCP.",
    status: "available",
  },
  {
    provider: "composio",
    connector_type: "mcp_remote_http",
    name: "Composio",
    description: "Connect 1000+ apps through Composio MCP.",
    status: "available",
  },
];

/** Keep first-class connectors visible even if an older agent catalog omits them. */
export function mergeCatalogDefaults(catalog: CatalogItem[]): CatalogItem[] {
  const providers = new Set(catalog.map((item) => item.provider));
  const missing = CATALOG_DEFAULTS.filter((item) => !providers.has(item.provider));
  return missing.length ? [...catalog, ...missing] : catalog;
}

export function isGoogleProvider(provider: string): boolean {
  return GOOGLE_PROVIDERS.has(provider);
}

export function isMarketplaceProvider(provider: string): boolean {
  return provider !== "system";
}

export function providerLogo(provider: string): string | null {
  switch (provider) {
    case "google_drive":
      return "https://www.gstatic.com/images/branding/product/2x/drive_2020q4_48dp.png";
    case "gmail":
      return "https://www.gstatic.com/images/branding/product/2x/gmail_2020q4_48dp.png";
    case "google_calendar":
      return "https://www.gstatic.com/images/branding/product/2x/calendar_2020q4_48dp.png";
    case "google_tasks":
      return "/connectors/google-tasks.svg";
    case "github":
      return "https://upload.wikimedia.org/wikipedia/commons/9/91/Octicons-mark-github.svg";
    case "exa":
      return "https://exa.imgix.net/exa-logo.jpg";
    case "treg":
      return "/connectors/treg.svg";
    case "tavily":
      return "/connectors/tavily.svg";
    case "tinyfish":
      return "/connectors/tinyfish.png";
    case "linear":
      return "/connectors/linear.svg";
    case "vercel":
      return "/connectors/vercel.svg";
    case "cloudflare":
      return "/connectors/cloudflare.svg";
    case "apify":
      return "/connectors/apify.svg";
    case "slack":
      return "/connectors/slack.svg";
    case "openai":
      return "/connectors/openai.svg";
    case "vyora":
      return "/connectors/vyora.png";
    case "mcp":
      return "/connectors/mcp.svg";
    case "composio":
      return "/connectors/composio.svg";
    case "stripe":
      return "/connectors/stripe.svg";
    case "insights":
      return "/connectors/insights.svg";
    default:
      return null;
  }
}

export function providerLogoDark(provider: string): string | null {
  if (provider === "tavily") return "/connectors/tavily-dark.svg";
  return null;
}

export function invertLogoInDark(provider: string): boolean {
  return provider === "github" || provider === "vercel" || provider === "openai";
}

export function logoFillsTile(provider: string): boolean {
  return provider === "treg" || provider === "tavily" || provider === "mcp" || provider === "composio";
}

export function logoTileClass(provider: string): string {
  switch (provider) {
    case "treg":
      return "border-0 bg-[#211d16]";
    case "tavily":
      return "border-0 bg-white dark:bg-[#1F1E1E]";
    case "mcp":
      return "border border-zinc-200 bg-black dark:border-white/10";
    case "composio":
      return "border-0 bg-[#111111]";
    default:
      return "border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900";
  }
}

export function connectionByProvider(
  connections: IntegrationConnection[],
): Map<string, IntegrationConnection> {
  const map = new Map<string, IntegrationConnection>();
  for (const connection of connections) {
    if (connection.provider === "mcp") continue;
    if (!map.has(connection.provider)) map.set(connection.provider, connection);
  }
  return map;
}

export function isConnectorConnected(
  item: CatalogItem,
  connection: IntegrationConnection | undefined,
  googleConnected: boolean,
): boolean {
  if (isGoogleProvider(item.provider)) return googleConnected;
  const status = connection?.enabled === false ? "disabled" : connection?.status || item.status;
  return status === "connected";
}

export function isGoogleSuiteConnected(connections: IntegrationConnection[], catalog: CatalogItem[]): boolean {
  if (catalog.some((item) => isGoogleProvider(item.provider) && item.status === "connected")) {
    return true;
  }
  return connections.some(
    (connection) =>
      isGoogleProvider(connection.provider) &&
      connection.enabled !== false &&
      connection.status === "connected",
  );
}

export function marketplaceCatalog(catalog: CatalogItem[]): CatalogItem[] {
  return catalog.filter((item) => isMarketplaceProvider(item.provider));
}

export function searchCatalog(items: CatalogItem[], query: string): CatalogItem[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return items;
  return items.filter((item) => {
    const haystack = `${item.name} ${item.description} ${item.provider}`.toLowerCase();
    return haystack.includes(needle);
  });
}

function pickProviders(items: CatalogItem[], providers: string[]): CatalogItem[] {
  const byProvider = new Map(items.map((item) => [item.provider, item]));
  return providers
    .map((provider) => byProvider.get(provider))
    .filter((item): item is CatalogItem => Boolean(item));
}

export function mcpItemsFromConnections(connections: IntegrationConnection[]): CatalogItem[] {
  return connections
    .filter((connection) => connection.provider === "mcp")
    .map((connection) => ({
      provider: "mcp",
      connector_type: connection.connector_type || connection.connection_id,
      name: connection.name,
      description: "Remote MCP server connected to the agent.",
      status: connection.enabled === false ? "disabled" : connection.status,
    }));
}

export function groupCatalogSections(
  items: CatalogItem[],
  extraMcp: CatalogItem[] = [],
): ConnectorSection[] {
  const developer = [...pickProviders(items, DEVELOPER_PROVIDERS)];
  const seen = new Set(developer.map((item) => `${item.provider}:${item.connector_type}:${item.name}`));
  for (const item of extraMcp) {
    const key = `${item.provider}:${item.connector_type}:${item.name}`;
    if (seen.has(key)) continue;
    seen.add(key);
    developer.push(item);
  }

  return ([
    { id: "featured", label: "Featured", items: pickProviders(items, FEATURED_PROVIDERS) },
    { id: "search", label: "Search", items: pickProviders(items, SEARCH_PROVIDERS) },
    { id: "developer", label: "Developer", items: developer },
  ] as ConnectorSection[]).filter((section) => section.items.length > 0);
}

export function installedConnections(
  catalog: CatalogItem[],
  connections: IntegrationConnection[],
): CatalogItem[] {
  const market = marketplaceCatalog(catalog);
  const byProvider = connectionByProvider(connections);
  const googleConnected = isGoogleSuiteConnected(connections, catalog);
  const installed: CatalogItem[] = [];
  const seen = new Set<string>();

  for (const item of market) {
    const connection = byProvider.get(item.provider);
    if (!isConnectorConnected(item, connection, googleConnected)) continue;
    if (seen.has(item.provider) && item.provider !== "mcp") continue;
    seen.add(item.provider);
    installed.push(item);
  }

  for (const connection of connections) {
    if (connection.provider !== "mcp") continue;
    if (connection.enabled === false || connection.status !== "connected") continue;
    if (installed.some((item) => item.provider === "mcp" && item.name === connection.name)) continue;
    installed.push({
      provider: "mcp",
      connector_type: connection.connector_type,
      name: connection.name,
      description: "Remote MCP server",
      status: "connected",
    });
  }

  return installed;
}

export function resolveConnection(
  item: CatalogItem,
  connections: IntegrationConnection[],
): IntegrationConnection | undefined {
  if (item.provider === "mcp") {
    return connections.find(
      (connection) =>
        connection.provider === "mcp" &&
        (connection.name === item.name || connection.connector_type === item.connector_type),
    );
  }
  if (isGoogleProvider(item.provider)) {
    return connections.find((connection) => isGoogleProvider(connection.provider));
  }
  return connections.find((connection) => connection.provider === item.provider);
}

export type ConnectorDetail = {
  summary: string;
  capabilities: string[];
  connectHint: string;
};

const CONNECTOR_DETAILS: Record<string, ConnectorDetail> = {
  google_drive: {
    summary:
      "Let the agent search, read, create, and upload files in your Google Drive without leaving CoComputer.",
    capabilities: [
      "Search Drive by name or contents",
      "Read documents the agent needs as context",
      "Create and upload files into CoComputer folders",
    ],
    connectHint: "Connects with Google OAuth. One Google login covers Drive, Gmail, Calendar, and Tasks.",
  },
  gmail: {
    summary: "Search, read, and send email from Gmail so the agent can triage inboxes and draft replies.",
    capabilities: [
      "Search and read messages",
      "Draft and send email on your behalf",
      "Use threads as context for follow-ups",
    ],
    connectHint: "Connects with Google OAuth. One Google login covers Drive, Gmail, Calendar, and Tasks.",
  },
  google_calendar: {
    summary: "List, create, update, and delete calendar events so the agent can schedule and manage your day.",
    capabilities: [
      "List and read upcoming events",
      "Create, reschedule, edit, and cancel events with title, time, timezone, and optional guests",
      "Ask in chat: “Move Design Review to 10am” or “Cancel tomorrow’s standup.”",
    ],
    connectHint:
      "Connects with Google OAuth. One Google login covers Drive, Gmail, Calendar, and Tasks. Creating, updating, or deleting an event always shows an approval card in chat.",
  },
  google_tasks: {
    summary: "Manage Google Tasks lists and to-dos from the agent loop.",
    capabilities: [
      "List tasks in your default list",
      "Create to-dos with an optional due date",
      "Ask in chat: “Add a Google Task: send the weekly digest, due Friday 5pm.”",
    ],
    connectHint:
      "Connects with Google OAuth. One Google login covers Drive, Gmail, Calendar, and Tasks. Creating a task always shows an approval card in chat.",
  },
  github: {
    summary: "Search repos, read files, clone, create repositories, and push with git using your connected GitHub account.",
    capabilities: [
      "Search repositories and read files",
      "Clone a repo into the workspace",
      "Create a GitHub repository and push local code",
      "List and create issues",
      "Summarize pull requests",
    ],
    connectHint: "Connects with GitHub OAuth, the same popup flow as Google. A personal access token is optional fallback. Clone and push use the sandbox git CLI with your connected token.",
  },
  exa: {
    summary:
      "Live web search, clean page fetch, filtered retrieval, and multi-step Exa Agent research inside a session.",
    capabilities: [
      "Search the web with Exa and get citable results",
      "Fetch full page content as clean markdown",
      "Advanced filters (domains, dates, categories) and Exa Agent runs",
    ],
    connectHint: "Connects with Exa OAuth. Sign in at dashboard.exa.ai — no API key to paste.",
  },
  treg: {
    summary:
      "Keyword, SERP, backlink, enrichment, ads, and social APIs through one Treg MCP connection.",
    capabilities: [
      "Search the Treg catalog by job (keywords, backlinks, emails, ads)",
      "Call priced endpoints on your Treg team balance or your own keys",
      "Check remaining balance before expensive lookups",
    ],
    connectHint: "Connects with Treg OAuth. Sign in and pick your team — no API key to paste.",
  },
  tavily: {
    summary: "AI-oriented web search with results shaped for agents instead of a generic SERP dump.",
    capabilities: [
      "Live web search during a session",
      "Preferred source for discovery before scraping pages",
      "Returns concise, citable results",
    ],
    connectHint: "Requires a Tavily API key from tavily.com. It is encrypted and stored server-side.",
  },
  tinyfish: {
    summary: "Run browser automations on real websites from a natural-language goal.",
    capabilities: [
      "Operate real websites in a remote browser",
      "Complete multi-step UI tasks",
      "Use when native APIs are not available",
    ],
    connectHint:
      "Requires a Tinyfish API key from agent.tinyfish.ai/api-keys. It is encrypted and stored server-side.",
  },
  mcp: {
    summary: "Connect any Streamable HTTP MCP server and expose its tools to the agent.",
    capabilities: [
      "Bring your own MCP tools into a session",
      "Optional bearer token for private servers",
      "HTTPS required in production",
    ],
    connectHint: "You’ll enter a server name, HTTPS endpoint, and optional bearer token.",
  },
  composio: {
    summary:
      "Give the agent 1000+ apps (Gmail, Notion, Slack, GitHub, and more) through one Composio MCP connection.",
    capabilities: [
      "Search, connect, and run tools across connected apps",
      "Authorize each app in the browser the first time it is needed",
      "Seven meta-tools instead of a separate connector per app",
    ],
    connectHint:
      "Connects to https://connect.composio.dev/mcp. Optional consumer API key from connect.composio.dev if the server returns 401.",
  },
  linear: {
    summary: "Work Linear issues, projects, and comments from the session without leaving CoComputer.",
    capabilities: ["Search and update issues", "Read project and comment context", "Create work from the agent loop"],
    connectHint: "Connects with Linear OAuth through Linear MCP.",
  },
  vercel: {
    summary: "Inspect Vercel projects, deployments, and logs through Vercel MCP.",
    capabilities: ["List projects and deployments", "Read deployment logs", "Operate Vercel from the session"],
    connectHint:
      "Connects with Vercel OAuth. If Vercel rejects unapproved MCP clients, use Remote MCP as an escape hatch.",
  },
  cloudflare: {
    summary: "Use Cloudflare Workers, DNS, and account tools through Cloudflare MCP.",
    capabilities: ["Inspect Workers and DNS", "Read account resources", "Operate Cloudflare from the session"],
    connectHint: "Connects with Cloudflare OAuth through Cloudflare MCP.",
  },
  apify: {
    summary: "Run Apify actors and read datasets through Apify MCP.",
    capabilities: ["Start and inspect actors", "Read datasets and crawls", "Automate scraping jobs"],
    connectHint: "Connects with Apify OAuth through Apify MCP.",
  },
  slack: {
    summary: "Search, read, and post in Slack through Slack MCP.",
    capabilities: ["Search messages", "Read channel history", "Post updates from the agent"],
    connectHint: "Connects with Slack OAuth, the same popup flow as Google.",
  },
  openai: {
    summary: "Give the agent OpenAI Responses web search as a first-class connector, separate from Gemini BYOK.",
    capabilities: ["Live web search via the Responses API", "Citable answers during a session"],
    connectHint: "Requires an OpenAI API key. It is encrypted and stored server-side.",
  },
  vyora: {
    summary: "List Vyora agents and numbers, trigger outbound AI calls, and poll call results.",
    capabilities: ["List agents and caller-line numbers", "Start outbound calls", "List and inspect call records"],
    connectHint: "Requires a Vyora API key from Settings → Integrations. It is encrypted and stored server-side.",
  },
};

export function connectorDetail(item: CatalogItem): ConnectorDetail {
  return (
    CONNECTOR_DETAILS[item.provider] ?? {
      summary: item.description,
      capabilities: [],
      connectHint: "Connect this tool so the agent can use it in sessions.",
    }
  );
}
