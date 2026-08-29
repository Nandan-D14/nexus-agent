/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import {
  FileText,
  Download,
  ExternalLink,
  File,
  Eye,
  Loader2,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import type { RunArtifact } from "@/lib/message-types";
import {
  canInlinePreview,
  downloadArtifactFile,
  isDeliverableArtifact,
  isSourceArtifact,
  previewKind,
  resolveArtifactUrl,
} from "@/lib/artifact-url";
import { ArtifactIcon, DocumentViewerModal } from "@/components/artifacts";
import { useSessionCanvas } from "@/lib/session-canvas-context";
import { isCanvasArtifact } from "@/lib/session-canvas";

type Props = {
  artifacts: RunArtifact[];
  emptyState?: string;
};

/** Strips the native PDF chrome so card thumbnails show just the page. */
const PDF_THUMBNAIL_PARAMS = "#toolbar=0&navpanes=0&scrollbar=0&view=FitH";

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "Unknown time";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown time";
  return date.toLocaleString();
}

export function OutputsPanel({
  artifacts,
  emptyState = "No outputs have been captured for this run yet.",
}: Props) {
  const [viewerArtifact, setViewerArtifact] = useState<RunArtifact | null>(null);
  const [viewerUrl, setViewerUrl] = useState<string | null>(null);
  const [freshUrls, setFreshUrls] = useState<Record<string, string>>({});
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const fetchedIds = useRef<Set<string>>(new Set());
  const canvas = useSessionCanvas();

  const deliverables = useMemo(
    () => artifacts.filter(isDeliverableArtifact),
    [artifacts],
  );
  const sources = useMemo(
    () => artifacts.filter(isSourceArtifact),
    [artifacts],
  );

  const resolveUrl = useCallback(
    async (artifact: RunArtifact, forPreview = true): Promise<string | null> => {
      if (freshUrls[artifact.artifact_id]) return freshUrls[artifact.artifact_id];
      const url = await resolveArtifactUrl(artifact, forPreview);
      if (url) {
        setFreshUrls((prev) => ({ ...prev, [artifact.artifact_id]: url }));
      }
      return url;
    },
    [freshUrls],
  );

  // Prefetch URLs for anything that renders a thumbnail on its card.
  useEffect(() => {
    deliverables.forEach((artifact) => {
      const kind = previewKind(artifact);
      if (kind === "none" || kind === "sheet") return;
      if (freshUrls[artifact.artifact_id] || fetchedIds.current.has(artifact.artifact_id)) {
        return;
      }
      fetchedIds.current.add(artifact.artifact_id);
      resolveUrl(artifact).catch(() => {});
    });
  }, [deliverables, resolveUrl, freshUrls]);

  const handleDownload = useCallback(async (artifact: RunArtifact) => {
    setLoadingId(artifact.artifact_id);
    try {
      await downloadArtifactFile(artifact);
    } catch (e) {
      console.error("Download failed", e);
    } finally {
      setLoadingId(null);
    }
  }, []);

  const handleOpenViewer = useCallback(
    async (artifact: RunArtifact) => {
      if (canvas && isCanvasArtifact(artifact)) {
        canvas.openFromArtifact(artifact, "user");
        return;
      }
      if (!canInlinePreview(artifact)) {
        // The viewer explains why and offers a download instead.
        setViewerUrl(null);
        setViewerArtifact(artifact);
        return;
      }
      setLoadingId(artifact.artifact_id);
      try {
        const url = await resolveUrl(artifact, true);
        setViewerUrl(url);
        setViewerArtifact(artifact);
      } finally {
        setLoadingId(null);
      }
    },
    [canvas, resolveUrl],
  );

  const closeViewer = useCallback(() => {
    setViewerArtifact(null);
    setViewerUrl(null);
  }, []);

  const getUrl = (artifact: RunArtifact): string | null =>
    freshUrls[artifact.artifact_id] || artifact.url || null;

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
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-6">
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-lg font-semibold text-zinc-100 flex items-center gap-2">
            <FileText className="w-5 h-5 text-amber-400" />
            Generated Artifacts
          </h3>
          <span className="text-xs font-medium text-zinc-500 uppercase tracking-widest">
            {deliverables.length} deliverable{deliverables.length === 1 ? "" : "s"}
            {sources.length > 0 ? ` · ${sources.length} source${sources.length === 1 ? "" : "s"}` : ""}
          </span>
        </div>

        {deliverables.length === 0 ? (
          <div className="rounded-xl border border-dashed border-zinc-800 bg-white/5 px-4 py-8 text-center text-sm text-zinc-500">
            No downloadable deliverables yet. Sources used during the run are listed below.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {deliverables.map((artifact) => {
              const isLoading = loadingId === artifact.artifact_id;
              const currentUrl = getUrl(artifact);
              const kind = previewKind(artifact);
              const previewable = kind !== "none";

              return (
                <div
                  key={artifact.artifact_id}
                  className="group relative rounded-xl border border-zinc-800 bg-[#141414] hover:bg-[#1a1a1c] hover:border-zinc-700 transition-all duration-200 overflow-hidden shadow-sm flex flex-col"
                >
                  <button
                    type="button"
                    onClick={() => handleOpenViewer(artifact)}
                    className="relative aspect-video w-full bg-[#1c1c1e] flex items-center justify-center overflow-hidden border-b border-zinc-800 text-left"
                    aria-label={`Open ${artifact.title || artifact.kind}`}
                  >
                    {kind === "image" && currentUrl ? (
                      <img
                        src={currentUrl}
                        alt={artifact.title}
                        className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity"
                      />
                    ) : kind === "html" && currentUrl ? (
                      <iframe
                        src={currentUrl}
                        title={`${artifact.title} thumbnail`}
                        className="w-[200%] h-[200%] scale-50 origin-top-left bg-white pointer-events-none opacity-80 group-hover:opacity-100 transition-opacity"
                        sandbox="allow-scripts allow-forms allow-modals"
                      />
                    ) : kind === "pdf" && currentUrl ? (
                      <object
                        data={`${currentUrl}${PDF_THUMBNAIL_PARAMS}`}
                        type="application/pdf"
                        className="w-[200%] h-[200%] scale-50 origin-top-left bg-white pointer-events-none opacity-80 group-hover:opacity-100 transition-opacity"
                        aria-label={`${artifact.title} thumbnail`}
                      />
                    ) : (
                      <div className="flex w-full flex-col items-center gap-2 opacity-50 group-hover:opacity-70 transition-opacity">
                        <ArtifactIcon artifact={artifact} className="w-12 h-12" />
                        {!previewable && (
                          <span className="text-[10px] uppercase tracking-wide text-zinc-500">
                            Download to open
                          </span>
                        )}
                      </div>
                    )}

                    <div className="absolute bottom-2 right-2 bg-white/10 backdrop-blur-md px-2 py-0.5 rounded-full text-[10px] font-medium text-white flex items-center gap-1 border border-white/10 shadow-sm">
                      <Eye className="w-3 h-3" /> {previewable ? "Preview" : "File"}
                    </div>

                    <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 flex items-center justify-center gap-3 transition-opacity">
                      <span className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs font-semibold shadow-md">
                        {isLoading ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Eye className="w-3.5 h-3.5" />
                        )}
                        Open
                      </span>
                    </div>
                  </button>

                  <div className="p-4 flex flex-col flex-grow">
                    <h4
                      className="text-[14px] font-semibold text-zinc-200 line-clamp-1 group-hover:text-white transition-colors"
                      title={artifact.title || artifact.kind}
                    >
                      {artifact.title || artifact.kind.replace(/_/g, " ")}
                    </h4>
                    <div className="mt-1 flex items-center justify-between gap-2">
                      <p className="text-[12px] text-zinc-500 line-clamp-1">
                        Last edited {formatTimestamp(artifact.created_at)}
                      </p>
                      <div className="flex shrink-0 items-center gap-1">
                        <button
                          type="button"
                          onClick={() => handleDownload(artifact)}
                          disabled={isLoading}
                          className="p-1.5 rounded-lg text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 transition-colors disabled:opacity-50"
                          title="Download"
                        >
                          {isLoading ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <Download className="w-4 h-4" />
                          )}
                        </button>
                        {currentUrl && previewable && (
                          <a
                            href={currentUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="p-1.5 rounded-lg text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 transition-colors"
                            title="Open in new tab"
                          >
                            <ExternalLink className="w-4 h-4" />
                          </a>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {sources.length > 0 && (
          <div className="rounded-xl border border-zinc-800 bg-[#121214] overflow-hidden">
            <button
              type="button"
              onClick={() => setSourcesOpen((open) => !open)}
              className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-zinc-900/60 transition-colors"
            >
              <div className="flex items-center gap-2">
                {sourcesOpen ? (
                  <ChevronDown className="w-4 h-4 text-zinc-500" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-zinc-500" />
                )}
                <span className="text-sm font-medium text-zinc-300">Sources</span>
                <span className="text-[11px] uppercase tracking-wide text-zinc-500">
                  {sources.length}
                </span>
              </div>
              <span className="text-[12px] text-zinc-500">
                Search, scrape, and working files
              </span>
            </button>

            {sourcesOpen && (
              <ul className="divide-y divide-zinc-800/80 border-t border-zinc-800">
                {sources.map((artifact) => {
                  const isLoading = loadingId === artifact.artifact_id;
                  return (
                    <li
                      key={artifact.artifact_id}
                      className="flex items-center gap-3 px-4 py-2.5 hover:bg-zinc-900/40"
                    >
                      <ArtifactIcon artifact={artifact} className="w-4 h-4 shrink-0" />
                      <div className="min-w-0 flex-1">
                        <div className="text-[13px] text-zinc-300 truncate">
                          {artifact.title || artifact.kind.replace(/_/g, " ")}
                        </div>
                        <div className="text-[11px] text-zinc-500 truncate">
                          {artifact.preview || formatTimestamp(artifact.created_at)}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleDownload(artifact)}
                        disabled={isLoading}
                        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-zinc-300 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50"
                        title="Download"
                      >
                        {isLoading ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <Download className="w-3 h-3" />
                        )}
                        Download
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}
      </div>

      <DocumentViewerModal
        artifact={viewerArtifact}
        url={viewerUrl}
        onClose={closeViewer}
      />
    </div>
  );
}
