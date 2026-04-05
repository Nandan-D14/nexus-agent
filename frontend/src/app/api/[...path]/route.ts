import { NextRequest, NextResponse } from "next/server";

const AGENT_URL = process.env.AGENT_URL || "http://localhost:8000";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function resolveBackendPath(path: string[]): string {
  if (path[0] === "api" && path[1] === "v1") {
    return `/${path.join("/")}`;
  }
  if (path[0] === "v1") {
    return `/api/${path.join("/")}`;
  }
  return `/${path.join("/")}`;
}

async function handler(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const backendPath = resolveBackendPath(path);
  const target = `${AGENT_URL}${backendPath}${request.nextUrl.search}`;

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.set("accept", "application/json");

  const init: RequestInit & { duplex?: string } = {
    method: request.method,
    headers,
    cache: "no-store",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = request.body;
    init.duplex = "half";
  }

  try {
    const backendRes = await fetch(target, init);

    const responseHeaders = new Headers(backendRes.headers);
    responseHeaders.delete("transfer-encoding");

    return new NextResponse(backendRes.body, {
      status: backendRes.status,
      statusText: backendRes.statusText,
      headers: new Headers({
        ...Object.fromEntries(responseHeaders.entries()),
        "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
        Pragma: "no-cache",
        Expires: "0",
      }),
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
