/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, ExternalLink, Loader2, Maximize2 } from "lucide-react";
import { TodoList } from "@/components/todo-list";
import { ArtifactPreview } from "@/components/artifacts/artifact-preview";
import { ArtifactIconTile, artifactBadge } from "@/components/artifacts/artifact-icon";
import { DocumentViewerModal } from "@/components/artifacts/document-viewer-modal";
import { MarkdownPreview } from "@/components/artifacts/markdown-preview";
import {
  downloadArtifactFile,
  previewKind,
  resolveArtifactUrl,
} from "@/lib/artifact-url";
import { useSessionCanvas } from "@/lib/session-canvas-context";
import {
  canvasKindLabel,
  documentFromArtifact,
  isCanvasArtifact,
  looksLikeHtml,
  type SessionCanvasDocument,
  type SessionCanvasKind,
} from "@/lib/session-canvas";
import type { RunArtifact } from "@/lib/message-types";
import { cn } from "@/lib/utils";

const KIND_ORDER: SessionCanvasKind[] = ["document", "file", "plan"];

const ICON_BUTTON =
  "flex h-8 w-8 items-center justify-center rounded-lg text-text-tertiary transition-colors hover:bg-background-secondary-hover hover:text-text-primary disabled:opacity-50";

type Props = {
  artifacts?: RunArtifact[];
};

function isTextLikeDocument(doc: SessionCanvasDocument): boolean {
  if (doc.markdown) return true;
  const path = `${doc.path || ""} ${doc.title || ""}`.toLowerCase();
  if (/\.(md|markdown|txt|html)$/i.test(path)) return true;
  return doc.kind === "file" || doc.kind === "plan";
}

function HtmlFrame({ html, title }: { html: string; title: string }) {
  const url = useMemo(() => {
    const blob = new Blob([html], { type: "text/html;charset=utf-8" });
    return URL.createObjectURL(blob);
  }, [html]);

  useEffect(() => {
    return () => URL.revokeObjectURL(url);
  }, [url]);

  return (
    <iframe
      src={url}
      title={title}
      className="h-full w-full bg-white"
      sandbox="allow-scripts allow-forms allow-modals"
    />
  );
}

function TextCanvasBody({ doc }: { doc: SessionCanvasDocument }) {
  const [text, setText] = useState(doc.markdown ?? "");
  const [loading, setLoading] = useState(!doc.markdown && Boolean(doc.artifact));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (doc.markdown) {
      setText(doc.markdown);
      setLoading(false);
      setError(null);
      return;
    }
    const artifact = doc.artifact;
    if (!artifact) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    resolveArtifactUrl(artifact, false)
      .then(async (url) => {
        if (cancelled) return;
        if (!url || url.includes("storage.googleapis.com")) {
          setText(artifact.preview || "");
          return;
        }
        const res = await fetch(url);
        if (!res.ok) throw new Error("fetch failed");
        const body = await res.text();
        if (!cancelled) setText(body);
      })
      .catch(() => {
        if (!cancelled) {
          setError("Could not load this file.");
          setText(artifact.preview || "");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [doc.artifact, doc.markdown]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-text-tertiary">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading document…
      </div>
    );
  }

  if (error && !text) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center text-sm text-red-400">
        {error}
      </div>
    );
  }

  if (looksLikeHtml(text) || /\.html$/i.test(doc.path || doc.title)) {
    return (
      <div className="h-full min-h-0">
        <HtmlFrame html={text} title={doc.title} />
      </div>
    );
  }

  return <MarkdownPreview content={text} />;
}

function CanvasBody({
  doc,
  onUrlChange,
}: {
  doc: SessionCanvasDocument;
  onUrlChange: (url: string | null) => void;
}) {
  const preview = doc.artifact ? previewKind(doc.artifact) : "none";
  if (doc.markdown || (isTextLikeDocument(doc) && preview === "none")) {
    return <TextCanvasBody doc={doc} />;
  }
  if (doc.artifact) {
    return (
      <ArtifactPreview
        artifact={doc.artifact}
        onUrlChange={onUrlChange}
        className="relative h-full min-h-0 flex-1 bg-background-full"
      />
    );
  }
  return (
    <div className="flex h-full items-center justify-center px-6 text-center text-sm text-text-secondary">
      This document has no preview yet.
    </div>
  );
}

