/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import {
  FileText,
  Download,
  ExternalLink,
  Image as ImageIcon,
  Database,
  File,
  Eye,
  X,
  FileSpreadsheet,
  FileType,
  Loader2,
} from "lucide-react";
import type { RunArtifact } from "@/lib/message-types";
import { authenticatedFetch } from "@/lib/api-client";

type Props = {
  artifacts: RunArtifact[];
  emptyState?: string;
};

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "Unknown time";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown time";
  return date.toLocaleString();
}

function ArtifactIcon({ kind, className }: { kind: string; className?: string }) {
  switch (kind) {
    case "pdf_report":
    case "pdf":
      return <FileText className={className || "w-5 h-5 text-red-400"} />;
    case "image":
    case "screenshot":
      return <ImageIcon className={className || "w-5 h-5 text-blue-400"} />;
    case "data":
    case "csv":
    case "json":
      return <Database className={className || "w-5 h-5 text-emerald-400"} />;
    case "spreadsheet":
      return <FileSpreadsheet className={className || "w-5 h-5 text-green-400"} />;
    case "document":
      return <FileType className={className || "w-5 h-5 text-blue-500"} />;
    default:
      return <File className={className || "w-5 h-5 text-zinc-400"} />;
  }
}

function InlineIframeViewer({
  url,
  title,
  onClose,
}: {
  url: string;
  title: string;
  onClose: () => void;
}) {
  // Convert Google Drive view URLs to preview URLs to bypass iframe restrictions
  let embedUrl = url;
  if (url.includes("drive.google.com/file/d/")) {
    embedUrl = url.replace(/\/view.*$/, "/preview");
  }

  return (
    <div className="mt-4 rounded-xl overflow-hidden border border-zinc-700 bg-black/30">
      <div className="flex items-center justify-between px-4 py-2 bg-zinc-900/80 border-b border-zinc-800">
        <span className="text-xs font-semibold text-zinc-300 truncate">
          {title}
        </span>
        <div className="flex items-center gap-2">
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 transition-colors"
          >
            <ExternalLink className="w-3 h-3" />
            Open
          </a>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
      <iframe
        src={embedUrl}
        className="w-full h-[500px] bg-white"
        title={title}
      />
    </div>
  );
}

/**
 * Helper to convert a Base64 data URI to a Blob.
 */
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

/**
 * Fetch a fresh signed download URL from the backend for a given artifact.
 * Uses the GCS-backed `/api/v1/artifacts/{id}/download` endpoint.
 */
async function fetchFreshArtifactUrl(artifactId: string): Promise<string | null> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000); // 3-second timeout

    const res = await authenticatedFetch(
      `/api/v1/artifacts/${encodeURIComponent(artifactId)}/download`,
      { signal: controller.signal }
    );
    
    clearTimeout(timeoutId);

    if (!res.ok) return null;
    const body = await res.json();
    return body.url ?? null;
  } catch {
    return null;
  }
}

/**
 * Downloads a file directly from the active sandbox workspace.
 * Used as a fallback if GCS durable storage failed to upload.
 */
