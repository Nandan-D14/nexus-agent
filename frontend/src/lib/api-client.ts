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

export async function parseApiError(response: Response): Promise<string> {
  const body = (await response.json().catch(() => null)) as JsonValue | null;

  if (
    body &&
    typeof body === "object" &&
    !Array.isArray(body) &&
    "detail" in body
  ) {
    return String(body.detail);
  }

  return `HTTP ${response.status}`;
}
