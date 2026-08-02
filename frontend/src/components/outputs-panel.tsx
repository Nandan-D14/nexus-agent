/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useState, useCallback, useEffect, useRef, useMemo } from "react";
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
  ChevronDown,
  ChevronRight,
  Maximize2,
  Minimize2,
} from "lucide-react";
import type { RunArtifact } from "@/lib/message-types";
import {
  canInlinePreview,
  downloadArtifactFile,
  isDeliverableArtifact,
  isHtmlArtifact,
  isOfficeArtifact,
  isPdfArtifact,
  isSourceArtifact,
  resolveArtifactUrl,
} from "@/lib/artifact-url";
import { PdfArtifactViewer } from "@/components/artifacts";

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
    case "html":
      return <FileText className={className || "w-5 h-5 text-amber-400"} />;
    default:
      return <File className={className || "w-5 h-5 text-zinc-400"} />;
  }
}

function Fullscreenable({
  title,
  onClose,
  openUrl,
  children,
}: {
  title: string;
  onClose?: () => void;
  openUrl?: string;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    const onChange = () => setIsFullscreen(document.fullscreenElement === ref.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const toggle = async () => {
    const el = ref.current;
    if (!el) return;
    try {
      if (document.fullscreenElement === el) await document.exitFullscreen();
      else await el.requestFullscreen();
    } catch {
      // ignore
    }
  };

  return (
    <div
      ref={ref}
      className={
        isFullscreen
          ? "fixed inset-0 z-[9999] flex flex-col bg-black"
          : "mt-4 rounded-xl overflow-hidden border border-zinc-700 bg-black/30"
      }
    >
      <div className="flex items-center justify-between px-4 py-2 bg-zinc-900/80 border-b border-zinc-800 shrink-0">
        <span className="text-xs font-semibold text-zinc-300 truncate">{title}</span>
        <div className="flex items-center gap-2">
          {openUrl && (
            <a
              href={openUrl}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 transition-colors"
            >
              <ExternalLink className="w-3 h-3" />
              Open
            </a>
          )}
          <button
            type="button"
            onClick={toggle}
            className="p-1 rounded hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors"
            title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
          >
            {isFullscreen ? (
              <Minimize2 className="w-3.5 h-3.5" />
            ) : (
              <Maximize2 className="w-3.5 h-3.5" />
            )}
          </button>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="p-1 rounded hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
      <div className={isFullscreen ? "flex-1 min-h-0" : ""}>{children}</div>
    </div>
  );
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
  let embedUrl = url;
  if (url.includes("drive.google.com/file/d/")) {
    embedUrl = url.replace(/\/view.*$/, "/preview");
  }

  return (
    <Fullscreenable title={title} onClose={onClose} openUrl={url}>
      <iframe
        src={embedUrl}
        className="w-full h-full min-h-[500px] bg-white"
        title={title}
        sandbox="allow-scripts allow-forms allow-modals"
      />
    </Fullscreenable>
  );
}

export function OutputsPanel({
  artifacts,
  emptyState = "No outputs have been captured for this run yet.",
}: Props) {
  const [viewingId, setViewingId] = useState<string | null>(null);
  const [freshUrls, setFreshUrls] = useState<Record<string, string>>({});
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const fetchedIds = useRef<Set<string>>(new Set());
  const autoOpenedIds = useRef<Set<string>>(new Set());

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

  useEffect(() => {
    deliverables.forEach((artifact) => {
      const wantsEager =
        artifact.kind === "image" ||
        artifact.kind === "screenshot" ||
        isHtmlArtifact(artifact) ||
        isPdfArtifact(artifact);
      if (wantsEager && !freshUrls[artifact.artifact_id] && !fetchedIds.current.has(artifact.artifact_id)) {
        fetchedIds.current.add(artifact.artifact_id);
        resolveUrl(artifact).catch(() => {});
      }
    });
  }, [deliverables, resolveUrl, freshUrls]);

  useEffect(() => {
    const htmlArtifact = deliverables.find(isHtmlArtifact);
    if (!htmlArtifact || autoOpenedIds.current.has(htmlArtifact.artifact_id)) return;
    autoOpenedIds.current.add(htmlArtifact.artifact_id);
    setViewingId(htmlArtifact.artifact_id);
  }, [deliverables]);

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

  const handleTogglePreview = useCallback(
    async (artifact: RunArtifact) => {
      if (viewingId === artifact.artifact_id) {
        setViewingId(null);
        return;
      }
      if (!canInlinePreview(artifact)) {
        // Office without PDF preview: jump straight to download
        await handleDownload(artifact);
        return;
      }
      setLoadingId(artifact.artifact_id);
      try {
        const url = await resolveUrl(artifact, true);
        if (url) {
          setViewingId(artifact.artifact_id);
        } else {
          console.error("No previewable URL found for artifact", artifact.artifact_id);
        }
      } finally {
        setLoadingId(null);
      }
    },
    [viewingId, resolveUrl, handleDownload],
  );

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
              const isImage = artifact.kind === "image" || artifact.kind === "screenshot";
              const isHtml = isHtmlArtifact(artifact);
              const isPdf = isPdfArtifact(artifact);
              const isOffice = isOfficeArtifact(artifact) && !isPdf;
              const previewable = canInlinePreview(artifact);

              return (
                <div
                  key={artifact.artifact_id}
                  className="group relative rounded-xl border border-zinc-800 bg-[#141414] hover:bg-[#1a1a1c] hover:border-zinc-700 transition-all duration-200 overflow-hidden shadow-sm flex flex-col"
                >
                  <div className="relative aspect-video w-full bg-[#1c1c1e] flex items-center justify-center overflow-hidden border-b border-zinc-800">
                    {isImage && currentUrl ? (
                      <img
                        src={currentUrl}
                        alt={artifact.title}
                        className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity"
                      />
                    ) : isHtml && currentUrl ? (
                      <iframe
                        src={currentUrl}
                        title={`${artifact.title} thumbnail`}
                        className="w-[200%] h-[200%] scale-50 origin-top-left bg-white pointer-events-none opacity-80 group-hover:opacity-100 transition-opacity"
                        sandbox="allow-scripts allow-forms allow-modals"
                      />
                    ) : (
                      <div className="flex flex-col items-center gap-2 opacity-50 group-hover:opacity-70 transition-opacity">
                        <ArtifactIcon kind={artifact.kind} className="w-12 h-12 text-zinc-500" />
                        {isOffice && !artifact.metadata?.preview_url && (
                          <span className="text-[10px] uppercase tracking-wide text-zinc-500">
                            Download to open
                          </span>
                        )}
                        {isOffice && artifact.metadata?.preview_url && (
                          <span className="text-[10px] uppercase tracking-wide text-zinc-500">
                            PDF preview available
                          </span>
                        )}
                      </div>
                    )}

                    <div className="absolute bottom-2 right-2 bg-white/10 backdrop-blur-md px-2 py-0.5 rounded-full text-[10px] font-medium text-white flex items-center gap-1 border border-white/10 shadow-sm">
                      <Eye className="w-3 h-3" /> {previewable ? "Preview" : "File"}
                    </div>

                    <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 flex items-center justify-center gap-3 transition-opacity">
                      <button
                        type="button"
                        onClick={() => handleTogglePreview(artifact)}
                        disabled={isLoading}
                        className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 text-xs font-semibold transition-all shadow-md disabled:opacity-50"
                      >
                        {isLoading ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Eye className="w-3.5 h-3.5" />
                        )}
                        {isOffice && !artifact.metadata?.preview_url
                          ? "Open"
                          : viewingId === artifact.artifact_id
                            ? "Hide"
                            : "Preview"}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDownload(artifact)}
                        disabled={isLoading}
                        className="p-1.5 rounded-lg bg-zinc-700 text-white hover:bg-zinc-600 text-xs font-semibold transition-all shadow-md disabled:opacity-50"
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
                          className="p-1.5 rounded-lg bg-zinc-700 text-white hover:bg-zinc-600 text-xs font-semibold transition-all shadow-md"
                          title="Open in new tab"
                        >
                          <ExternalLink className="w-4 h-4" />
                        </a>
                      )}
                    </div>
                  </div>

                  <div className="p-4 flex flex-col flex-grow">
                    <h4
                      className="text-[14px] font-semibold text-zinc-200 line-clamp-1 group-hover:text-white transition-colors"
                      title={artifact.title || artifact.kind}
                    >
                      {artifact.title || artifact.kind.replace(/_/g, " ")}
                    </h4>
                    <div className="mt-1 flex items-center gap-2">
                      <p className="text-[12px] text-zinc-500 line-clamp-1">
                        Last edited {formatTimestamp(artifact.created_at)}
                      </p>
                    </div>
                  </div>

                  {viewingId === artifact.artifact_id && previewable && (
                    <div className="border-t border-zinc-800 bg-[#0a0a0c] p-3">
                      {artifact.preview && !isImage && !isPdf && (
                        <div className="text-[13px] leading-relaxed text-zinc-400 line-clamp-4 group-hover:line-clamp-none transition-all mb-4 [&_a]:text-blue-400">
                          <ReactMarkdown>{artifact.preview}</ReactMarkdown>
                        </div>
                      )}

                      {isImage && currentUrl && (
                        <Fullscreenable title={artifact.title || "Image"} onClose={() => setViewingId(null)} openUrl={currentUrl}>
                          <div className="rounded-xl overflow-hidden border border-zinc-800 bg-black/20 relative">
                            <img
                              src={currentUrl}
                              alt={artifact.title}
                              className="w-full h-auto object-contain max-h-[60vh]"
                            />
                          </div>
                        </Fullscreenable>
                      )}

                      {isPdf && (
                        <PdfArtifactViewer
                          artifact={artifact}
                          url={currentUrl}
                          title={artifact.title || "PDF preview"}
                          onClose={() => setViewingId(null)}
                        />
                      )}

                      {isOffice && !isPdf && currentUrl && (
                        <PdfArtifactViewer
                          artifact={artifact}
                          url={currentUrl}
                          title={artifact.title || "PDF preview"}
                          onClose={() => setViewingId(null)}
                        />
                      )}

                      {isHtml && currentUrl && (
                        <InlineIframeViewer
                          url={currentUrl}
                          title={artifact.title || "Preview"}
                          onClose={() => setViewingId(null)}
                        />
                      )}
                    </div>
                  )}
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
                      <ArtifactIcon kind={artifact.kind} className="w-4 h-4 text-zinc-500 shrink-0" />
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
    </div>
  );
}