async function downloadFromWorkspaceSandbox(sessionId: string, path: string): Promise<string | null> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 4000); // 4-second timeout

    const res = await authenticatedFetch(
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/files/download?relative_path=${encodeURIComponent(path)}`,
      { signal: controller.signal }
    );
    clearTimeout(timeoutId);

    if (!res.ok) return null;
    const blob = await res.blob();
    return window.URL.createObjectURL(blob);
  } catch (e) {
    if ((e as any)?.name !== "AbortError") {
      console.error("Workspace download failed", e);
    }
    return null;
  }
}

export function OutputsPanel({
  artifacts,
  emptyState = "No outputs have been captured for this run yet.",
}: Props) {
  const [viewingId, setViewingId] = useState<string | null>(null);
  // Cache of fresh URLs fetched from the backend, keyed by artifact_id
  const [freshUrls, setFreshUrls] = useState<Record<string, string>>({});
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const fetchedIds = useRef<Set<string>>(new Set());

  /**
   * Resolve a working URL for an artifact. Prefers the one already on the
   * artifact object, but if it's missing (GCS upload returned null, URL expired)
   * it fetches a fresh signed URL from the backend.
   * As a final fallback for local debugging, attempts to fetch from the sandbox.
   */
  const resolveUrl = useCallback(
    async (artifact: RunArtifact): Promise<string | null> => {
      // Already have a cached fresh URL
      if (freshUrls[artifact.artifact_id]) return freshUrls[artifact.artifact_id];
      
      // Use the URL on the artifact if it exists and is not an expired signed URL
      // (Google Drive URLs are permanent, so we can use them directly)
      if (artifact.url && !artifact.url.includes("storage.googleapis.com")) {
        // If it's a data URI, convert it to a Blob URL to bypass browser security restrictions
        if (artifact.url.startsWith("data:")) {
          try {
            const blob = dataURItoBlob(artifact.url);
            const blobUrl = window.URL.createObjectURL(blob);
            setFreshUrls((prev) => ({ ...prev, [artifact.artifact_id]: blobUrl }));
            return blobUrl;
          } catch (e) {
            console.error("Failed to convert data URI to blob URL", e);
            return artifact.url;
          }
        }
        return artifact.url;
      }

      // Fetch a fresh one from GCS metadata
      const freshGcsUrl = await fetchFreshArtifactUrl(artifact.artifact_id);
      if (freshGcsUrl) {
        // If the backend returns a base64 data URI, convert it to a Blob URL
        if (freshGcsUrl.startsWith("data:")) {
          try {
            const blob = dataURItoBlob(freshGcsUrl);
            const blobUrl = window.URL.createObjectURL(blob);
            setFreshUrls((prev) => ({ ...prev, [artifact.artifact_id]: blobUrl }));
            return blobUrl;
          } catch (e) {
            console.error("Failed to convert fresh data URI to blob URL", e);
          }
        }
        setFreshUrls((prev) => ({ ...prev, [artifact.artifact_id]: freshGcsUrl }));
        return freshGcsUrl;
      }
      
      // Fallback: If GCS failed and the file is in the workspace, fetch from sandbox
      if (artifact.path) {
        const sandboxUrl = await downloadFromWorkspaceSandbox(artifact.session_id, artifact.path);
        if (sandboxUrl) {
          setFreshUrls((prev) => ({ ...prev, [artifact.artifact_id]: sandboxUrl }));
          return sandboxUrl;
        }
      }

      return artifact.url || null;
    },
    [freshUrls],
  );

  // Auto-fetch fresh URLs for images so their thumbnails load immediately
  useEffect(() => {
    artifacts.forEach((artifact) => {
      const isImage = artifact.kind === "image" || artifact.kind === "screenshot";
      if (isImage && !freshUrls[artifact.artifact_id] && !fetchedIds.current.has(artifact.artifact_id)) {
        fetchedIds.current.add(artifact.artifact_id);
        resolveUrl(artifact).catch(() => {});
      }
    });
  }, [artifacts, resolveUrl, freshUrls]);

  /** Download an artifact by getting a fresh signed URL and triggering browser download. */
  const handleDownload = useCallback(
    async (artifact: RunArtifact) => {
      setLoadingId(artifact.artifact_id);
      try {
        const url = await resolveUrl(artifact);
        if (!url) {
          console.error("No downloadable URL found for artifact", artifact.artifact_id);
          return;
        }
        
        // Standard, robust way to trigger download of Blob/Data URLs in browsers
        if (url.startsWith("blob:") || url.startsWith("data:")) {
          const link = document.createElement("a");
          link.href = url;
          const filename = artifact.title || artifact.path?.split("/").pop() || "artifact";
          link.download = filename;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
        } else {
          // Open the signed URL in a new tab — the browser handles the download
          window.open(url, "_blank", "noopener,noreferrer");
        }
      } catch (e) {
        console.error("Download failed", e);
      } finally {
        setLoadingId(null);
      }
    },
    [resolveUrl],
  );

  /** Toggle preview — fetches a fresh URL if needed before opening the viewer. */
  const handleTogglePreview = useCallback(
    async (artifact: RunArtifact) => {
      if (viewingId === artifact.artifact_id) {
        setViewingId(null);
        return;
      }
      setLoadingId(artifact.artifact_id);
      try {
        const url = await resolveUrl(artifact);
        if (url) {
          // Store the fresh URL so the viewer can use it
          setFreshUrls((prev) => ({ ...prev, [artifact.artifact_id]: url }));
          setViewingId(artifact.artifact_id);
        } else {
          console.error("No previewable URL found for artifact", artifact.artifact_id);
        }
      } finally {
        setLoadingId(null);
      }
    },
    [viewingId, resolveUrl],
  );

  /** Get the best available URL for an artifact (from cache or original). */
  const getUrl = (artifact: RunArtifact): string | null => {
    return freshUrls[artifact.artifact_id] || artifact.url || null;
  };

  if (artifacts.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-4 py-6 bg-[#0a0a0c]">
        <div className="flex min-h-[240px] w-full max-w-2xl items-center justify-center rounded-2xl border border-dashed border-zinc-800 bg-white/5 p-6 text-center text-sm text-zinc-500">
          <div className="flex flex-col items-center gap-3">
            <File className="w-8 h-8 opacity-20" />
            <p>{emptyState}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto custom-scrollbar px-6 py-8 bg-[#0a0a0c]">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-lg font-semibold text-zinc-100 flex items-center gap-2">
            <FileText className="w-5 h-5 text-amber-400" />
            Generated Artifacts
          </h3>
          <span className="text-xs font-medium text-zinc-500 uppercase tracking-widest">
            {artifacts.length} {artifacts.length === 1 ? 'Item' : 'Items'}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {artifacts.map((artifact) => {
            const isLoading = loadingId === artifact.artifact_id;
            const currentUrl = getUrl(artifact);
            const isImage = artifact.kind === "image" || artifact.kind === "screenshot";

            return (
              <div
                key={artifact.artifact_id}
                className="group relative rounded-xl border border-zinc-800 bg-[#141414] hover:bg-[#1a1a1c] hover:border-zinc-700 transition-all duration-200 overflow-hidden shadow-sm flex flex-col"
              >
                {/* Top Preview Area */}
                <div className="relative aspect-video w-full bg-[#1c1c1e] flex items-center justify-center overflow-hidden border-b border-zinc-800">
                  {isImage && currentUrl ? (
                    <img src={currentUrl} alt={artifact.title} className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity" />
                  ) : (
                    <div className="flex flex-col items-center gap-2 opacity-50 group-hover:opacity-70 transition-opacity">
                      <ArtifactIcon kind={artifact.kind} className="w-12 h-12 text-zinc-500" />
                    </div>
                  )}

                  {/* Optional Eye Icon Badge (like in the screenshot) */}
                  <div className="absolute bottom-2 right-2 bg-white/10 backdrop-blur-md px-2 py-0.5 rounded-full text-[10px] font-medium text-white flex items-center gap-1 border border-white/10 shadow-sm">
                    <Eye className="w-3 h-3" /> Preview
                  </div>

                  {/* Hover Overlay with Actions */}
                  <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 flex items-center justify-center gap-3 transition-opacity">
                    <button
                      onClick={() => handleTogglePreview(artifact)}
                      disabled={isLoading}
                      className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 text-xs font-semibold transition-all shadow-md disabled:opacity-50"
                    >
                      {isLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Eye className="w-3.5 h-3.5" />}
                      {viewingId === artifact.artifact_id ? "Hide" : "Preview"}
                    </button>
                    <button
                      onClick={() => handleDownload(artifact)}
                      disabled={isLoading}
                      className="p-1.5 rounded-lg bg-zinc-700 text-white hover:bg-zinc-600 text-xs font-semibold transition-all shadow-md disabled:opacity-50"
                      title="Download"
                    >
                      {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                    </button>
                    {currentUrl && (
                      <a
                        href={currentUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="p-1.5 rounded-lg bg-zinc-700 text-white hover:bg-zinc-600 text-xs font-semibold transition-all shadow-md"
                        title="Open in new tab"
                      >
                        <ExternalLink className="w-4 h-4" />
                      </a>
                    )}
                  </div>
                </div>

                {/* Bottom Info Area */}
                <div className="p-4 flex flex-col flex-grow">
                  <h4 className="text-[14px] font-semibold text-zinc-200 line-clamp-1 group-hover:text-white transition-colors" title={artifact.title || artifact.kind}>
                    {artifact.title || artifact.kind.replace(/_/g, " ")}
                  </h4>
                  <div className="mt-1 flex items-center gap-2">
                    <p className="text-[12px] text-zinc-500 line-clamp-1">
                      Last edited {formatTimestamp(artifact.created_at)}
                    </p>
                  </div>
                </div>

                {/* Inline Preview expansions (Appears below the card content if activated) */}
                {viewingId === artifact.artifact_id && (
                  <div className="border-t border-zinc-800 bg-[#0a0a0c] p-3">
                    {/* Markdown Preview */}
                    {artifact.preview && !isImage && (
                      <div className="text-[13px] leading-relaxed text-zinc-400 dark:text-zinc-400 line-clamp-4 group-hover:line-clamp-none transition-all mb-4 [&_a]:text-blue-400">
                        <ReactMarkdown>{artifact.preview}</ReactMarkdown>
                      </div>
                    )}
                    
                    {/* Inline image preview (large) */}
                    {isImage && currentUrl && (
                      <div className="rounded-xl overflow-hidden border border-zinc-800 bg-black/20 relative">
                        <div className="absolute top-2 right-2 bg-black/50 rounded p-1 hover:bg-black/80 cursor-pointer text-zinc-300" onClick={() => setViewingId(null)}>
                          <X className="w-4 h-4" />
                        </div>
                        <img src={currentUrl} alt={artifact.title} className="w-full h-auto object-contain max-h-[300px]" />
                      </div>
                    )}

                    {/* Inline Iframe viewer */}
                    {!isImage && currentUrl && (
                      <InlineIframeViewer url={currentUrl} title={artifact.title || "Preview"} onClose={() => setViewingId(null)} />
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
