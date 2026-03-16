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
