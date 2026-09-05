/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

/**
 * Resolve durable artifact URLs through the authenticated download API
 * so the UI never relies on expired WebSocket signed URLs.
 */

import type { RunArtifact } from "@/lib/message-types";
import { authenticatedFetch } from "@/lib/api-client";

const DOWNLOAD_TIMEOUT_MS = 8000;
const CONTENT_TIMEOUT_MS = 20000;
const SANDBOX_TIMEOUT_MS = 45000;

export function isPdfArtifact(artifact: Pick<RunArtifact, "kind" | "metadata">): boolean {
  if (artifact.kind === "pdf" || artifact.kind === "pdf_report") return true;
  const contentType = String(artifact.metadata?.content_type ?? "").toLowerCase();
  return contentType.includes("pdf");
}

const SOURCE_KINDS = new Set([
  "summary",
  "screenshot_reference",
  "export_reference",
  "workspace_output",
]);

const SOURCE_TOOLS = new Set(["scrape_web_page", "web_search", "tavily_search"]);

/**
 * Source/working artifacts (search dumps, scrapes, screenshots, agent summaries).
 * These belong in the Sources panel section — never as chat cards.
 * Heuristic also covers older artifacts minted before `metadata.role` existed.
 */
export function isSourceArtifact(artifact: Pick<RunArtifact, "kind" | "path" | "metadata">): boolean {
  const tool = artifact.metadata?.tool;
  if (typeof tool === "string" && SOURCE_TOOLS.has(tool)) return true;
  const role = artifact.metadata?.role;
  if (role === "source") return true;
  if (role === "deliverable") return false;
  if (SOURCE_KINDS.has(artifact.kind)) return true;
  const path = (artifact.path || "").replace(/\\/g, "/");
  if (path.startsWith("sources/")) return true;
  return false;
}

export function isDeliverableArtifact(
  artifact: Pick<RunArtifact, "kind" | "path" | "metadata">,
): boolean {
  return !isSourceArtifact(artifact);
}

export function isHtmlArtifact(
  artifact: Pick<RunArtifact, "kind" | "metadata" | "path" | "title">,
): boolean {
  if (artifact.kind === "html") return true;
  if (
    artifact.kind === "presentation" ||
    artifact.kind === "document" ||
    artifact.kind === "spreadsheet"
  ) {
    return false;
  }
  const path = (artifact.path || artifact.title || "").replace(/\\/g, "/").toLowerCase();
  if (/\.(pptx|ppt|docx|doc|xlsx|xls)$/.test(path)) return false;
  return artifact.metadata?.render_mode === "iframe";
}

export function isOfficeArtifact(artifact: Pick<RunArtifact, "kind" | "metadata">): boolean {
  if (
    artifact.kind === "document" ||
    artifact.kind === "spreadsheet" ||
    artifact.kind === "presentation"
  ) {
    return true;
  }
  const contentType = String(artifact.metadata?.content_type ?? "").toLowerCase();
  return (
    contentType.includes("wordprocessingml") ||
    contentType.includes("spreadsheetml") ||
    contentType.includes("presentationml") ||
    contentType.includes("msword") ||
    contentType.includes("ms-excel") ||
    contentType.includes("ms-powerpoint") ||
    contentType.includes("officedocument")
  );
}

const SHEET_EXT = /\.(xlsx|xlsm|xls|csv)$/i;
const CSV_EXT = /\.csv$/i;
const MARKDOWN_EXT = /\.(md|markdown)$/i;
const TEXT_EXT = /\.txt$/i;
const PPT_EXT = /\.(pptx|ppt)$/i;
const CODE_EXT =
  /\.(py|pyw|ts|tsx|js|jsx|mjs|cjs|json|css|scss|less|go|rs|java|kt|kts|swift|rb|php|c|cc|cpp|cxx|h|hpp|cs|sql|sh|bash|zsh|yml|yaml|toml|xml|graphql|gql|vue|svelte|r|lua|pl|ex|exs|erl|hs|scala|dart|proto|tf|ini|cfg|conf|env|dockerignore|gitignore|makefile|mk|cmake|gradle|ipynb)$/i;

