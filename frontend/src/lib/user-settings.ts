"use client";

import { authenticatedFetch, readApiError } from "./api-client";

export type GeminiProvider = "apiKey" | "vertex";

export type ByokSettings = {
  e2bKeySet: boolean;
  geminiKeySet: boolean;
  geminiProvider: GeminiProvider;
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
};

export type UserSettingsUpdatePayload = {
  settings?: Record<string, unknown>;
  byok?: {
    e2bApiKey?: string | null;
    geminiApiKey?: string | null;
    geminiProvider?: GeminiProvider;
    accessCode?: string | null;
  };
};

export function requiresByokSetup(data: UserSettingsResponse): boolean {
  return data.requireByok && data.byok.missing.length > 0;
}

export async function fetchUserSettings(): Promise<UserSettingsResponse> {
  const response = await authenticatedFetch("/api/v1/user/settings");
  if (!response.ok) {
    const error = await readApiError(response);
    throw new Error(error.message);
  }
  return (await response.json()) as UserSettingsResponse;
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

  return (await response.json()) as UserSettingsResponse;
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
