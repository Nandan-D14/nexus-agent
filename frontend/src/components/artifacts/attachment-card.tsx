/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useCallback, useState } from "react";
import {
  Download,
  Eye,
  File,
  FileSpreadsheet,
  FileText,
  FileType,
  Image as ImageIcon,
  Loader2,
} from "lucide-react";
import type { RunArtifact } from "@/lib/message-types";
import {
  canInlinePreview,
  downloadArtifactFile,
  isHtmlArtifact,
  isOfficeArtifact,
  isPdfArtifact,
  resolveArtifactUrl,
} from "@/lib/artifact-url";
import { PdfArtifactViewer } from "@/components/artifacts/pdf-viewer";

type Props = {
  artifact: RunArtifact;
  /** Compact chat-style layout */
  compact?: boolean;
};

function ArtifactKindIcon({ kind, className }: { kind: string; className?: string }) {
  const cls = className || "w-5 h-5";
  switch (kind) {
    case "pdf_report":
    case "pdf":
      return <FileText className={`${cls} text-red-400`} />;
    case "image":
    case "screenshot":
      return <ImageIcon className={`${cls} text-blue-400`} />;
    case "spreadsheet":
      return <FileSpreadsheet className={`${cls} text-green-400`} />;
    case "document":
      return <FileType className={`${cls} text-blue-500`} />;
    case "html":
      return <FileText className={`${cls} text-amber-400`} />;
    default:
      return <File className={`${cls} text-zinc-400`} />;
  }
}

function kindBadge(artifact: RunArtifact): string {
  if (isPdfArtifact(artifact)) return "PDF";
  if (artifact.kind === "document") return "DOCX";
  if (artifact.kind === "spreadsheet") return "XLSX";
  if (isHtmlArtifact(artifact)) return "HTML";
  if (artifact.kind === "image" || artifact.kind === "screenshot") return "Image";
  return artifact.kind.replace(/_/g, " ").toUpperCase();
}

/**
 * SaaS-style file card: title, type badge, Preview / Download.
 * Office formats: download only (no broken iframe).
 */
export function ArtifactAttachmentCard({ artifact, compact = false }: Props) {
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const previewable = canInlinePreview(artifact);
  const officeOnly = isOfficeArtifact(artifact) && !isPdfArtifact(artifact);

  const handleDownload = useCallback(async () => {
    setLoading(true);
    try {
      await downloadArtifactFile(artifact);
    } finally {
      setLoading(false);
    }
  }, [artifact]);

  const handleTogglePreview = useCallback(async () => {
    if (!previewable) return;
    if (previewOpen) {
      setPreviewOpen(false);
      return;
    }
    setLoading(true);
    try {
      const url = await resolveArtifactUrl(artifact, true);
      if (url) {
        setPreviewUrl(url);
        setPreviewOpen(true);
      }
    } finally {
      setLoading(false);
    }
  }, [artifact, previewOpen, previewable]);

  return (
    <div
      className={
        compact
          ? "rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-[#141414] overflow-hidden"
          : "rounded-xl border border-zinc-800 bg-[#141414] overflow-hidden"
      }
    >
      <div className="flex items-center gap-3 px-3.5 py-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800">
          <ArtifactKindIcon kind={artifact.kind} className="w-5 h-5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[14px] font-medium text-zinc-800 dark:text-zinc-100 truncate">
            {artifact.title || "Generated file"}
          </div>
          <div className="mt-0.5 flex items-center gap-2 text-[12px] text-zinc-500">
            <span className="rounded bg-zinc-200/80 dark:bg-zinc-800 px-1.5 py-0.5 font-medium uppercase tracking-wide text-[10px] text-zinc-600 dark:text-zinc-400">
              {kindBadge(artifact)}
            </span>
            {artifact.preview && (
              <span className="truncate max-w-[240px]">{artifact.preview}</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {previewable && (
            <button
              type="button"
              onClick={handleTogglePreview}
              disabled={loading}
              className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12px] font-medium bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors"
            >
              {loading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Eye className="w-3.5 h-3.5" />
              )}
              {previewOpen ? "Hide" : "Preview"}
            </button>
          )}
          <button
            type="button"
            onClick={handleDownload}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12px] font-medium bg-zinc-200 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-200 hover:bg-zinc-300 dark:hover:bg-zinc-700 disabled:opacity-50 transition-colors"
            title="Download"
          >
            {loading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Download className="w-3.5 h-3.5" />
            )}
            Download
          </button>
        </div>
      </div>

      {officeOnly && !artifact.metadata?.preview_url && (
        <div className="px-3.5 pb-3 text-[12px] text-zinc-500">
          Preview in Word/Excel after download — inline Office preview is not available.
        </div>
      )}

      {previewOpen && previewUrl && isPdfArtifact(artifact) && (
        <div className="px-3 pb-3">
          <PdfArtifactViewer
            artifact={artifact}
            url={previewUrl}
            onClose={() => setPreviewOpen(false)}
            heightClassName="h-[640px]"
          />
        </div>
      )}

      {previewOpen && previewUrl && (artifact.kind === "image" || artifact.kind === "screenshot") && (
        <div className="px-3 pb-3">
          <img
            src={previewUrl}
            alt={artifact.title}
            className="w-full max-h-[360px] object-contain rounded-lg border border-zinc-800 bg-black/20"
          />
        </div>
      )}

      {previewOpen && previewUrl && isOfficeArtifact(artifact) && !isPdfArtifact(artifact) && (
        <div className="px-3 pb-3">
          <PdfArtifactViewer
            artifact={artifact}
            url={previewUrl}
            onClose={() => setPreviewOpen(false)}
            heightClassName="h-[640px]"
          />
        </div>
      )}

      {previewOpen && previewUrl && isHtmlArtifact(artifact) && (
        <div className="px-3 pb-3">
          <iframe
            src={previewUrl}
            title={artifact.title || "HTML preview"}
            className="w-full h-[360px] rounded-lg border border-zinc-800 bg-white"
            sandbox="allow-scripts allow-forms allow-modals"
          />
        </div>
      )}
    </div>
  );
}
