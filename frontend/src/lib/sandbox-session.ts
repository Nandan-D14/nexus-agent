/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
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
