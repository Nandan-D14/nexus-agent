/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Download, ExternalLink, FileCode, FileText, Loader2, Maximize2, Minimize2, X } from "lucide-react";
import type { RunArtifact } from "@/lib/message-types";
import {
  downloadArtifactFile,
  downloadTextFile,
  isCodePath,
  previewKind,
  usablePreviewSrc,
} from "@/lib/artifact-url";
import { ArtifactIconTile, artifactBadge } from "./artifact-icon";
import { ArtifactPreview } from "./artifact-preview";
import { CodePreview } from "./code-preview";
import { MarkdownPreview } from "./markdown-preview";

type Props = {
  /** The artifact to display; `null` closes the viewer unless markdown is set. */
  artifact: RunArtifact | null;
  /** Pre-resolved preview URL. Resolved internally when omitted. */
  url?: string | null;
  /** Inline markdown for workspace files that are not stored as artifacts. */
  markdown?: string | null;
  title?: string;
  onClose: () => void;
};

const ICON_BUTTON =
  "flex h-8 w-8 items-center justify-center rounded-lg text-text-tertiary transition-colors hover:bg-background-secondary-hover hover:text-text-primary disabled:opacity-50";

// `createPortal` needs a real DOM, so the modal renders nothing until hydration.
const subscribeNoop = () => () => {};
const getIsClient = () => true;
const getIsServer = () => false;

