/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { auth } from "@/lib/firebase-client";

const API_BASE = "/api";

type JsonValue =
  | Record<string, unknown>
  | unknown[]
  | string
  | number
  | boolean
  | null;

export type ApiErrorData = {
  message: string;
  code?: string;
  missing?: string[];
};

const TOKEN_SKEW_MS = 60_000;

type CachedAuthToken = {
  uid: string;
  header: string;
  expMs: number;
};

let cachedAuthToken: CachedAuthToken | null = null;
let authHeaderInflight: Promise<string> | null = null;

function jwtExpMs(token: string): number | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const padded = payload.replace(/-/g, "+").replace(/_/g, "/");
    const pad = padded.length % 4 === 0 ? "" : "=".repeat(4 - (padded.length % 4));
    const parsed = JSON.parse(atob(`${padded}${pad}`)) as { exp?: unknown };
    return typeof parsed.exp === "number" ? parsed.exp * 1000 : null;
  } catch {
    return null;
  }
}

export function clearAuthTokenCache() {
  cachedAuthToken = null;
  authHeaderInflight = null;
}

function mergeHeaders(initHeaders: HeadersInit | undefined, authHeader: string) {
  const headers = new Headers(initHeaders);
  headers.set("Authorization", authHeader);
  return headers;
}

function cachedAuthHeader(uid: string): string | null {
  if (!cachedAuthToken || cachedAuthToken.uid !== uid) return null;
  if (Date.now() >= cachedAuthToken.expMs - TOKEN_SKEW_MS) return null;
  return cachedAuthToken.header;
}

async function fetchAndCacheAuthHeader(
  user: { uid: string; getIdToken: (forceRefresh?: boolean) => Promise<string> },
  forceRefresh: boolean,
): Promise<string> {
  const token = await user.getIdToken(forceRefresh);
  const header = `Bearer ${token}`;
  cachedAuthToken = {
    uid: user.uid,
    header,
    expMs: jwtExpMs(token) ?? Date.now() + 50 * 60 * 1000,
  };
  return header;
}

async function getAuthHeader(forceRefresh = false) {
  const user = auth.currentUser;
  if (!user) {
    clearAuthTokenCache();
    throw new Error("You must sign in before starting or opening a session.");
  }

  if (!forceRefresh) {
    const hit = cachedAuthHeader(user.uid);
    if (hit) return hit;
    if (authHeaderInflight) return authHeaderInflight;
    authHeaderInflight = fetchAndCacheAuthHeader(user, false).finally(() => {
      authHeaderInflight = null;
    });
    return authHeaderInflight;
  }

  authHeaderInflight = null;
  return fetchAndCacheAuthHeader(user, true);
}

function isNonReplayableBody(body: BodyInit | null | undefined): boolean {
  return (
    typeof ReadableStream !== "undefined" && body instanceof ReadableStream
  );
}

function resolveApiPath(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return normalizedPath.startsWith(`${API_BASE}/`)
    ? normalizedPath
    : `${API_BASE}${normalizedPath}`;
}

export async function authenticatedFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const perform = async (forceRefresh = false) => {
    const authHeader = await getAuthHeader(forceRefresh);
    return fetch(resolveApiPath(path), {
      ...init,
      headers: mergeHeaders(init?.headers, authHeader),
    });
  };

  let response = await perform(false);
  // Skip the 401-retry when the body is a non-replayable stream to avoid
  // sending an empty body on the second request.
  if (response.status === 401 && !isNonReplayableBody(init?.body)) {
    response = await perform(true);
  }

  return response;
}

export async function readApiError(response: Response): Promise<ApiErrorData> {
  const body = (await response.json().catch(() => null)) as JsonValue | null;
  const fallback: ApiErrorData = {
    message: `HTTP ${response.status}`,
  };

  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return fallback;
  }

  const record = body as Record<string, unknown>;
  const nestedDetail =
    record.detail && typeof record.detail === "object" && !Array.isArray(record.detail)
      ? (record.detail as Record<string, unknown>)
      : null;

  const message =
    (typeof record.detail === "string" && record.detail) ||
    (typeof record.message === "string" && record.message) ||
    (nestedDetail && typeof nestedDetail.message === "string" && nestedDetail.message) ||
    (nestedDetail && typeof nestedDetail.detail === "string" && nestedDetail.detail) ||
    fallback.message;

  const code =
    (typeof record.code === "string" && record.code) ||
    (nestedDetail && typeof nestedDetail.code === "string" && nestedDetail.code) ||
    undefined;

  const missing =
    (Array.isArray(record.missing)
      ? record.missing
      : nestedDetail && Array.isArray(nestedDetail.missing)
        ? nestedDetail.missing
        : [])
      .filter((value): value is string => typeof value === "string");

  return {
    message,
    code,
    missing: missing.length > 0 ? missing : undefined,
  };
}

export async function parseApiError(response: Response): Promise<string> {
  const error = await readApiError(response);
  return error.message;
}

export function getApiErrorCode(error: unknown): string | undefined {
  if (error && typeof error === "object" && "code" in error) {
    const code = (error as { code?: unknown }).code;
    return typeof code === "string" ? code : undefined;
  }
  return undefined;
}

/** Throw-on-error JSON helper for TanStack Query. Leaves authenticatedFetch unchanged. */
export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authenticatedFetch(path, init);
  if (!response.ok) {
    const apiError = await readApiError(response);
    const error = new Error(apiError.message);
    if (apiError.code) {
      (error as Error & { code?: string }).code = apiError.code;
    }
    throw error;
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  if (!text) {
    return undefined as T;
  }

  return JSON.parse(text) as T;
}