const CODE_LANG_BY_EXT: Record<string, string> = {
  py: "python",
  pyw: "python",
  ts: "typescript",
  tsx: "tsx",
  js: "javascript",
  jsx: "jsx",
  mjs: "javascript",
  cjs: "javascript",
  json: "json",
  css: "css",
  scss: "scss",
  go: "go",
  rs: "rust",
  java: "java",
  kt: "kotlin",
  rb: "ruby",
  php: "php",
  c: "c",
  cpp: "cpp",
  h: "c",
  cs: "csharp",
  sql: "sql",
  sh: "bash",
  bash: "bash",
  yml: "yaml",
  yaml: "yaml",
  toml: "toml",
  xml: "xml",
  vue: "javascript",
  r: "r",
};

function artifactFileName(
  artifact: Pick<RunArtifact, "path" | "title">,
): string {
  const path = (artifact.path || "").replace(/\\/g, "/");
  return `${path.split("/").pop() || ""} ${artifact.title || ""}`;
}

export function isCsvArtifact(
  artifact: Pick<RunArtifact, "kind" | "metadata" | "path" | "title">,
): boolean {
  if (artifact.kind === "csv") return true;
  const name = artifactFileName(artifact);
  if (CSV_EXT.test(artifact.path || "") || CSV_EXT.test(name)) return true;
  const contentType = String(artifact.metadata?.content_type ?? "").toLowerCase();
  return (
    contentType === "text/csv" ||
    contentType === "application/csv" ||
    contentType.startsWith("text/csv")
  );
}

export function isSpreadsheetArtifact(
  artifact: Pick<RunArtifact, "kind" | "metadata" | "path" | "title">,
): boolean {
  if (artifact.kind === "spreadsheet" || artifact.kind === "csv") return true;
  const path = (artifact.path || "").replace(/\\/g, "/");
  const name = artifactFileName(artifact);
  if (SHEET_EXT.test(path) || SHEET_EXT.test(name)) return true;
  const contentType = String(artifact.metadata?.content_type ?? "").toLowerCase();
  return (
    contentType.includes("spreadsheetml") ||
    contentType.includes("ms-excel") ||
    contentType === "text/csv" ||
    contentType === "application/csv" ||
    contentType.startsWith("text/csv")
  );
}

export function isPresentationArtifact(
  artifact: Pick<RunArtifact, "kind" | "metadata" | "path" | "title">,
): boolean {
  if (artifact.kind === "presentation") return true;
  const name = artifactFileName(artifact);
  if (PPT_EXT.test(artifact.path || "") || PPT_EXT.test(name)) return true;
  const contentType = String(artifact.metadata?.content_type ?? "").toLowerCase();
  return contentType.includes("presentationml") || contentType.includes("ms-powerpoint");
}

export function isMarkdownArtifact(
  artifact: Pick<RunArtifact, "kind" | "metadata" | "path" | "title">,
): boolean {
  if (artifact.kind === "markdown") return true;
  const name = artifactFileName(artifact);
  if (MARKDOWN_EXT.test(artifact.path || "") || MARKDOWN_EXT.test(name)) return true;
  const contentType = String(artifact.metadata?.content_type ?? "").toLowerCase();
  return contentType.includes("markdown");
}

export function isPlainTextArtifact(
  artifact: Pick<RunArtifact, "kind" | "metadata" | "path" | "title">,
): boolean {
  const name = artifactFileName(artifact);
  if (TEXT_EXT.test(artifact.path || "") || TEXT_EXT.test(name)) return true;
  const contentType = String(artifact.metadata?.content_type ?? "").toLowerCase();
  return contentType === "text/plain" || contentType.startsWith("text/plain");
}

