/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

/**
 * Resolve durable artifact URLs through the authenticated download API
 * so the UI never relies on expired WebSocket signed URLs.
 */

import type { RunArtifact } from "@/lib/message-types";
import { authenticatedFetch } from "@/lib/api-client";

const DOWNLOAD_TIMEOUT_MS = 8000;
const SANDBOX_TIMEOUT_MS = 5000;

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

export function isHtmlArtifact(artifact: Pick<RunArtifact, "kind" | "metadata">): boolean {
  return artifact.kind === "html" || artifact.metadata?.render_mode === "iframe";
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

export function isSpreadsheetArtifact(
  artifact: Pick<RunArtifact, "kind" | "metadata" | "path" | "title">,
): boolean {
  if (artifact.kind === "spreadsheet" || artifact.kind === "csv") return true;
  const path = (artifact.path || "").replace(/\\/g, "/");
  const name = `${path.split("/").pop() || ""} ${artifact.title || ""}`;
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

function officeSiblingPreviewKind(
  artifact: Pick<RunArtifact, "metadata">,
): "html" | "pdf" | "none" {
  const previewUrl = artifact.metadata?.preview_url;
  if (typeof previewUrl !== "string" || !previewUrl) return "none";
  const previewType = String(artifact.metadata?.preview_content_type ?? "").toLowerCase();
  const previewPath = String(artifact.metadata?.preview_path ?? "").toLowerCase();
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
export type PreviewKind = "pdf" | "image" | "html" | "sheet" | "none";

type PreviewArtifact = Pick<RunArtifact, "kind" | "metadata" | "path" | "title">;

/**
 * Single source of truth for viewer rendering, card thumbnails, and previewability.
 * Spreadsheets parse in-browser. Office files otherwise use an HTML or PDF sibling
 * when `preview_url` is set; without one they fall back to download-only.
 */
export function previewKind(artifact: PreviewArtifact): PreviewKind {
  if (artifact.kind === "image" || artifact.kind === "screenshot") return "image";
  if (isPdfArtifact(artifact)) return "pdf";
  if (isSpreadsheetArtifact(artifact)) return "sheet";
  if (isHtmlArtifact(artifact)) return "html";
  if (isOfficeArtifact(artifact)) return officeSiblingPreviewKind(artifact);
  return "none";
}

export function canInlinePreview(artifact: PreviewArtifact): boolean {
  return previewKind(artifact) !== "none";
}

export function getPreviewUrl(artifact: RunArtifact): string | null {
  // Office: use the HTML/PDF sibling for preview when present
  if (isOfficeArtifact(artifact) && !isPdfArtifact(artifact) && !isSpreadsheetArtifact(artifact)) {
    const previewUrl = artifact.metadata?.preview_url;
    if (typeof previewUrl === "string" && previewUrl) return previewUrl;
  }
  return artifact.url || null;
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

/**
 * Ask the backend for a fresh signed / data URI URL for an artifact.
 */
export async function fetchFreshArtifactUrl(artifactId: string): Promise<string | null> {
  const res = await fetchWithTimeout(
    `/api/v1/artifacts/${encodeURIComponent(artifactId)}/download`,
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
): Promise<string | null> {
  const relative = path.includes("/Workspaces/")
    ? path.split("/Workspaces/").pop() || path
    : path.replace(/^\/home\/user\/CoComputer\/Workspaces\/?/, "");

  const res = await fetchWithTimeout(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}/files/download?relative_path=${encodeURIComponent(relative)}`,
    SANDBOX_TIMEOUT_MS,
  );
  if (!res?.ok) return null;
  try {
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  } catch {
    return null;
  }
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
  if (url.startsWith("data:")) return toBlobUrlIfDataUri(url);
  if (url.startsWith("blob:") || url.startsWith("http")) return url;
  return null;
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
  // Permanent non-GCS URLs (Drive, http(s) CDN, etc.)
  if (
    artifact.url &&
    !artifact.url.includes("storage.googleapis.com") &&
    !artifact.url.startsWith("data:")
  ) {
    if (forPreview) {
      const preview = getPreviewUrl(artifact);
      if (preview && preview !== artifact.url) {
        const src = usableInlineSrc(preview);
        if (src) return src;
      }
    }
    return artifact.url;
  }

  if (artifact.url?.startsWith("data:")) {
    return toBlobUrlIfDataUri(artifact.url);
  }

  // Office artifacts: use the HTML/PDF preview sibling when available
  if (forPreview) {
    const officePreview = getPreviewUrl(artifact);
    if (officePreview && officePreview !== artifact.url) {
      const src = usableInlineSrc(officePreview);
      if (src) return src;
    }
  }

  const fresh = await fetchFreshArtifactUrl(artifact.artifact_id);
  if (fresh) {
    return toBlobUrlIfDataUri(fresh);
  }

  if (allowSandbox && artifact.path && artifact.session_id) {
    const sandboxUrl = await downloadFromWorkspaceSandbox(
      artifact.session_id,
      artifact.path,
    );
    if (sandboxUrl) return sandboxUrl;
  }

  return artifact.url || null;
}

/**
 * Trigger a browser download for an artifact (blob preferred).
 */
export async function downloadArtifactFile(
  artifact: RunArtifact,
  options?: ResolveArtifactOptions,
): Promise<boolean> {
  const url = await resolveArtifactUrl(artifact, options);
  if (!url) return false;

  const filename =
    artifact.title ||
    artifact.path?.split("/").pop() ||
    `artifact-${artifact.artifact_id.slice(0, 8)}`;

  if (url.startsWith("blob:") || url.startsWith("data:")) {
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    return true;
  }

  // Fetch through our API again and force a blob download when possible
  try {
    const res = await fetch(url);
    if (res.ok) {
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
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
