/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Check, Clipboard, Code2, RefreshCw, ZoomIn, ZoomOut } from "lucide-react";
import mermaid from "mermaid";

type Props = {
  chart: string;
};

// Initialize mermaid once on the client
let isMermaidInitialized = false;
function initMermaid() {
  if (typeof window !== "undefined" && !isMermaidInitialized) {
    mermaid.initialize({
      startOnLoad: false,
      theme: "dark",
      securityLevel: "loose",
      fontFamily: "var(--font-sans, system-ui, sans-serif)",
    });
    isMermaidInitialized = true;
  }
}

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
    initMermaid();

    const renderChart = async () => {
      if (!chart.trim()) {
        setSvg("");
        setError(null);
        return;
      }

      try {
        const id = `mermaid_${uniqueId}_${Date.now()}`;
        const { svg: renderedSvg } = await mermaid.render(id, chart.trim());
        if (active) {
          setSvg(renderedSvg);
          setError(null);
        }
      } catch (err: unknown) {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to render diagram");
          setSvg("");
        }
      }
    };

    void renderChart();

    return () => {
      active = false;
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
