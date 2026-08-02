/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useCallback, useState } from "react";
import { Download, Eye, Loader2 } from "lucide-react";
import type { RunArtifact } from "@/lib/message-types";
import {
  canInlinePreview,
  downloadArtifactFile,
  resolveArtifactUrl,
} from "@/lib/artifact-url";
import { ArtifactIconTile, artifactBadge } from "./artifact-icon";
import { DocumentViewerModal } from "./document-viewer-modal";

type Props = {
  artifact: RunArtifact;
  /** Compact chat-style layout */
  compact?: boolean;
};

/**
 * SaaS-style file card: title, type badge, Preview / Download.
 * Preview opens the full-screen viewer so the chat transcript never reflows.
 */
export function ArtifactAttachmentCard({ artifact, compact = false }: Props) {
  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewerUrl, setViewerUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const previewable = canInlinePreview(artifact);

  const handleDownload = useCallback(async () => {
    setLoading(true);
    try {
      await downloadArtifactFile(artifact);
    } catch (e) {
      console.error("Download failed", e);
    } finally {
      setLoading(false);
    }
  }, [artifact]);

  const handleOpenViewer = useCallback(async () => {
    setLoading(true);
    try {
      const url = previewable ? await resolveArtifactUrl(artifact, true) : null;
      setViewerUrl(url);
      setViewerOpen(true);
    } finally {
      setLoading(false);
    }
  }, [artifact, previewable]);

  const closeViewer = useCallback(() => {
    setViewerOpen(false);
    setViewerUrl(null);
  }, []);

  return (
    <>
      <div
        className={
          compact
            ? "rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-[#141414] overflow-hidden"
            : "rounded-xl border border-zinc-800 bg-[#141414] overflow-hidden"
        }
      >
        <div className="flex items-center gap-3 px-3.5 py-3">
          <ArtifactIconTile artifact={artifact} />
          <div className="min-w-0 flex-1">
            <div className="text-[14px] font-medium text-zinc-800 dark:text-zinc-100 truncate">
              {artifact.title || "Generated file"}
            </div>
            <div className="mt-0.5 flex items-center gap-2 text-[12px] text-zinc-500">
              <span className="rounded bg-zinc-200/80 dark:bg-zinc-800 px-1.5 py-0.5 font-medium uppercase tracking-wide text-[10px] text-zinc-600 dark:text-zinc-400">
                {artifactBadge(artifact)}
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
                onClick={handleOpenViewer}
                disabled={loading}
                className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12px] font-medium bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors"
              >
                {loading ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Eye className="w-3.5 h-3.5" />
                )}
                Preview
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
      </div>

      <DocumentViewerModal
        artifact={viewerOpen ? artifact : null}
        url={viewerUrl}
        onClose={closeViewer}
      />
    </>
  );
}
