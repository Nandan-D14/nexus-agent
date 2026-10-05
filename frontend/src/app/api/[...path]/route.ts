/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import { NextRequest, NextResponse } from "next/server";

const AGENT_URL = process.env.AGENT_URL || "http://localhost:8000";

export const dynamic = "force-dynamic";
export const revalidate = 0;

// Request headers the backend needs. Everything else (cookies, hop-by-hop
// headers, client-supplied X-Forwarded-*) is dropped so browsers cannot
// smuggle values the backend trusts.
const FORWARDED_REQUEST_HEADERS = [
  "accept",
  "accept-language",
  "authorization",
  "content-type",
  "if-none-match",
  "range",
  "user-agent",
  "x-request-id",
];

// fetch() already decoded the body and owns framing; forwarding these would
// make the browser decode a second time or truncate the stream.
const DROPPED_RESPONSE_HEADERS = [
  "content-encoding",
  "content-length",
  "transfer-encoding",
  "connection",
  "keep-alive",
];

function resolveBackendPath(path: string[]): string | null {
  // Next decodes segments, so "..", "%2e%2e" or an encoded "/" would let the
  // URL normalise onto a different backend route.
  if (path.some((segment) => segment === "." || segment === ".." || /[\\/]/.test(segment))) {
    return null;
  }
  let resolved: string;
  if (path[0] === "api" && path[1] === "v1") {
    resolved = `/${path.join("/")}`;
  } else if (path[0] === "v1") {
    resolved = `/api/${path.join("/")}`;
  } else {
    resolved = `/${path.join("/")}`;
  }
  // Worker/scheduler endpoints are for Cloud Tasks only, never the browser.
  if (resolved === "/internal" || resolved.startsWith("/internal/")) return null;
  return resolved;
}

/** Client IP as seen by the platform: the right-most X-Forwarded-For entry. */
function clientIp(request: NextRequest): string | null {
  const forwarded = request.headers.get("x-forwarded-for");
  if (!forwarded) return null;
  const parts = forwarded.split(",").map((part) => part.trim()).filter(Boolean);
  return parts.length ? parts[parts.length - 1] : null;
}

async function handler(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const backendPath = resolveBackendPath(path);
  if (!backendPath) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }
  const target = `${AGENT_URL}${backendPath}${request.nextUrl.search}`;

  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  if (!headers.has("accept")) {
    headers.set("accept", "*/*");
  }
  const ip = clientIp(request);
  if (ip) {
    // Replaces any client-supplied chain; the backend rate-limits on this.
    headers.set("x-forwarded-for", ip);
  }

  const init: RequestInit & { duplex?: string } = {
    method: request.method,
    headers,
    cache: "no-store",
    redirect: "manual",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = request.body;
    init.duplex = "half";
  }

  try {
    const backendRes = await fetch(target, init);

    const responseHeaders = new Headers(backendRes.headers);
    for (const name of DROPPED_RESPONSE_HEADERS) {
      responseHeaders.delete(name);
    }
    responseHeaders.set("Cache-Control", "no-store, no-cache, must-revalidate, proxy-revalidate");
    responseHeaders.set("Pragma", "no-cache");
    responseHeaders.set("Expires", "0");

    return new NextResponse(backendRes.body, {
      status: backendRes.status,
      statusText: backendRes.statusText,
      headers: responseHeaders,
    });
  } catch {
    return NextResponse.json(
      { detail: "Backend unavailable" },
      { status: 502 }
    );
  }
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const DELETE = handler;
export const PATCH = handler;
