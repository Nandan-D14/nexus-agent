/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useState } from "react";
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
} from "lucide-react";
import type { RunArtifact } from "@/lib/message-types";

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

function ArtifactIcon({ kind }: { kind: string }) {
  switch (kind) {
    case "pdf_report":
    case "pdf":
      return <FileText className="w-5 h-5 text-red-400" />;
    case "image":
    case "screenshot":
      return <ImageIcon className="w-5 h-5 text-blue-400" />;
    case "data":
    case "csv":
    case "json":
      return <Database className="w-5 h-5 text-emerald-400" />;
    case "spreadsheet":
      return <FileSpreadsheet className="w-5 h-5 text-green-400" />;
    case "document":
      return <FileType className="w-5 h-5 text-blue-500" />;
    default:
      return <File className="w-5 h-5 text-zinc-400" />;
  }
}

function isViewableInline(kind: string): boolean {
  return ["pdf_report", "pdf", "image", "screenshot"].includes(kind);
}

function InlinePdfViewer({
  url,
  title,
  onClose,
}: {
  url: string;
  title: string;
  onClose: () => void;
}) {
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
        src={url}
        className="w-full h-[500px] bg-white"
        title={title}
      />
    </div>
  );
}

export function OutputsPanel({
  artifacts,
  emptyState = "No outputs have been captured for this run yet.",
}: Props) {
  const [viewingId, setViewingId] = useState<string | null>(null);

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

        <div className="grid grid-cols-1 gap-3">
          {artifacts.map((artifact) => (
            <div
              key={artifact.artifact_id}
              className="group relative rounded-2xl border border-zinc-800 bg-[#141416] hover:bg-[#19191b] hover:border-zinc-700 transition-all duration-200 p-5 shadow-sm"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-4">
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-zinc-900 border border-zinc-800 group-hover:border-zinc-700 transition-colors">
                    <ArtifactIcon kind={artifact.kind} />
                  </div>
                  <div>
                    <h4 className="text-[15px] font-semibold text-zinc-100 group-hover:text-white transition-colors">
                      {artifact.title || artifact.kind.replace(/_/g, " ")}
                    </h4>
                    <div className="mt-1.5 flex items-center gap-3">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 px-2 py-0.5 rounded-md bg-zinc-900 border border-zinc-800">
                        {artifact.kind.replace(/_/g, " ")}
                      </span>
                      <span className="text-[11px] text-zinc-500">
                        {formatTimestamp(artifact.created_at)}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {/* Inline View for PDF/images */}
                  {artifact.url && isViewableInline(artifact.kind) && (
                    <button
                      onClick={() =>
                        setViewingId(
                          viewingId === artifact.artifact_id
                            ? null
                            : artifact.artifact_id
                        )
                      }
                      className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-bold transition-all border ${
                        viewingId === artifact.artifact_id
                          ? "bg-indigo-500 text-white border-indigo-400"
                          : "bg-indigo-500/10 text-indigo-400 hover:bg-indigo-500 hover:text-white border-indigo-500/20"
                      }`}
                    >
                      <Eye className="w-3.5 h-3.5" />
                      {viewingId === artifact.artifact_id ? "Hide" : "Preview"}
                    </button>
                  )}

                  {/* Download / Open for all artifacts */}
                  {artifact.url && (
                    <a
                      href={artifact.url}
                      target="_blank"
                      rel="noreferrer"
                      download
                      className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-zinc-800/60 text-zinc-300 hover:bg-zinc-700 text-xs font-bold transition-all border border-zinc-700/50"
                    >
                      <Download className="w-3.5 h-3.5" />
                      Download
                    </a>
                  )}

                  {artifact.path && !artifact.url && (
                    <button
                      className="p-2 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
                      title={`Path: ${artifact.path}`}
                    >
                      <Download className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>

              {artifact.preview && (
                <div className="mt-4 pt-4 border-t border-zinc-800/50">
                  <p className="text-[13px] leading-relaxed text-zinc-400 dark:text-zinc-400 line-clamp-3 group-hover:line-clamp-none transition-all">
                    {artifact.preview}
                  </p>
                </div>
              )}

              {/* Inline image preview */}
              {artifact.kind === "image" && artifact.url && (
                <div className="mt-4 rounded-xl overflow-hidden border border-zinc-800 bg-black/20">
                  <img
                    src={artifact.url}
                    alt={artifact.title}
                    className="w-full h-auto max-h-[300px] object-contain"
                  />
                </div>
              )}

              {/* Inline PDF viewer */}
              {viewingId === artifact.artifact_id &&
                artifact.url &&
                (artifact.kind === "pdf_report" || artifact.kind === "pdf") && (
                  <InlinePdfViewer
                    url={artifact.url}
                    title={artifact.title || "PDF Preview"}
                    onClose={() => setViewingId(null)}
                  />
                )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
