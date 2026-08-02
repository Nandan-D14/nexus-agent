/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useState } from "react";
import { ExternalLink, Loader2, X } from "lucide-react";
import type { RunArtifact } from "@/lib/message-types";
import { resolveArtifactUrl } from "@/lib/artifact-url";

type Props = {
  artifact: RunArtifact;
  /** Prefetched blob/signed URL; resolved on mount if omitted. */
  url?: string | null;
  title?: string;
  onClose?: () => void;
  className?: string;
  heightClassName?: string;
};

/**
 * In-page PDF preview via blob URL + native browser PDF renderer.
 * Avoids sandboxed iframes that block PDF plugins.
 */
export function PdfArtifactViewer({
  artifact,
  url: initialUrl,
  title,
  onClose,
  className,
  heightClassName = "h-[520px]",
}: Props) {
  const [url, setUrl] = useState<string | null>(initialUrl ?? null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!initialUrl);

  useEffect(() => {
    if (initialUrl) {
      setUrl(initialUrl);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    resolveArtifactUrl(artifact)
      .then((resolved) => {
        if (cancelled) return;
        if (!resolved) {
          setError("Could not load PDF preview.");
          return;
        }
        setUrl(resolved);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load PDF preview.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [artifact, initialUrl]);

  const displayTitle = title || artifact.title || "PDF preview";

  return (
    <div
      className={
        className ||
        "mt-3 rounded-xl overflow-hidden border border-zinc-700 bg-black/30"
      }
    >
      <div className="flex items-center justify-between px-4 py-2 bg-zinc-900/80 border-b border-zinc-800">
        <span className="text-xs font-semibold text-zinc-300 truncate">
          {displayTitle}
        </span>
        <div className="flex items-center gap-2">
          {url && (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 transition-colors"
            >
              <ExternalLink className="w-3 h-3" />
              Open
            </a>
          )}
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

      {loading && (
        <div
          className={`flex items-center justify-center gap-2 text-sm text-zinc-400 bg-[#111] ${heightClassName}`}
        >
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading preview…
        </div>
      )}

      {!loading && error && (
        <div
          className={`flex items-center justify-center text-sm text-red-400 bg-[#111] px-4 ${heightClassName}`}
        >
          {error}
        </div>
      )}

      {!loading && !error && url && (
        <object
          data={url}
          type="application/pdf"
          className={`w-full bg-white ${heightClassName}`}
          aria-label={displayTitle}
        >
          <embed src={url} type="application/pdf" className={`w-full ${heightClassName}`} />
        </object>
      )}
    </div>
  );
}
