/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { authenticatedFetch, errorFromApiResponse, readApiError } from "./api-client";
import { DEFAULT_PLAN_QUOTA, type PlanQuota } from "./message-types";

export type GeminiProvider = "apiKey" | "vertex";

export type LlmProviderId =
  | "openai"
  | "anthropic"
  | "gemini"
  | "groq"
  | "openrouter"
  | "orcarouter"
  | "deepseek"
  | "mistral"
  | "xai"
  | "custom";

export type LlmProviderInfo = {
  id: string;
  name: string;
  description: string;
  signupUrl: string;
  keyUrl: string;
  docsUrl: string;
  apiBase: string;
  defaultModel: string;
  defaultVisionModel: string;
  recommendedModels: string[];
  steps: string[];
  notes: string;
  visionWarning: string;
  custom: boolean;
  logoUrl: string;
  logoInvertInDark: boolean;
};

export type E2bSetupInfo = {
  signupUrl: string;
  keyUrl: string;
  docsUrl: string;
  steps: string[];
  notes: string;
  logoUrl: string;
  logoInvertInDark: boolean;
};

export type ByokSettings = {
  e2bKeySet: boolean;
  geminiKeySet: boolean;
  geminiProvider: GeminiProvider;
  llmKeySet: boolean;
  llmProvider: string;
  llmModel: string;
  llmVisionModel: string;
  llmApiBase: string;
  missing: string[];
  configured: boolean;
  vertexConfigured: boolean;
  sharedAccessEnabled: boolean;
  sharedAccessCodeConfigured: boolean;
  serverE2bConfigured: boolean;
};

export type UserSettingsResponse = {
  requireByok: boolean;
  googleDriveConnected: boolean;
  settings: Record<string, unknown>;
  byok: ByokSettings;
  llmProviders: LlmProviderInfo[];
  e2bSetup: E2bSetupInfo;
};

export type UserSettingsUpdatePayload = {
  settings?: Record<string, unknown>;
  byok?: {
    e2bApiKey?: string | null;
    geminiApiKey?: string | null;
    geminiProvider?: GeminiProvider;
    accessCode?: string | null;
    llmProvider?: string;
    llmApiKey?: string | null;
    llmModel?: string | null;
    llmVisionModel?: string | null;
    llmApiBase?: string | null;
  };
};

export type AutonomyMode = "manual" | "auto";
export type ArtifactOpenMode = "in_app" | "browser";

export type NotificationPrefs = {
  critical: boolean;
  system: boolean;
  sound: boolean;
};

export type ProfilePrefs = {
  firstName: string;
  lastName: string;
};

export type AppSettingsBlob = {
  notifications?: NotificationPrefs;
  profile?: ProfilePrefs;
  agentRules?: string;
  autonomyMode?: AutonomyMode;
  artifactOpenMode?: ArtifactOpenMode;
};

export const DEFAULT_NOTIFICATIONS: NotificationPrefs = {
  critical: true,
  system: false,
  sound: false,
};

