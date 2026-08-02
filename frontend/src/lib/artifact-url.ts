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

export function isHtmlArtifact(artifact: Pick<RunArtifact, "kind" | "metadata">): boolean {
  return artifact.kind === "html" || artifact.metadata?.render_mode === "iframe";
}

export function isOfficeArtifact(artifact: Pick<RunArtifact, "kind" | "metadata">): boolean {
  if (artifact.kind === "document" || artifact.kind === "spreadsheet") return true;
  const contentType = String(artifact.metadata?.content_type ?? "").toLowerCase();
  return (
    contentType.includes("wordprocessingml") ||
    contentType.includes("spreadsheetml") ||
    contentType.includes("msword") ||
    contentType.includes("ms-excel") ||
    contentType.includes("officedocument")
  );
}

export function canInlinePreview(artifact: Pick<RunArtifact, "kind" | "metadata">): boolean {
  if (isOfficeArtifact(artifact) && !isPdfArtifact(artifact)) return false;
  return (
    isPdfArtifact(artifact) ||
    isHtmlArtifact(artifact) ||
    artifact.kind === "image" ||
    artifact.kind === "screenshot"
  );
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

/**
 * Resolve a working preview/download URL.
 * Prefer the authenticated download API for GCS-backed artifacts.
 */
export async function resolveArtifactUrl(artifact: RunArtifact): Promise<string | null> {
  // Permanent non-GCS URLs (Drive, http(s) CDN, etc.)
  if (
    artifact.url &&
    !artifact.url.includes("storage.googleapis.com") &&
    !artifact.url.startsWith("data:")
  ) {
    return artifact.url;
  }

  if (artifact.url?.startsWith("data:")) {
    return toBlobUrlIfDataUri(artifact.url);
  }

  const fresh = await fetchFreshArtifactUrl(artifact.artifact_id);
  if (fresh) {
    return toBlobUrlIfDataUri(fresh);
  }

  if (artifact.path && artifact.session_id) {
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
export async function downloadArtifactFile(artifact: RunArtifact): Promise<boolean> {
  const url = await resolveArtifactUrl(artifact);
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
            : tool === "publish_html_artifact"
              ? "html"
              : "file";

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
                : kind === "html"
                  ? "text/html"
                  : "application/octet-stream",
      },
    };
  } catch {
    return null;
  }
}