function formatModified(value: string | null | undefined): string {
  if (!value) return "Unknown date";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown date";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function ViewerPanel({
  artifact,
  url: initialUrl,
  markdown,
  title: titleOverride,
  onClose,
}: {
  artifact: RunArtifact | null;
  url?: string | null;
  markdown?: string | null;
  title?: string;
  onClose: () => void;
}) {
  const [url, setUrl] = useState<string | null>(usablePreviewSrc(initialUrl));
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const panelRef = useRef<HTMLDivElement | null>(null);

  const title =
    artifact?.title || titleOverride || artifact?.kind.replace(/_/g, " ") || "Document";
  const codeOnly = !artifact && isCodePath(titleOverride || title || "");
  const kind = artifact ? previewKind(artifact) : codeOnly ? "code" : "markdown";
  const wide = kind === "sheet" || kind === "html" || kind === "pdf" || kind === "code";

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      // The browser consumes the first Escape to leave fullscreen; only close after that.
      if (document.fullscreenElement) return;
      onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  useEffect(() => {
    const element = panelRef.current;
    const onFullscreenChange = () => setIsFullscreen(document.fullscreenElement === element);
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => {
      document.removeEventListener("fullscreenchange", onFullscreenChange);
      if (document.fullscreenElement === element) {
        document.exitFullscreen().catch(() => {});
      }
    };
  }, []);

  const toggleFullscreen = useCallback(async () => {
    const element = panelRef.current;
    if (!element) return;
    try {
      if (document.fullscreenElement === element) await document.exitFullscreen();
      else await element.requestFullscreen();
    } catch {
      // Fullscreen can be blocked by browser policy; keep the windowed viewer.
    }
  }, []);

  const handleDownload = useCallback(async () => {
    if (artifact) {
      setDownloading(true);
      try {
        await downloadArtifactFile(artifact);
      } catch (e) {
        console.error("Download failed", e);
      } finally {
        setDownloading(false);
      }
      return;
    }
    if (markdown) {
      const name = titleOverride || title || (codeOnly ? "file.txt" : "document.md");
      const mime = codeOnly
        ? "text/plain;charset=utf-8"
        : /\.html?$/i.test(name)
          ? "text/html;charset=utf-8"
          : "text/markdown;charset=utf-8";
      downloadTextFile(name, markdown, mime);
    }
  }, [artifact, codeOnly, markdown, title, titleOverride]);

  return (
    <motion.div
      className="fixed inset-0 z-[120] flex items-center justify-center p-4"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.15 }}
      role="presentation"
    >
      <button
        type="button"
        aria-label="Close preview"
        tabIndex={-1}
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-black/70 backdrop-blur-sm"
      />

      <motion.div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        initial={{ scale: 0.96, y: 8 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.96, y: 8 }}
        transition={{ duration: 0.18, ease: [0.32, 0.72, 0, 1] }}
        className={
          isFullscreen
            ? "relative z-10 flex h-screen w-screen flex-col overflow-hidden bg-background-full"
            : wide
              ? "relative z-10 flex h-[min(920px,calc(100dvh-40px))] w-[min(1280px,calc(100vw-32px))] flex-col overflow-hidden rounded-2xl border border-card-border bg-background-full shadow-2xl"
              : "relative z-10 flex h-[min(880px,calc(100dvh-64px))] w-[min(920px,calc(100vw-64px))] flex-col overflow-hidden rounded-2xl border border-card-border bg-background-full shadow-2xl"
        }
      >
        <div className="flex shrink-0 items-center gap-3 border-b border-separator-border px-4 py-3">
          {artifact ? (
            <ArtifactIconTile
              artifact={artifact}
              className="h-9 w-9"
              iconClassName="w-[18px] h-[18px]"
            />
          ) : (
            <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border ${codeOnly ? "border-lime-500/20 bg-lime-500/10 text-lime-400" : "border-violet-500/20 bg-violet-500/10 text-violet-400"}`}>
              {codeOnly ? <FileCode className="h-[18px] w-[18px]" /> : <FileText className="h-[18px] w-[18px]" />}
            </div>
          )}
          <div className="min-w-0 flex-1">
            <div className="truncate text-[14px] font-semibold text-text-primary" title={title}>
              {title}
            </div>
            <div className="mt-0.5 truncate text-[12px] text-text-secondary">
              {artifact ? artifactBadge(artifact) : codeOnly ? (title.split(".").pop() || "CODE").toUpperCase() : "Markdown"} · Last modified{" "}
              {formatModified(artifact?.created_at)}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {url && !url.includes("storage.googleapis.com") && (
              <a
                href={url}
                target="_blank"
                rel="noreferrer"
                className={ICON_BUTTON}
                title="Open in new tab"
              >
                <ExternalLink className="h-4 w-4" />
              </a>
            )}
            {(artifact || markdown) ? (
              <button
                type="button"
                onClick={handleDownload}
                disabled={downloading}
                className={ICON_BUTTON}
                title="Download"
              >
                {downloading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Download className="h-4 w-4" />
                )}
              </button>
            ) : null}
            <button
              type="button"
              onClick={toggleFullscreen}
              className={ICON_BUTTON}
              title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
            >
              {isFullscreen ? (
                <Minimize2 className="h-4 w-4" />
              ) : (
                <Maximize2 className="h-4 w-4" />
              )}
            </button>
            <button type="button" onClick={onClose} className={ICON_BUTTON} title="Close">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {artifact ? (
          <ArtifactPreview
            artifact={artifact}
            url={usablePreviewSrc(initialUrl)}
            onUrlChange={setUrl}
            className="relative min-h-0 flex-1 bg-background-full"
          />
        ) : codeOnly ? (
          <CodePreview
            content={markdown || ""}
            filename={title}
            className="relative min-h-0 flex-1"
          />
        ) : (
          <MarkdownPreview content={markdown || ""} className="relative min-h-0 flex-1" />
        )}
      </motion.div>
    </motion.div>
  );
}

/**
 * Full-screen document viewer rendered into `document.body`, so it is never
 * constrained by the chat bubble or the artifacts grid cell that launched it.
 */
export function DocumentViewerModal({ artifact, url, markdown, title, onClose }: Props) {
  const hydrated = useSyncExternalStore(subscribeNoop, getIsClient, getIsServer);
  const open = Boolean(artifact) || Boolean(markdown);

  if (!hydrated) return null;

  return createPortal(
    <AnimatePresence>
      {open ? (
        <ViewerPanel
          key={artifact?.artifact_id || title || "markdown"}
          artifact={artifact}
          url={url}
          markdown={markdown}
          title={title}
          onClose={onClose}
        />
      ) : null}
    </AnimatePresence>,
    document.body,
  );
}