const DEFAULT_PROFILE: ProfilePrefs = { firstName: "", lastName: "" };

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asBool(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

export function readAppSettings(data: UserSettingsResponse): Required<AppSettingsBlob> {
  const raw = asRecord(data.settings);
  const notifications = asRecord(raw.notifications);
  const profile = asRecord(raw.profile);
  const autonomy = asString(raw.autonomyMode);
  const artifactOpen = asString(raw.artifactOpenMode);
  return {
    notifications: {
      critical: asBool(notifications.critical, DEFAULT_NOTIFICATIONS.critical),
      system: asBool(notifications.system, DEFAULT_NOTIFICATIONS.system),
      sound: asBool(notifications.sound, DEFAULT_NOTIFICATIONS.sound),
    },
    profile: {
      firstName: asString(profile.firstName),
      lastName: asString(profile.lastName),
    },
    agentRules: asString(raw.agentRules),
    autonomyMode: autonomy === "auto" ? "auto" : "manual",
    artifactOpenMode: artifactOpen === "browser" ? "browser" : "in_app",
  };
}

export async function patchAppSettings(
  partial: AppSettingsBlob,
): Promise<UserSettingsResponse> {
  const current = await fetchUserSettings();
  const parsed = readAppSettings(current);
  const next: Required<AppSettingsBlob> = {
    ...parsed,
    ...partial,
    notifications: partial.notifications
      ? { ...parsed.notifications, ...partial.notifications }
      : parsed.notifications,
    profile: partial.profile ? { ...parsed.profile, ...partial.profile } : parsed.profile,
  };
  return updateUserSettings({
    settings: {
      ...current.settings,
      notifications: next.notifications,
      profile: next.profile,
      agentRules: next.agentRules,
      autonomyMode: next.autonomyMode,
      artifactOpenMode: next.artifactOpenMode,
    },
  });
}

export async function fetchUserQuota(): Promise<PlanQuota> {
  const response = await authenticatedFetch("/api/v1/user/quota");
  if (!response.ok) {
    throw errorFromApiResponse(response, await readApiError(response));
  }
  const body = (await response.json()) as Partial<PlanQuota>;
  return {
    ...DEFAULT_PLAN_QUOTA,
    ...body,
    plan: body.plan ?? DEFAULT_PLAN_QUOTA.plan,
    credits: body.credits ?? DEFAULT_PLAN_QUOTA.credits,
    tokens: body.tokens ?? DEFAULT_PLAN_QUOTA.tokens,
  };
}

export function splitDisplayName(name: string | null | undefined): ProfilePrefs {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return { ...DEFAULT_PROFILE };
  if (parts.length === 1) return { firstName: parts[0], lastName: "" };
  return { firstName: parts[0], lastName: parts.slice(1).join(" ") };
}

export function requiresByokSetup(data: UserSettingsResponse): boolean {
  return data.requireByok && data.byok.missing.length > 0;
}

export function byokMissingLabels(missing: string[]): string[] {
  return missing.map((key) => {
    if (key === "e2b") return "E2B API key";
    if (key === "llm") return "LLM provider and API key";
    return key;
  });
}

export function formatByokMissingMessage(missing: string[]): string {
  const labels = byokMissingLabels(missing);
  if (labels.length === 0) {
    return "Add your API keys in Settings before starting a session.";
  }
  if (labels.length === 1) {
    return `Add your ${labels[0]} in Settings before starting a session.`;
  }
  const last = labels[labels.length - 1];
  return `Add your ${labels.slice(0, -1).join(", ")} and ${last} in Settings before starting a session.`;
}

function normalizeUserSettings(body: UserSettingsResponse): UserSettingsResponse {
  return {
    ...body,
    llmProviders: Array.isArray(body.llmProviders) ? body.llmProviders : [],
    e2bSetup: body.e2bSetup ?? {
      signupUrl: "",
      keyUrl: "",
      docsUrl: "",
      steps: [],
      notes: "",
      logoUrl: "/llm-providers/e2b.svg",
      logoInvertInDark: false,
    },
    byok: {
      ...body.byok,
      llmKeySet: Boolean(body.byok?.llmKeySet),
      llmProvider: body.byok?.llmProvider ?? "",
      llmModel: body.byok?.llmModel ?? "",
      llmVisionModel: body.byok?.llmVisionModel ?? "",
      llmApiBase: body.byok?.llmApiBase ?? "",
    },
  };
}

export async function fetchUserSettings(): Promise<UserSettingsResponse> {
  const response = await authenticatedFetch("/api/v1/user/settings");
  if (!response.ok) {
    throw errorFromApiResponse(response, await readApiError(response));
  }
  return normalizeUserSettings((await response.json()) as UserSettingsResponse);
}

export async function updateUserSettings(
  payload: UserSettingsUpdatePayload,
): Promise<UserSettingsResponse> {
  const response = await authenticatedFetch("/api/v1/user/settings", {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const error = await readApiError(response);
    throw new Error(error.message);
  }

  return normalizeUserSettings((await response.json()) as UserSettingsResponse);
}

export async function testLlmConnection(payload: {
  llmProvider?: string;
  llmApiKey?: string;
  llmModel?: string;
  llmVisionModel?: string;
  llmApiBase?: string;
}): Promise<{ ok: boolean; model: string }> {
  const response = await authenticatedFetch("/api/v1/user/settings/test-llm", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await readApiError(response);
    throw new Error(error.message);
  }
  return (await response.json()) as { ok: boolean; model: string };
}

export async function fetchLlmModels(payload: {
  llmProvider?: string;
  llmApiKey?: string;
  llmModel?: string;
  llmApiBase?: string;
}): Promise<{ models: string[]; apiBase: string }> {
  const response = await authenticatedFetch("/api/v1/user/settings/llm-models", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await readApiError(response);
    throw new Error(error.message);
  }
  const body = (await response.json()) as { models?: string[]; apiBase?: string };
  return {
    models: Array.isArray(body.models) ? body.models.filter(Boolean) : [],
    apiBase: body.apiBase ?? "",
  };
}

export async function fetchGoogleDriveAuthUrl(): Promise<string> {
  const response = await authenticatedFetch("/api/v1/auth/google-drive/url");
  if (!response.ok) {
    const error = await readApiError(response);
    throw new Error(error.message);
  }

  const body = (await response.json()) as { auth_url?: string };
  if (!body.auth_url) {
    throw new Error("Google Drive auth URL was not returned.");
  }
  return body.auth_url;
}

export async function disconnectGoogleDrive(): Promise<void> {
  const response = await authenticatedFetch("/api/v1/auth/google-drive", {
    method: "DELETE",
  });
  if (!response.ok) {
    const error = await readApiError(response);
    throw new Error(error.message);
  }
}
