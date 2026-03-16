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

function mergeHeaders(initHeaders: HeadersInit | undefined, authHeader: string) {
  const headers = new Headers(initHeaders);
  headers.set("Authorization", authHeader);
  return headers;
}

async function getAuthHeader(forceRefresh = false) {
  const user = auth.currentUser;
  if (!user) {
    throw new Error("You must sign in before starting or opening a session.");
  }

  const token = await user.getIdToken(forceRefresh);
  return `Bearer ${token}`;
}

function isNonReplayableBody(body: BodyInit | null | undefined): boolean {
  return (
    typeof ReadableStream !== "undefined" && body instanceof ReadableStream
  );
}

export async function authenticatedFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const perform = async (forceRefresh = false) => {
    const authHeader = await getAuthHeader(forceRefresh);
    return fetch(`${API_BASE}${path}`, {
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