export function SessionCanvas({ artifacts = [] }: Props) {
  const canvas = useSessionCanvas();
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  const documents = useMemo(() => {
    if (canvas && canvas.documents.length > 0) return canvas.documents;
    return artifacts.filter(isCanvasArtifact).map(documentFromArtifact);
  }, [artifacts, canvas]);

  const active = useMemo(() => {
    if (documents.length === 0) return null;
    const match = documents.find((doc) => doc.id === canvas?.activeId);
    return match ?? documents[documents.length - 1];
  }, [canvas?.activeId, documents]);

  const presentKinds = useMemo(() => {
    const found = new Set(documents.map((doc) => doc.kind));
    return KIND_ORDER.filter((kind) => found.has(kind));
  }, [documents]);

  useEffect(() => {
    setPreviewUrl(null);
  }, [active?.id]);

  const selectKind = useCallback(
    (kind: SessionCanvasKind) => {
      const latest = [...documents].reverse().find((doc) => doc.kind === kind);
      if (latest) canvas?.selectDocument(latest.id);
    },
    [canvas, documents],
  );

  const handleDownload = useCallback(async () => {
    if (!active?.artifact) return;
    setDownloading(true);
    try {
      await downloadArtifactFile(active.artifact);
    } catch (e) {
      console.error("Download failed", e);
    } finally {
      setDownloading(false);
    }
  }, [active?.artifact]);

  if (!active) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center text-sm text-text-secondary">
        Reports and documents the agent creates will open here.
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-background-full">
      <div className="flex shrink-0 items-center gap-3 border-b border-separator-border px-4 py-2.5">
        {presentKinds.length > 0 ? (
          <div className="flex shrink-0 items-center gap-1 rounded-lg bg-background-secondary-default p-0.5">
            {presentKinds.map((kind) => (
              <button
                key={kind}
                type="button"
                onClick={() => selectKind(kind)}
                className={cn(
                  "rounded-md px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide transition-colors",
                  active.kind === kind
                    ? "bg-background-primary-default text-text-primary shadow-sm"
                    : "text-text-secondary hover:text-text-primary",
                )}
              >
                {canvasKindLabel(kind)}
              </button>
            ))}
          </div>
        ) : null}

        {active.artifact ? (
          <ArtifactIconTile
            artifact={active.artifact}
            className="h-8 w-8"
            iconClassName="w-4 h-4"
          />
        ) : null}

        <button
          type="button"
          onClick={() => canvas?.openViewer()}
          className="min-w-0 flex-1 text-left"
          title="Open preview"
        >
          <div className="truncate text-[13px] font-semibold text-text-primary" title={active.title}>
            {active.title}
          </div>
          <div className="truncate text-[11px] text-text-secondary">
            {active.artifact ? artifactBadge(active.artifact) : canvasKindLabel(active.kind)}
            {active.path ? ` · ${active.path}` : ""}
          </div>
        </button>

        <div className="flex shrink-0 items-center gap-1">
          {previewUrl ? (
            <a
              href={previewUrl}
              target="_blank"
              rel="noreferrer"
              className={ICON_BUTTON}
              title="Open in new tab"
            >
              <ExternalLink className="h-4 w-4" />
            </a>
          ) : null}
          {active.artifact ? (
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
            onClick={() => canvas?.openViewer()}
            className={ICON_BUTTON}
            title="Open popup preview"
          >
            <Maximize2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        <div className="relative h-full min-h-0 flex-1">
          <CanvasBody doc={active} onUrlChange={setPreviewUrl} />
        </div>
        {active.kind === "plan" && canvas && canvas.todoItems.length > 0 ? (
          <div className="shrink-0 border-t border-separator-border bg-background-secondary-default px-4 py-3">
            <TodoList items={canvas.todoItems} defaultExpanded />
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** Always-mounted overlay so chat cards can open the popup even before the Document tab is visible. */
export function SessionCanvasViewer() {
  const canvas = useSessionCanvas();
  const active = useMemo(() => {
    if (!canvas || canvas.documents.length === 0) return null;
    return canvas.documents.find((doc) => doc.id === canvas.activeId) ?? canvas.documents[canvas.documents.length - 1];
  }, [canvas]);

  if (!canvas) return null;

  return (
    <DocumentViewerModal
      artifact={canvas.viewerOpen ? active?.artifact ?? null : null}
      markdown={
        canvas.viewerOpen && !active?.artifact ? active?.markdown || null : null
      }
      title={active?.title}
      onClose={canvas.closeViewer}
    />
  );
}
