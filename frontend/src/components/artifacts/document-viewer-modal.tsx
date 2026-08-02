/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Download, ExternalLink, Loader2, Maximize2, Minimize2, X } from "lucide-react";
import type { RunArtifact } from "@/lib/message-types";
import {
  downloadArtifactFile,
  previewKind,
  resolveArtifactUrl,
} from "@/lib/artifact-url";
import { ArtifactIcon, ArtifactIconTile, artifactBadge } from "./artifact-icon";

type Props = {
  /** The artifact to display; `null` closes the viewer. */
  artifact: RunArtifact | null;
  /** Pre-resolved preview URL. Resolved internally when omitted. */
  url?: string | null;
  onClose: () => void;
};

const ICON_BUTTON =
  "flex h-8 w-8 items-center justify-center rounded-lg text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-50";

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
  onClose,
}: {
  artifact: RunArtifact;
  url?: string | null;
  onClose: () => void;
}) {
  const [url, setUrl] = useState<string | null>(initialUrl ?? null);
  const [loading, setLoading] = useState(!initialUrl);
  const [error, setError] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const panelRef = useRef<HTMLDivElement | null>(null);

  const kind = previewKind(artifact);
  const title = artifact.title || artifact.kind.replace(/_/g, " ");

  useEffect(() => {
    if (initialUrl) {
      setUrl(initialUrl);
      setLoading(false);
      return;
    }
    if (kind === "none") {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    resolveArtifactUrl(artifact, true)
      .then((resolved) => {
        if (cancelled) return;
        if (resolved) setUrl(resolved);
        else setError("Could not load a preview for this file.");
      })
      .catch(() => {
        if (!cancelled) setError("Could not load a preview for this file.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [artifact, initialUrl, kind]);

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
    setDownloading(true);
    try {
      await downloadArtifactFile(artifact);
    } catch (e) {
      console.error("Download failed", e);
    } finally {
      setDownloading(false);
    }
  }, [artifact]);

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
            ? "relative z-10 flex h-screen w-screen flex-col overflow-hidden bg-[#1a1a1c]"
            : "relative z-10 flex h-[min(880px,calc(100dvh-64px))] w-[min(1100px,calc(100vw-64px))] flex-col overflow-hidden rounded-2xl border border-white/10 bg-[#1a1a1c] shadow-2xl"
        }
      >
        <div className="flex shrink-0 items-center gap-3 border-b border-zinc-800 px-4 py-3">
          <ArtifactIconTile
            artifact={artifact}
            className="h-9 w-9"
            iconClassName="w-[18px] h-[18px]"
          />
          <div className="min-w-0 flex-1">
            <div className="truncate text-[14px] font-semibold text-zinc-100" title={title}>
              {title}
            </div>
            <div className="mt-0.5 truncate text-[12px] text-zinc-500">
              {artifactBadge(artifact)} · Last modified {formatModified(artifact.created_at)}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {url && (
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

        <div className="relative min-h-0 flex-1 bg-[#0e0e10]">
          {loading ? (
            <div className="flex h-full items-center justify-center gap-2 text-sm text-zinc-400">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading preview…
            </div>
          ) : error ? (
            <div className="flex h-full items-center justify-center px-6 text-center text-sm text-red-400">
              {error}
            </div>
          ) : kind === "none" ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
              <ArtifactIcon artifact={artifact} className="h-14 w-14" />
              <div>
                <p className="text-[14px] font-medium text-zinc-200">
                  Preview isn&apos;t available for this file type
                </p>
                <p className="mt-1 text-[13px] text-zinc-500">
                  Download it to open in your desktop app.
                </p>
              </div>
              <button
                type="button"
                onClick={handleDownload}
                disabled={downloading}
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3.5 py-2 text-[13px] font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
              >
                {downloading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Download className="h-4 w-4" />
                )}
                Download
              </button>
            </div>
          ) : !url ? null : kind === "pdf" ? (
            <object
              data={url}
              type="application/pdf"
              className="h-full w-full bg-white"
              aria-label={title}
            >
              <embed src={url} type="application/pdf" className="h-full w-full" />
            </object>
          ) : kind === "image" ? (
            <div className="flex h-full items-center justify-center p-6">
              <img
                src={url}
                alt={title}
                className="max-h-full max-w-full object-contain"
              />
            </div>
          ) : (
            <iframe
              src={url}
              title={title}
              className="h-full w-full bg-white"
              sandbox="allow-scripts allow-forms allow-modals"
            />
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}

/**
 * Full-screen document viewer rendered into `document.body`, so it is never
 * constrained by the chat bubble or the artifacts grid cell that launched it.
 */
export function DocumentViewerModal({ artifact, url, onClose }: Props) {
  const hydrated = useSyncExternalStore(subscribeNoop, getIsClient, getIsServer);

  if (!hydrated) return null;

  return createPortal(
    <AnimatePresence>
      {artifact ? (
        <ViewerPanel
          key={artifact.artifact_id}
          artifact={artifact}
          url={url}
          onClose={onClose}
        />
      ) : null}
    </AnimatePresence>,
    document.body,
  );
}