export function fileExtension(
  artifact: Pick<RunArtifact, "path" | "title">,
): string {
  const name = (
    (artifact.path || "").replace(/\\/g, "/").split("/").pop() ||
    artifact.title ||
    ""
  ).toLowerCase();
  const match = /\.([a-z0-9]+)$/i.exec(name);
  return match ? match[1].toLowerCase() : "";
}

export function isCodeArtifact(
  artifact: Pick<RunArtifact, "kind" | "metadata" | "path" | "title">,
): boolean {
  if (isMarkdownArtifact(artifact) || isHtmlArtifact(artifact) || isPlainTextArtifact(artifact)) {
    return false;
  }
  const path = (artifact.path || "").replace(/\\/g, "/");
  const name = artifactFileName(artifact);
  if (CODE_EXT.test(path) || CODE_EXT.test(name)) return true;
  const contentType = String(artifact.metadata?.content_type ?? "").toLowerCase();
  return (
    contentType.includes("javascript") ||
    contentType.includes("typescript") ||
    contentType.includes("json") ||
    contentType.includes("x-python") ||
    contentType.includes("x-sh")
  );
}

export function isCodePath(path: string): boolean {
  return CODE_EXT.test(path.replace(/\\/g, "/"));
}

export function isMarkdownPath(path: string): boolean {
  return MARKDOWN_EXT.test(path.replace(/\\/g, "/"));
}

export function codeLanguageForPath(path: string): string {
  const name = path.replace(/\\/g, "/").split("/").pop() || path;
  const ext = fileExtension({ path: name, title: name });
  return CODE_LANG_BY_EXT[ext] || ext || "text";
}

export function codeLanguageForArtifact(
  artifact: Pick<RunArtifact, "path" | "title">,
): string {
  return codeLanguageForPath(artifact.path || artifact.title || "");
}

function officeSiblingPreviewKind(
  artifact: Pick<RunArtifact, "metadata">,
): "html" | "pdf" | "none" {
  const previewUrl = artifact.metadata?.preview_url;
  const previewPath = String(artifact.metadata?.preview_path ?? "").toLowerCase();
  const hasSibling =
    (typeof previewUrl === "string" && previewUrl.length > 0) || previewPath.length > 0;
  if (!hasSibling) return "none";
  const previewType = String(artifact.metadata?.preview_content_type ?? "").toLowerCase();
  if (
    artifact.metadata?.render_mode === "iframe" ||
    previewType.includes("html") ||
    previewPath.endsWith(".html") ||
    previewPath.endsWith(".htm")
  ) {
    return "html";
  }
  return "pdf";
}

/** How an artifact renders inside the document viewer. */
export type PreviewKind = "pdf" | "image" | "html" | "sheet" | "markdown" | "code" | "none";

type PreviewArtifact = Pick<RunArtifact, "kind" | "metadata" | "path" | "title">;

/**
 * Single source of truth for viewer rendering, card thumbnails, and previewability.
 * Spreadsheets parse in-browser. Office files otherwise use an HTML or PDF sibling
 * fetched same-origin (never a GCS URL). Markdown renders. Source files use a code view.
 */
export function previewKind(artifact: PreviewArtifact): PreviewKind {
  if (artifact.kind === "image" || artifact.kind === "screenshot") return "image";
  if (isPdfArtifact(artifact)) return "pdf";
  if (isSpreadsheetArtifact(artifact)) return "sheet";
  if (isMarkdownArtifact(artifact) || isPlainTextArtifact(artifact)) return "markdown";
  if (isPresentationArtifact(artifact) || isOfficeArtifact(artifact)) {
    const sibling = officeSiblingPreviewKind(artifact);
    if (sibling !== "none") return sibling;
  }
  if (isHtmlArtifact(artifact)) return "html";
  if (isCodeArtifact(artifact)) return "code";
  return "none";
}

export function canInlinePreview(artifact: PreviewArtifact): boolean {
  return previewKind(artifact) !== "none";
}

