/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import { authenticatedFetch, parseApiError } from "@/lib/api-client";

export type OAuthPopupResult = "connected" | "closed" | "not-configured" | "redirected";

export type OAuthPopupOptions = {
  urlPath: string;
  messageTypes: string[];
  windowName: string;
  failLabel: string;
  onNotConfigured?: () => void;
};

export const MCP_OAUTH_PROVIDERS: Record<
  string,
  { windowName: string; messageType: string; failLabel: string }
> = {
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

/**
 * Shared OAuth popup flow (extracted from ConnectorsView so the onboarding
 * quick-connect modal can reuse the exact same behavior).
 *
 * Resolves "connected" when the provider posts back a success message,
 * "closed" when the popup is closed without a message, "not-configured"
 * when the backend reports 501, and "redirected" when the popup was blocked
 * and we fell back to a full-page redirect.
 */
export async function startOAuthPopup(opts: OAuthPopupOptions): Promise<OAuthPopupResult> {
  if (typeof window === "undefined") {
    throw new Error(opts.failLabel);
  }

  const response = await authenticatedFetch(opts.urlPath);
  if (response.status === 501 && opts.onNotConfigured) {
    opts.onNotConfigured();
    return "not-configured";
  }
  if (!response.ok) throw new Error(await parseApiError(response));
  const body = (await response.json()) as { auth_url?: string };
  const authUrl = body.auth_url;
  if (!authUrl) throw new Error(opts.failLabel);

  return new Promise<OAuthPopupResult>((resolve) => {
    let popupClosedPoll: number | null = null;
    const cleanup = () => {
      window.removeEventListener("message", handleMessage);
      if (popupClosedPoll !== null) window.clearInterval(popupClosedPoll);
    };
    const handleMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return;
      if (!opts.messageTypes.includes(event.data?.type)) return;
      cleanup();
      resolve("connected");
    };

    window.addEventListener("message", handleMessage);

    const width = 600;
    const height = 700;
    const left = window.screen.width / 2 - width / 2;
    const top = window.screen.height / 2 - height / 2;
    const popup = window.open(
      authUrl,
      opts.windowName,
      `width=${width},height=${height},top=${top},left=${left},scrollbars=yes`,
    );

    if (!popup) {
      cleanup();
      window.location.href = authUrl;
      resolve("redirected");
      return;
    }

    popupClosedPoll = window.setInterval(() => {
      if (popup.closed) {
        cleanup();
        resolve("closed");
      }
    }, 500);
  });
}

export function startGoogleConnect(onNotConfigured?: () => void) {
  return startOAuthPopup({
    urlPath: "/api/v1/auth/google/url",
    messageTypes: ["google_drive_connected", "google_connected"],
    windowName: "GoogleAuth",
    failLabel: "Failed to start Google OAuth",
    onNotConfigured,
  });
}

export function startGithubConnect(onNotConfigured?: () => void) {
  return startOAuthPopup({
    urlPath: "/api/v1/auth/github/url",
    messageTypes: ["github_connected"],
    windowName: "GitHubAuth",
    failLabel: "Failed to start GitHub OAuth",
    onNotConfigured,
  });
}

export function startSlackConnect(onNotConfigured?: () => void) {
  return startOAuthPopup({
    urlPath: "/api/v1/auth/slack/url",
    messageTypes: ["slack_connected"],
    windowName: "SlackAuth",
    failLabel: "Failed to start Slack OAuth",
    onNotConfigured,
  });
}

export function startMcpOAuthConnect(provider: string) {
  const config = MCP_OAUTH_PROVIDERS[provider];
  if (!config) return Promise.reject(new Error(`No OAuth flow for provider "${provider}"`));
  return startOAuthPopup({
    urlPath: `/api/v1/auth/${provider}/url`,
    messageTypes: [config.messageType],
    windowName: config.windowName,
    failLabel: config.failLabel,
  });
}
