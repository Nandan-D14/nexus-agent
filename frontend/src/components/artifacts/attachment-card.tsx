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
import {
  Artifact,
  ArtifactAction,
  ArtifactActions,
  ArtifactDescription,
  ArtifactHeader,
  ArtifactTitle,
} from "@/components/ai-elements/artifact";
import { ArtifactIconTile, artifactBadge } from "./artifact-icon";
import { DocumentViewerModal } from "./document-viewer-modal";
import { CanvasHandleCard } from "@/components/session/canvas-handle-card";
import { useSessionCanvas } from "@/lib/session-canvas-context";
import { canvasKindForArtifact, isCanvasArtifact } from "@/lib/session-canvas";
import { cn } from "@/lib/utils";

type Props = {
  artifact: RunArtifact;
  /** Compact chat-style layout */
  compact?: boolean;
};

/**
 * Chat deliverable card: AI Elements Artifact chrome with Preview / Download.
 * In a live session, canvas-worthy artifacts open the right-hand document pane.
 * Elsewhere, preview still uses the full-screen viewer.
 */
export function ArtifactAttachmentCard({ artifact, compact = false }: Props) {
  const canvas = useSessionCanvas();
  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewerUrl, setViewerUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const previewable = canInlinePreview(artifact);
  const badge = artifactBadge(artifact);
  const openInCanvas = Boolean(canvas) && isCanvasArtifact(artifact);

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

  if (openInCanvas && canvas) {
    return (
      <CanvasHandleCard
        kind={canvasKindForArtifact(artifact)}
        title={artifact.title || "Untitled"}
        subtitle={artifact.path || artifact.title || badge}
        artifact={artifact}
        onOpen={() => canvas.openFromArtifact(artifact, "user")}
        onDownload={handleDownload}
        downloading={loading}
      />
    );
  }

  const descriptionParts = [
    badge,
    artifact.preview?.trim() ? artifact.preview.trim() : null,
  ].filter(Boolean);

  return (
    <>
      <Artifact
        className={cn(
          "w-full max-w-xl shadow-sm",
          compact
            ? "rounded-xl border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-[#141414]"
            : "rounded-xl border-zinc-800 bg-[#141414]",
        )}
      >
        <ArtifactHeader
          className={cn(
            "gap-3 border-b-0 bg-transparent px-3.5 py-3",
            compact ? "dark:bg-transparent" : "",
          )}
        >
          <div className="flex min-w-0 flex-1 items-center gap-3">
            <ArtifactIconTile artifact={artifact} />
            <div className="min-w-0">
              <ArtifactTitle className="truncate text-[14px] text-zinc-800 dark:text-zinc-100">
                {artifact.title || "Generated file"}
              </ArtifactTitle>
              {descriptionParts.length > 0 ? (
                <ArtifactDescription className="mt-0.5 flex items-center gap-2 text-[12px] text-zinc-500">
                  <span className="rounded bg-zinc-200/80 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                    {badge}
                  </span>
                  {artifact.preview ? (
                    <span className="max-w-[240px] truncate">{artifact.preview}</span>
                  ) : null}
                </ArtifactDescription>
              ) : null}
            </div>
          </div>
          <ArtifactActions className="shrink-0">
            {previewable ? (
              <ArtifactAction
                tooltip="Preview"
                label="Preview"
                icon={loading ? Loader2 : Eye}
                onClick={handleOpenViewer}
                disabled={loading}
                className={cn(
                  loading && "[&_svg]:animate-spin",
                  "text-indigo-600 hover:text-indigo-500 dark:text-indigo-400",
                )}
              />
            ) : null}
            <ArtifactAction
              tooltip="Download"
              label="Download"
              icon={loading ? Loader2 : Download}
              onClick={handleDownload}
              disabled={loading}
              className={cn(loading && "[&_svg]:animate-spin")}
            />
          </ArtifactActions>
        </ArtifactHeader>
      </Artifact>

      <DocumentViewerModal
        artifact={viewerOpen ? artifact : null}
        url={viewerUrl}
        onClose={closeViewer}
      />
    </>
  );
}
