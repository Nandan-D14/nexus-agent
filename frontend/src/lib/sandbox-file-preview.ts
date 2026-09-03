/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

/** Max bytes the Files tab will load into the editor (matches the backend helper). */
export const TEXT_PREVIEW_MAX_BYTES = 2 * 1024 * 1024;

const TEXT_PREVIEW_EXTENSIONS = new Set([
  "py",
  "ts",
  "tsx",
  "js",
  "jsx",
  "mjs",
  "cjs",
  "json",
  "md",
  "mdx",
  "html",
  "htm",
  "css",
  "scss",
  "sass",
  "less",
  "sh",
  "bash",
  "zsh",
  "yml",
  "yaml",
  "toml",
  "ini",
  "cfg",
  "conf",
  "txt",
  "xml",
  "svg",
  "csv",
  "sql",
  "go",
  "rs",
  "java",
  "kt",
  "rb",
  "php",
  "c",
  "h",
  "cpp",
  "hpp",
  "cs",
  "swift",
  "vue",
  "svelte",
  "graphql",
  "prisma",
]);

const TEXT_PREVIEW_BASENAMES = new Set([
  "dockerfile",
  "makefile",
  "readme",
  "license",
  "procfile",
  "gemfile",
  "rakefile",
]);

export function isPreviewableTextFile(name: string, size?: number | null): boolean {
  if (typeof size === "number" && (size < 0 || size > TEXT_PREVIEW_MAX_BYTES)) {
    return false;
  }
  const base = name.replace(/\\/g, "/").split("/").pop()?.trim() || "";
  if (!base) return false;
  const lowered = base.toLowerCase();
  if (TEXT_PREVIEW_BASENAMES.has(lowered)) return true;
  if (base.startsWith(".") && !base.slice(1).includes(".")) return true;
  const dot = base.lastIndexOf(".");
  if (dot <= 0) return false;
  return TEXT_PREVIEW_EXTENSIONS.has(base.slice(dot + 1).toLowerCase());
}
