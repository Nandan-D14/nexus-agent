/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Check, Clipboard, Code2, RefreshCw, ZoomIn, ZoomOut } from "lucide-react";
import type { Mermaid } from "mermaid";

type Props = {
  chart: string;
};

// Chart text is model output. "strict" makes mermaid HTML-encode labels,
// disable click handlers, and DOMPurify the generated SVG before we inject it.
// mermaid (~1 MB) is loaded on first use instead of shipping with the chat.
let mermaidPromise: Promise<Mermaid> | null = null;
function loadMermaid(): Promise<Mermaid> {
  if (!mermaidPromise) {
    mermaidPromise = import("mermaid").then(({ default: mermaid }) => {
      mermaid.initialize({
        startOnLoad: false,
        theme: "dark",
        securityLevel: "strict",
        fontFamily: "var(--font-sans, system-ui, sans-serif)",
      });
      return mermaid;
    });
  }
  return mermaidPromise;
}

// Streaming re-renders the fence on every token; wait for the text to settle.
const RENDER_DEBOUNCE_MS = 250;

export function MermaidDiagram({ chart }: Props) {
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [showCode, setShowCode] = useState(false);
  const [copied, setCopied] = useState(false);
  const [zoom, setZoom] = useState(1);
  const uniqueId = useId().replace(/:/g, "_");
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;

    const renderChart = async () => {
      if (!chart.trim()) {
        setSvg("");
        setError(null);
        return;
      }

      const id = `mermaid_${uniqueId}_${Date.now()}`;
      try {
        const mermaid = await loadMermaid();
        const { svg: renderedSvg } = await mermaid.render(id, chart.trim());
        if (active) {
          setSvg(renderedSvg);
          setError(null);
        }
      } catch (err: unknown) {
        // A failed render can leave mermaid's scratch node in <body>.
        document.getElementById(`d${id}`)?.remove();
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to render diagram");
          setSvg("");
        }
      }
    };

    const timer = window.setTimeout(() => void renderChart(), RENDER_DEBOUNCE_MS);

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [chart, uniqueId]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(chart);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard denied
    }
  };

  return (
    <div className="my-4 overflow-hidden rounded-xl border border-zinc-200 bg-zinc-950 shadow-sm dark:border-zinc-800">
      {/* Header bar */}
      <div className="flex h-9 items-center justify-between border-b border-zinc-800/80 bg-zinc-900/90 px-3.5 text-xs text-zinc-400">
        <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-zinc-300">
          Diagram
        </span>

        <div className="flex items-center gap-1.5">
          <button
            type="button"
            title="Zoom In"
            onClick={() => setZoom((z) => Math.min(2.5, z + 0.2))}
            className="flex items-center rounded-md p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
          >
            <ZoomIn className="size-3.5" aria-hidden />
          </button>

          <button
            type="button"
            title="Zoom Out"
            onClick={() => setZoom((z) => Math.max(0.5, z - 0.2))}
            className="flex items-center rounded-md p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
          >
            <ZoomOut className="size-3.5" aria-hidden />
          </button>

          <button
            type="button"
            title="Reset Zoom"
            onClick={() => setZoom(1)}
            className="flex items-center rounded-md p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
          >
            <RefreshCw className="size-3.5" aria-hidden />
          </button>

          <button
            type="button"
            title={showCode ? "Show Diagram" : "View Source Code"}
            onClick={() => setShowCode((s) => !s)}
            className={`flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] font-medium transition-colors ${
              showCode
                ? "bg-zinc-800 text-zinc-200"
                : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
            }`}
          >
            <Code2 className="size-3.5" aria-hidden />
            <span>Code</span>
          </button>

          <button
            type="button"
            onClick={() => void handleCopy()}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
          >
            {copied ? (
              <>
                <Check className="size-3.5 text-emerald-400" aria-hidden />
                <span className="text-emerald-400">Copied</span>
              </>
            ) : (
              <>
                <Clipboard className="size-3.5" aria-hidden />
                <span>Copy</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Body */}
      {showCode ? (
        <div className="overflow-x-auto p-4 font-mono text-[12.5px] leading-relaxed text-zinc-300">
          <pre className="m-0 bg-transparent p-0">{chart}</pre>
        </div>
      ) : error ? (
        <div className="p-4 text-xs text-amber-400">
          <p className="font-semibold">Unable to render diagram</p>
          <pre className="mt-2 overflow-x-auto rounded bg-zinc-900 p-2 font-mono text-zinc-400">
            {chart}
          </pre>
        </div>
      ) : svg ? (
        <div
          ref={containerRef}
          className="flex justify-center overflow-x-auto p-6 transition-transform"
          style={{ transform: `scale(${zoom})`, transformOrigin: "center top" }}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      ) : (
        <div className="flex h-32 items-center justify-center text-xs text-zinc-500">
          Rendering diagram...
        </div>
      )}
    </div>
  );
}
