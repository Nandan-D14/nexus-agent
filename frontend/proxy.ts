import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const AGENT_URL = process.env.AGENT_URL || "http://localhost:8000";

function resolveBackendPath(pathname: string): string {
  const backendPath = pathname.replace(/^\/api/, "");
  if (backendPath.startsWith("/api/v1/")) {
    return backendPath;
  }
  if (backendPath.startsWith("/v1/")) {
    return `/api${backendPath}`;
  }
  return backendPath;
}

export function proxy(request: NextRequest) {
  const url = request.nextUrl;

  // Proxy /api/* requests to the Python backend
  if (url.pathname.startsWith("/api/")) {
    const backendPath = resolveBackendPath(url.pathname);
    const target = `${AGENT_URL}${backendPath}${url.search}`;
    return NextResponse.rewrite(new URL(target));
  }

  return NextResponse.next();
}

export const config = {
  matcher: "/api/:path*",
};
