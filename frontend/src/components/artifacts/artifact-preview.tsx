/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Download, Loader2 } from "lucide-react";
import type { RunArtifact } from "@/lib/message-types";
import {
  downloadArtifactFile,
  isPresentationArtifact,
  previewKind,
  resolveArtifactUrl,
} from "@/lib/artifact-url";
import { ArtifactIcon, artifactBadge } from "./artifact-icon";
import { MarkdownPreview } from "./markdown-preview";
import { SlidePreview } from "./slide-preview";
import { SpreadsheetPreview } from "./spreadsheet-preview";

type Props = {
  artifact: RunArtifact;
  url?: string | null;
  className?: string;
  onUrlChange?: (url: string | null) => void;
};

export function ArtifactPreview({
  artifact,
  url: initialUrl,
  className,
  onUrlChange,
}: Props) {
  const [url, setUrl] = useState<string | null>(initialUrl ?? null);
  const [loading, setLoading] = useState(!initialUrl);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const onUrlChangeRef = useRef(onUrlChange);
  onUrlChangeRef.current = onUrlChange;
  const kind = previewKind(artifact);
  const title = artifact.title || artifact.kind.replace(/_/g, " ");
  const slideCount = Number(artifact.metadata?.slide_count);
  const presentation = isPresentationArtifact(artifact);

  useEffect(() => {
    if (kind === "sheet" || kind === "markdown") {
      setUrl(null);
      setLoading(false);
      setError(null);
      onUrlChangeRef.current?.(null);
      return;
    }
    if (initialUrl) {
      setUrl(initialUrl);
      setLoading(false);
      onUrlChangeRef.current?.(initialUrl);
      return;
    }
    if (kind === "none") {
      setLoading(false);
      onUrlChangeRef.current?.(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    resolveArtifactUrl(artifact, true)
      .then((resolved) => {
        if (cancelled) return;
        setUrl(resolved);
        onUrlChangeRef.current?.(resolved);
        if (!resolved) setError("Could not load a preview for this file.");
      })
      .catch(() => {
        if (!cancelled) {
          setError("Could not load a preview for this file.");
          onUrlChangeRef.current?.(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [artifact, initialUrl, kind]);

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
    <div className={className ?? "relative min-h-0 flex-1 bg-background-full"}>
      {kind === "sheet" ? (
        <SpreadsheetPreview artifact={artifact} />
      ) : kind === "markdown" ? (
        <MarkdownPreview artifact={artifact} />
      ) : loading ? (
        <div className="flex h-full items-center justify-center gap-2 text-sm text-zinc-400">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading preview…
        </div>
      ) : error ? (
        <div className="flex h-full items-center justify-center px-6 text-center text-sm text-red-400">
          {error}
        </div>
      ) : kind === "none" ? (
        <div className="flex h-full flex-col items-center justify-center gap-5 px-6 text-center">
          <ArtifactIcon artifact={artifact} className="h-16 w-16" />
          <div>
            <p className="text-[15px] font-medium text-zinc-100">{title}</p>
            <p className="mt-1 text-[12px] uppercase tracking-wide text-zinc-500">
              {artifactBadge(artifact)}
            </p>
            <p className="mt-3 max-w-sm text-[13px] text-zinc-500">
              Preview isn&apos;t available for this file type. Download it to open
              in your desktop app.
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
          className="h-full w-full bg-zinc-200"
          aria-label={title}
        >
          <embed src={url} type="application/pdf" className="h-full w-full" />
        </object>
      ) : kind === "image" ? (
        <div className="flex h-full items-center justify-center bg-[#111113] p-6">
          <img
            src={url}
            alt={title}
            className="max-h-full max-w-full rounded-lg object-contain shadow-2xl"
          />
        </div>
      ) : presentation ? (
        <SlidePreview
          url={url}
          title={title}
          slideCount={Number.isFinite(slideCount) ? slideCount : undefined}
        />
      ) : (
        <iframe
          src={url}
          title={title}
          className="h-full w-full bg-white"
          sandbox="allow-scripts allow-forms allow-modals"
        />
      )}
    </div>
  );
}