export function getPreviewUrl(artifact: RunArtifact): string | null {
  if (isOfficeArtifact(artifact) && !isPdfArtifact(artifact) && !isSpreadsheetArtifact(artifact)) {
    const previewUrl = artifact.metadata?.preview_url;
    if (typeof previewUrl === "string" && previewUrl) {
      return durableInlineUrl(previewUrl);
    }
  }
  return durableInlineUrl(artifact.url);
}

function dataURItoBlob(dataURI: string): Blob {
  const parts = dataURI.split(",");
  if (parts.length < 2) {
    throw new Error("Invalid Data URI");
  }
  const byteString = atob(parts[1]);
  const mimeMatch = parts[0].match(/:(.*?);/);
  const mimeString = mimeMatch ? mimeMatch[1] : "application/octet-stream";

  const ab = new ArrayBuffer(byteString.length);
  const ia = new Uint8Array(ab);
  for (let i = 0; i < byteString.length; i++) {
    ia[i] = byteString.charCodeAt(i);
  }
  return new Blob([ab], { type: mimeString });
}

async function fetchWithTimeout(
  path: string,
  timeoutMs: number,
): Promise<Response | null> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await authenticatedFetch(path, { signal: controller.signal });
  } catch {
    return null;
  } finally {
    clearTimeout(timeoutId);
  }
}

async function fetchArtifactContentBlobUrl(
  artifact: RunArtifact,
  options?: { sibling?: "preview" },
): Promise<string | null> {
  const params = new URLSearchParams();
  if (artifact.session_id) params.set("session_id", artifact.session_id);
  if (artifact.run_id) params.set("run_id", artifact.run_id);
  if (options?.sibling) params.set("sibling", options.sibling);
  const query = params.toString();
  const res = await fetchWithTimeout(
    `/api/v1/artifacts/${encodeURIComponent(artifact.artifact_id)}/content${query ? `?${query}` : ""}`,
    CONTENT_TIMEOUT_MS,
  );
  if (!res?.ok) return null;
  try {
    const raw = await res.blob();
    if (!raw.size) return null;
    const mime =
      options?.sibling === "preview"
        ? siblingPreviewMime(artifact, raw.type)
        : blobMimeForArtifact(artifact, raw.type);
    const blob = mime && raw.type !== mime ? new Blob([raw], { type: mime }) : raw;
    return URL.createObjectURL(blob);
  } catch {
    return null;
  }
}

function siblingPreviewMime(
  artifact: Pick<RunArtifact, "metadata">,
  fallback: string,
): string {
  const declared = String(artifact.metadata?.preview_content_type ?? "").split(";")[0].trim();
  if (declared) return declared;
  const path = String(artifact.metadata?.preview_path ?? "").toLowerCase();
  if (path.endsWith(".html") || path.endsWith(".htm")) return "text/html;charset=utf-8";
  if (path.endsWith(".pdf")) return "application/pdf";
  if (fallback && fallback !== "application/octet-stream") return fallback;
  return "text/html;charset=utf-8";
}

function hasOfficePreviewSibling(
  artifact: Pick<RunArtifact, "kind" | "metadata" | "path" | "title">,
): boolean {
  if (isSpreadsheetArtifact(artifact) || isPdfArtifact(artifact)) return false;
  if (!isOfficeArtifact(artifact) && !isPresentationArtifact(artifact)) return false;
  const previewUrl = artifact.metadata?.preview_url;
  const previewPath = artifact.metadata?.preview_path;
  return (
    (typeof previewUrl === "string" && previewUrl.length > 0) ||
    (typeof previewPath === "string" && previewPath.length > 0)
  );
}

function blobMimeForArtifact(
  artifact: Pick<RunArtifact, "kind" | "metadata" | "path" | "title">,
  fallback: string,
): string {
  const declared = String(artifact.metadata?.content_type ?? "").split(";")[0].trim();
  if (declared) return declared;
  if (isPdfArtifact(artifact)) return "application/pdf";
  if (isCsvArtifact(artifact)) return "text/csv";
  if (isSpreadsheetArtifact(artifact)) {
    return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  }
  if (isPresentationArtifact(artifact)) {
    return "application/vnd.openxmlformats-officedocument.presentationml.presentation";
  }
  if (isMarkdownArtifact(artifact)) return "text/markdown;charset=utf-8";
  if (isPlainTextArtifact(artifact) || isCodeArtifact(artifact)) {
    return "text/plain;charset=utf-8";
  }
  if (fallback && fallback !== "application/octet-stream") return fallback;
  return fallback || "application/octet-stream";
}

