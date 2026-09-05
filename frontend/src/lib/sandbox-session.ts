/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

export type TerminalSessionState = {
  command: string;
  cwd: string;
  stdout: string;
  stderr: string;
  exitCode: number | null;
  running: boolean;
  ts: number;
};

export type EditorSessionState = {
  path: string;
  action: "write" | "read" | "list";
  content: string;
  append: boolean;
  bytesWritten: number | null;
  running: boolean;
  ts: number;
};

export type AppPreviewState = {
  url: string;
  port: number | null;
  title: string;
  workspacePath: string;
  expired: boolean;
  ts: number;
};

export function parseAppPreviewPayload(
  payload: {
    url?: unknown;
    port?: unknown;
    title?: unknown;
    workspace_path?: unknown;
    [key: string]: unknown;
  },
  ts = Date.now(),
): AppPreviewState | null {
  const url = typeof payload.url === "string" ? payload.url.trim() : "";
  if (!url) return null;
  const rawPort = payload.port;
  const port =
    typeof rawPort === "number" && Number.isFinite(rawPort)
      ? rawPort
      : typeof rawPort === "string" && rawPort.trim()
        ? Number(rawPort)
        : null;
  return {
    url,
    port: port && port > 0 && port <= 65535 ? port : null,
    title:
      typeof payload.title === "string" && payload.title.trim()
        ? payload.title.trim()
        : "App preview",
    workspacePath:
      typeof payload.workspace_path === "string" ? payload.workspace_path : "",
    expired: false,
    ts,
  };
}

export function languageFromPath(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase() || "";
  const map: Record<string, string> = {
    py: "python",
    ts: "typescript",
    tsx: "tsx",
    js: "javascript",
    jsx: "jsx",
    json: "json",
    md: "markdown",
    html: "html",
    css: "css",
    sh: "bash",
    bash: "bash",
    yml: "yaml",
    yaml: "yaml",
    go: "go",
    rs: "rust",
    toml: "toml",
  };
  return map[ext] || "text";
}

export function fileNameFromPath(path: string): string {
  const parts = path.replace(/\\/g, "/").split("/");
  return parts[parts.length - 1] || path || "untitled";
}
