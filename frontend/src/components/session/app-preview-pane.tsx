/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Copy, ExternalLink, Globe, Loader2 } from "lucide-react";
import type { AppPreviewState } from "@/lib/sandbox-session";

type Props = {
  preview: AppPreviewState | null;
};

export function AppPreviewPane({ preview }: Props) {
  const [copied, setCopied] = useState(false);
  const [iframeReady, setIframeReady] = useState(false);

  useEffect(() => {
    setIframeReady(false);
  }, [preview?.url]);

  const copyLink = useCallback(async () => {
    if (!preview?.url) return;
    try {
      await navigator.clipboard.writeText(preview.url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }, [preview?.url]);

  if (!preview) {
    return (
      <div className="flex h-full items-center justify-center bg-[#0a0a0c] px-6 text-center text-sm text-zinc-500">
        No live app preview yet. After the agent starts a server, a shareable URL
        appears here.
      </div>
    );
  }

  const portLabel =
    typeof preview.port === "number" && preview.port > 0 ? `:${preview.port}` : "";

  return (
    <div className="flex h-full flex-col bg-[#0a0a0c] text-zinc-100">
      <div className="flex items-center justify-between gap-3 border-b border-zinc-800/80 bg-[#141416] px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <Globe className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
          <span className="truncate text-[12px] font-medium text-zinc-200">
            {preview.title || "App preview"}
          </span>
          {portLabel ? (
            <span className="shrink-0 rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[10px] text-zinc-400">
              {portLabel}
            </span>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            onClick={() => void copyLink()}
            disabled={!preview.url}
            className="inline-flex items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-900/70 px-2 py-1 text-[11px] font-medium text-zinc-300 transition-colors hover:border-zinc-700 hover:text-zinc-100 disabled:opacity-40"
          >
            {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
            {copied ? "Copied" : "Copy link"}
          </button>
          <a
            href={preview.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-900/70 px-2 py-1 text-[11px] font-medium text-zinc-300 transition-colors hover:border-zinc-700 hover:text-zinc-100"
          >
            <ExternalLink className="h-3 w-3" />
            Open
          </a>
        </div>
      </div>

      {preview.expired ? (
        <div className="border-b border-amber-900/40 bg-amber-950/40 px-4 py-2 text-[11px] text-amber-200">
          This preview URL died with the sandbox. Restart the app and publish the
          preview again.
        </div>
      ) : (
        <div className="border-b border-zinc-800/60 bg-[#101012] px-4 py-1.5 font-mono text-[10px] text-zinc-500">
          Live only while this session sandbox is running
          {preview.url ? ` · ${preview.url}` : ""}
        </div>
      )}

      <div className="relative min-h-0 flex-1 bg-zinc-950">
        {preview.expired ? (
          <div className="flex h-full items-center justify-center px-6 text-center text-sm text-zinc-500">
            The iframe is unavailable because the sandbox is gone. Use Copy link
            only if you still have a running VM.
          </div>
        ) : (
          <>
            {!iframeReady ? (
              <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center gap-2 text-sm text-zinc-500">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading preview…
              </div>
            ) : null}
            <iframe
              key={preview.url}
              title={preview.title || "App preview"}
              src={preview.url}
              className="h-full w-full border-0 bg-white"
              sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox"
              onLoad={() => setIframeReady(true)}
            />
          </>
        )}
      </div>
    </div>
  );
}