function isGcsUrl(url: string | null | undefined): boolean {
  return Boolean(url && url.includes("storage.googleapis.com"));
}

/**
 * Ask the backend for a fresh signed / data URI URL for an artifact.
 */
export async function fetchFreshArtifactUrl(artifactId: string, artifact?: RunArtifact): Promise<string | null> {
  const params = new URLSearchParams();
  if (artifact?.session_id) params.set("session_id", artifact.session_id);
  if (artifact?.run_id) params.set("run_id", artifact.run_id);
  const query = params.toString();
  const res = await fetchWithTimeout(
    `/api/v1/artifacts/${encodeURIComponent(artifactId)}/download${query ? `?${query}` : ""}`,
    DOWNLOAD_TIMEOUT_MS,
  );
  if (!res?.ok) return null;
  try {
    const body = (await res.json()) as { url?: string };
    return body.url ?? null;
  } catch {
    return null;
  }
}

async function downloadFromWorkspaceSandbox(
  sessionId: string,
  path: string,
  runId?: string | null,
): Promise<string | null> {
  let relative = path.includes("/Workspaces/")
    ? path.split("/Workspaces/").pop() || path
    : path.replace(/^\/home\/user\/CoComputer\/Workspaces\/?/, "");
  relative = relative.replace(/^\/+/, "");
  // Drop a leading sessionId[/runId] prefix so the backend joins onto the
  // run workspace instead of nesting those ids a second time.
  const sessionPrefix = `${sessionId}/`;
  if (relative.startsWith(sessionPrefix)) {
    relative = relative.slice(sessionPrefix.length);
  }
  if (runId && relative.startsWith(`${runId}/`)) {
    relative = relative.slice(runId.length + 1);
  }

  const params = new URLSearchParams({ relative_path: relative });
  if (runId) params.set("run_id", runId);
  const res = await fetchWithTimeout(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}/files/download?${params.toString()}`,
    SANDBOX_TIMEOUT_MS,
  );
  if (!res?.ok) return null;
  try {
    const raw = await res.blob();
    if (!raw.size) return null;
    const mime = mimeFromFilename(relative, raw.type);
    const blob = mime && raw.type !== mime ? new Blob([raw], { type: mime }) : raw;
    return URL.createObjectURL(blob);
  } catch {
    return null;
  }
}

function mimeFromFilename(path: string, fallback: string): string {
  const name = path.replace(/\\/g, "/").split("/").pop() || "";
  const ext = name.includes(".") ? name.split(".").pop()!.toLowerCase() : "";
  const map: Record<string, string> = {
    html: "text/html;charset=utf-8",
    htm: "text/html;charset=utf-8",
    pdf: "application/pdf",
    md: "text/markdown;charset=utf-8",
    markdown: "text/markdown;charset=utf-8",
    txt: "text/plain;charset=utf-8",
    csv: "text/csv",
    json: "application/json",
    png: "image/png",
    jpg: "image/jpeg",
    jpeg: "image/jpeg",
    pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  };
  if (map[ext]) return map[ext];
  if (fallback && fallback !== "application/octet-stream") return fallback;
  return fallback || "application/octet-stream";
}

function toBlobUrlIfDataUri(url: string): string {
  if (!url.startsWith("data:")) return url;
  try {
    return URL.createObjectURL(dataURItoBlob(url));
  } catch {
    return url;
  }
}

export type ResolveArtifactOptions = {
  /** Prefer the PDF preview sibling for Office artifacts. */
  forPreview?: boolean;
  /**
   * Fall back to the live session sandbox. Library and other historical
   * views must leave this off — those sandboxes are gone and the API 400s.
   */
  allowSandbox?: boolean;
};

function normalizeResolveOptions(
  forPreviewOrOptions: boolean | ResolveArtifactOptions = false,
): Required<ResolveArtifactOptions> {
  if (typeof forPreviewOrOptions === "boolean") {
    return { forPreview: forPreviewOrOptions, allowSandbox: true };
  }
  return {
    forPreview: forPreviewOrOptions.forPreview ?? false,
    allowSandbox: forPreviewOrOptions.allowSandbox ?? true,
  };
}

/** URLs that can be used in <img>/<iframe> without a refresh round-trip. */
export function durableInlineUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  if (url.includes("storage.googleapis.com")) return null;
  if (url.startsWith("data:") || url.startsWith("blob:") || url.startsWith("http")) {
    return url;
  }
  return null;
}

function usableInlineSrc(url: string | null | undefined): string | null {
  if (!url) return null;
  if (isGcsUrl(url)) return null;
  if (url.startsWith("data:")) return toBlobUrlIfDataUri(url);
  if (url.startsWith("blob:") || url.startsWith("http")) return url;
  return null;
}

/** Same-origin, blob, or data URLs that can be used in an iframe/object/img. */
export function usablePreviewSrc(url: string | null | undefined): string | null {
  return usableInlineSrc(url);
}

/**
 * Resolve a working preview/download URL.
 * Prefer the authenticated download API for GCS-backed artifacts.
 * @param forPreviewOrOptions - `true` for preview, or `{ forPreview, allowSandbox }`
 */
export async function resolveArtifactUrl(
  artifact: RunArtifact,
  forPreviewOrOptions: boolean | ResolveArtifactOptions = false,
): Promise<string | null> {
  const { forPreview, allowSandbox } = normalizeResolveOptions(forPreviewOrOptions);

  if (forPreview && hasOfficePreviewSibling(artifact)) {
    const sibling = await fetchArtifactContentBlobUrl(artifact, { sibling: "preview" });
    if (sibling) return sibling;
    const previewPath = String(artifact.metadata?.preview_path || "").trim();
    if (allowSandbox && previewPath && artifact.session_id) {
      const sandboxPreview = await downloadFromWorkspaceSandbox(
        artifact.session_id,
        previewPath,
        artifact.run_id,
      );
      if (sandboxPreview) return sandboxPreview;
    }
  }

  if (
    artifact.url &&
    !isGcsUrl(artifact.url) &&
    !artifact.url.startsWith("data:")
  ) {
    const src = usableInlineSrc(artifact.url);
    if (src && !forPreview) return src;
    if (src && forPreview && !hasOfficePreviewSibling(artifact)) return src;
  }

  if (artifact.url?.startsWith("data:")) {
    return toBlobUrlIfDataUri(artifact.url);
  }

  const contentUrl = await fetchArtifactContentBlobUrl(artifact);
  if (contentUrl) return contentUrl;

  const fresh = await fetchFreshArtifactUrl(artifact.artifact_id, artifact);
  if (fresh && !isGcsUrl(fresh)) {
    return toBlobUrlIfDataUri(fresh);
  }

  if (allowSandbox && artifact.path && artifact.session_id) {
    const sandboxUrl = await downloadFromWorkspaceSandbox(
      artifact.session_id,
      artifact.path,
      artifact.run_id,
    );
    if (sandboxUrl) return sandboxUrl;
  }

  // A GCS URL cannot be fetched from the browser (CORS) or shown in an
  // <object>/<iframe>. Returning it made the preview look like a generic
  // load failure. Prefer nothing so the UI can show a download action.
  return usableInlineSrc(artifact.url);
}

export function downloadFilename(artifact: Pick<RunArtifact, "title" | "path" | "artifact_id">): string {
  const fromPath = (artifact.path || "").replace(/\\/g, "/").split("/").pop();
  if (fromPath && fromPath.includes(".")) return fromPath;
  const title = (artifact.title || "").trim();
  if (title && /\.[A-Za-z0-9]+$/.test(title)) return title;
  return title || `artifact-${artifact.artifact_id.slice(0, 8)}`;
}

export function triggerBlobDownload(url: string, filename: string): void {
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

export function downloadTextFile(filename: string, content: string, mime = "text/plain;charset=utf-8"): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  triggerBlobDownload(url, filename);
  URL.revokeObjectURL(url);
}

/**
 * Trigger a browser download for an artifact (blob preferred).
 */
export async function downloadArtifactFile(
  artifact: RunArtifact,
  options?: ResolveArtifactOptions,
): Promise<boolean> {
  const url = await resolveArtifactUrl(artifact, {
    forPreview: false,
    allowSandbox: options?.allowSandbox ?? true,
  });
  if (!url) return false;

  const filename = downloadFilename(artifact);

  if (url.startsWith("blob:") || url.startsWith("data:")) {
    triggerBlobDownload(url, filename);
    return true;
  }

  try {
    const res = await fetch(url);
    if (res.ok) {
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      triggerBlobDownload(blobUrl, filename);
      URL.revokeObjectURL(blobUrl);
      return true;
    }
  } catch {
    // fall through to open-in-tab
  }

  window.open(url, "_blank", "noopener,noreferrer");
  return true;
}

/** Tools that produce downloadable document artifacts. */
export const DOC_ARTIFACT_TOOLS = new Set([
  "generate_pdf_report",
  "generate_docx_report",
  "generate_excel_report",
  "generate_pptx_report",
  "save_as_artifact",
  "publish_html_artifact",
]);

/**
 * Best-effort parse of a docs-tool result JSON into a RunArtifact-like object.
 */
export function artifactFromToolResult(
  tool: string,
  output: string | undefined,
  fallbacks?: { sessionId?: string; runId?: string },
): RunArtifact | null {
  if (!output || !DOC_ARTIFACT_TOOLS.has(tool)) return null;
  try {
    const parsed = JSON.parse(output) as Record<string, unknown>;
    if (parsed.status === "error") return null;
    const detail =
      parsed.detail && typeof parsed.detail === "object"
        ? (parsed.detail as Record<string, unknown>)
        : parsed;
    const artifactId =
      (typeof detail.artifact_id === "string" && detail.artifact_id) ||
      (typeof parsed.artifact_id === "string" && parsed.artifact_id) ||
      null;
    if (!artifactId) return null;

    const kind =
      tool === "generate_pdf_report"
        ? "pdf_report"
        : tool === "generate_docx_report"
          ? "document"
          : tool === "generate_excel_report"
            ? "spreadsheet"
            : tool === "generate_pptx_report"
              ? "presentation"
              : tool === "publish_html_artifact"
                ? "html"
                : "file";

    const previewUrl =
      typeof detail.preview_url === "string" && detail.preview_url
        ? detail.preview_url
        : undefined;

    return {
      artifact_id: artifactId,
      run_id: fallbacks?.runId || "",
      session_id: fallbacks?.sessionId || "",
      kind,
      title:
        (typeof detail.filename === "string" && detail.filename) ||
        (typeof parsed.summary === "string" && parsed.summary) ||
        tool,
      preview: typeof parsed.summary === "string" ? parsed.summary : "",
      created_at: new Date().toISOString(),
      path: typeof detail.path === "string" ? detail.path : null,
      url: typeof detail.url === "string" ? detail.url : null,
      metadata: {
        content_type:
          kind === "pdf_report"
            ? "application/pdf"
            : kind === "document"
              ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              : kind === "spreadsheet"
                ? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                : kind === "presentation"
                  ? "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                  : kind === "html"
                    ? "text/html"
                    : "application/octet-stream",
        ...(previewUrl
          ? {
              preview_url: previewUrl,
              ...(kind === "presentation"
                ? {
                    preview_content_type: "text/html; charset=utf-8",
                    render_mode: "iframe",
                  }
                : {}),
            }
          : {}),
      },
    };
  } catch {
    return null;
  }
}
