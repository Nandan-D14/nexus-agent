/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  ChevronDown,
  Copy,
  ExternalLink,
  Loader2,
  Monitor,
  RotateCcw,
  RotateCw,
} from "lucide-react";
import type { AppPreviewState } from "@/lib/sandbox-session";

type Props = {
  preview: AppPreviewState | null;
  restarting?: boolean;
  onRestartSandbox?: () => void;
};

function previewPath(url: string): string {
  try {
    return new URL(url).pathname || "/";
  } catch {
    return "/";
  }
}

export function AppPreviewPane({
  preview,
  restarting = false,
  onRestartSandbox,
}: Props) {
  const [copied, setCopied] = useState(false);
  const [iframeReady, setIframeReady] = useState(false);
  const [reloadNonce, setReloadNonce] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setIframeReady(false);
  }, [preview?.url, reloadNonce]);

  useEffect(() => {
    if (!menuOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [menuOpen]);

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

  const iframeSrc = useMemo(() => {
    if (!preview?.url) return "";
    const joiner = preview.url.includes("?") ? "&" : "?";
    return reloadNonce > 0 ? `${preview.url}${joiner}_r=${reloadNonce}` : preview.url;
  }, [preview?.url, reloadNonce]);

  const path = preview?.url ? previewPath(preview.url) : "/";
  const canReload = Boolean(preview?.url) && !restarting;

  const toolbar = (
    <div className="flex items-center gap-2.5 border-b border-white/5 bg-[#1a1a1c] px-3 py-2">
      <Monitor className="h-4 w-4 shrink-0 text-white/90" strokeWidth={1.75} />
      <div ref={menuRef} className="relative min-w-0 flex-1">
        <div className="flex h-8 min-w-0 items-center gap-2 rounded-lg bg-[#111113] px-2.5 ring-1 ring-white/10">
          <button
            type="button"
            onClick={() => {
              if (!canReload) return;
              setIframeReady(false);
              setReloadNonce((value) => value + 1);
            }}
            disabled={!canReload}
            title="Reload preview"
            aria-label="Reload preview"
            className="shrink-0 rounded p-0.5 text-white/90 transition-colors hover:text-white disabled:opacity-40"
          >
            <RotateCw className={`h-3.5 w-3.5 ${restarting ? "animate-spin" : ""}`} strokeWidth={1.75} />
          </button>
          <span className="min-w-0 flex-1 truncate text-[13px] font-normal text-white/90">
            {path}
          </span>
          <button
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            aria-label="Preview actions"
            aria-expanded={menuOpen}
            className="shrink-0 rounded p-0.5 text-white/80 transition-colors hover:text-white"
          >
            <ChevronDown className="h-3.5 w-3.5" strokeWidth={1.75} />
          </button>
        </div>
        {menuOpen ? (
          <div className="absolute right-0 z-30 mt-1 min-w-[188px] overflow-hidden rounded-lg border border-zinc-800 bg-[#161618] py-1 shadow-xl">
            {preview?.title ? (
              <div className="truncate px-3 py-1.5 text-[11px] text-zinc-500">
                {preview.title}
                {typeof preview.port === "number" && preview.port > 0 ? ` :${preview.port}` : ""}
              </div>
            ) : null}
            <button
              type="button"
              onClick={() => {
                setMenuOpen(false);
                void copyLink();
              }}
              disabled={!preview?.url}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-zinc-200 hover:bg-zinc-800 disabled:opacity-40"
            >
              {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
              {copied ? "Copied" : "Copy link"}
            </button>
            {onRestartSandbox ? (
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  onRestartSandbox();
                }}
                disabled={restarting}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-zinc-200 hover:bg-zinc-800 disabled:opacity-40"
              >
                {restarting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
                Restart sandbox
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
      {preview?.url ? (
        <a
          href={preview.url}
          target="_blank"
          rel="noopener noreferrer"
          title="Open in new tab"
          aria-label="Open in new tab"
          className="inline-flex shrink-0 items-center p-1 text-white/90 transition-colors hover:text-white"
        >
          <ExternalLink className="h-4 w-4" strokeWidth={1.75} />
        </a>
      ) : (
        <span className="inline-flex shrink-0 items-center p-1 text-white/30">
          <ExternalLink className="h-4 w-4" strokeWidth={1.75} />
        </span>
      )}
    </div>
  );

  if (!preview) {
    return (
      <div className="flex h-full flex-col bg-[#0a0a0c] text-zinc-100">
        {toolbar}
        <div className="flex h-full items-center justify-center bg-[#0a0a0c] px-6 text-center text-sm text-zinc-500">
          No live app preview yet. After the agent starts a server, a shareable URL
          appears here.
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-[#0a0a0c] text-zinc-100">
      {toolbar}
      <div className="relative min-h-0 flex-1 bg-zinc-950">
        {!iframeReady || restarting ? (
          <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center gap-2 text-sm text-zinc-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            {restarting ? "Restarting sandbox…" : "Loading preview…"}
          </div>
        ) : null}
        {preview.expired && onRestartSandbox ? (
          <div className="absolute inset-x-0 top-4 z-20 flex justify-center px-4">
            <button
              type="button"
              onClick={onRestartSandbox}
              disabled={restarting}
              className="inline-flex items-center gap-1.5 rounded-md border border-amber-800/80 bg-amber-950/90 px-3 py-1.5 text-[12px] font-medium text-amber-100 shadow-lg hover:border-amber-600 disabled:opacity-40"
            >
              {restarting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
              Restart sandbox
            </button>
          </div>
        ) : null}
        <iframe
          key={`${preview.url}:${reloadNonce}`}
          title={preview.title || "App preview"}
          src={iframeSrc}
          className="h-full w-full border-0 bg-white"
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox"
          onLoad={() => setIframeReady(true)}
        />
      </div>
    </div>
  );
}
