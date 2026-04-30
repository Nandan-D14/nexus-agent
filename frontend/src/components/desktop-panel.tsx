"use client";

import { useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { VisionOverlay } from "@/components/vision-overlay";

export type AgentVisualAction = {
  kind: "click" | "move" | "drag" | "typing" | "key" | "scroll" | "observe" | "browser" | "command";
  label: string;
  x?: number;
  y?: number;
  direction?: string;
  ts: number;
};

type Props = {
  streamUrl: string | null;
  analysis?: string | null;
  action?: AgentVisualAction | null;
};

const SCREEN_W = 1324;
const SCREEN_H = 968;

function clampPercent(value: number | undefined, max: number): number {
  if (typeof value !== "number" || Number.isNaN(value)) return 50;
  return Math.min(100, Math.max(0, (value / max) * 100));
}

function AgentActionOverlay({ action }: { action?: AgentVisualAction | null }) {
  if (!action) return null;

  if (action.kind === "click" || action.kind === "move" || action.kind === "drag") {
    const left = `${clampPercent(action.x, SCREEN_W)}%`;
    const top = `${clampPercent(action.y, SCREEN_H)}%`;
    return (
      <AnimatePresence mode="wait">
        <motion.div
          key={`${action.kind}-${action.ts}`}
          className="absolute z-20 pointer-events-none"
          style={{ left, top }}
          initial={{ opacity: 0, scale: 0.6, x: "-50%", y: "-50%" }}
          animate={{ opacity: 1, scale: 1, x: "-50%", y: "-50%" }}
          exit={{ opacity: 0, scale: 1.35, x: "-50%", y: "-50%" }}
          transition={{ duration: 0.28 }}
        >
          <div className="relative flex h-12 w-12 items-center justify-center">
            <span className="absolute h-12 w-12 rounded-full border border-cyan-300/70 bg-cyan-300/10 animate-ping" />
            <span className="h-3 w-3 rounded-full bg-cyan-300 shadow-[0_0_14px_rgba(103,232,249,0.9)]" />
          </div>
        </motion.div>
      </AnimatePresence>
    );
  }

  if (action.kind === "observe") {
    return (
      <motion.div
        key={`observe-${action.ts}`}
        className="absolute inset-x-0 top-0 z-20 h-16 pointer-events-none bg-gradient-to-b from-cyan-300/20 to-transparent"
        initial={{ y: "-100%", opacity: 0 }}
        animate={{ y: "620%", opacity: [0, 1, 0] }}
        transition={{ duration: 1.2, ease: "easeInOut" }}
      />
    );
  }

  const label = action.label || "Working";
  return (
    <motion.div
      key={`${action.kind}-${action.ts}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 8 }}
      className="absolute bottom-4 left-4 z-20 pointer-events-none rounded-md border border-white/10 bg-black/70 px-3 py-2 shadow-xl backdrop-blur"
    >
      <div className="flex items-center gap-2">
        <span className="h-1.5 w-1.5 rounded-full bg-amber-300 animate-pulse" />
        <span className="text-[11px] font-semibold text-zinc-200">{label}</span>
      </div>
    </motion.div>
  );
}

export function DesktopPanel({ streamUrl, analysis, action }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  if (!streamUrl) {
    return (
      <div className="relative flex flex-col items-center justify-center h-full rounded-2xl border border-zinc-800 bg-zinc-950 overflow-hidden group">
        {/* Scanning Effect Background */}
        <div className="absolute inset-0 opacity-20 pointer-events-none">
          <div className="absolute inset-0 bg-[linear-gradient(to_bottom,transparent_0%,#22d3ee_50%,transparent_100%)] bg-[length:100%_4px] animate-[scan_3s_linear_infinite]" />
        </div>

        {/* Skeleton loading placeholder */}
        <div className="w-full h-full p-8 flex flex-col gap-6 animate-pulse opacity-40">
          <div className="flex items-center gap-4">
            <div className="h-3 w-32 rounded bg-zinc-800" />
            <div className="h-[1px] flex-1 bg-zinc-800" />
          </div>
          <div className="flex-1 rounded-xl bg-zinc-900/50 border border-zinc-800/50" />
          <div className="flex justify-between items-center">
            <div className="flex gap-3">
              <div className="h-2 w-16 rounded bg-zinc-800" />
              <div className="h-2 w-12 rounded bg-zinc-800" />
            </div>
            <div className="h-2 w-24 rounded bg-zinc-800" />
          </div>
        </div>

        <div className="absolute flex flex-col items-center gap-4">
          <div className="relative">
            <div className="absolute inset-0 bg-cyan-500/20 blur-xl animate-pulse" />
            <div className="relative w-12 h-12 rounded-full border border-cyan-500/30 flex items-center justify-center">
              <div className="w-2 h-2 rounded-full bg-cyan-500 shadow-[0_0_15px_rgba(34,211,238,0.8)]" />
            </div>
          </div>
          <div className="space-y-1 text-center">
            <p className="text-xs font-black text-cyan-400 uppercase tracking-[0.3em]">Establishing Link</p>
            <p className="text-[10px] text-zinc-600 font-bold uppercase tracking-widest">Secure VNC Protocol Initialization...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="relative h-full rounded-2xl border border-zinc-800 overflow-hidden bg-black shadow-inner shadow-black/80 group">
      {/* LIVE indicator */}
      <div className="absolute top-4 right-4 z-10 flex items-center gap-2.5 bg-black/60 backdrop-blur-md px-3 py-1.5 rounded-full border border-white/5 transition-transform group-hover:scale-105">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-40" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]" />
        </span>
        <span className="text-emerald-400 text-[10px] font-black uppercase tracking-[0.2em]">
          Live Stream
        </span>
      </div>

      <iframe
        src={streamUrl}
        className="w-full h-full border-0 grayscale-[0.15] contrast-[1.1] brightness-[1.05]"
        allow="clipboard-read; clipboard-write"
        title="CoComputer Desktop"
      />
      <AgentActionOverlay action={action} />
      
      <VisionOverlay analysis={analysis || null} containerRef={containerRef} />
      
      {/* Subtle Overlay Border */}
      <div className="absolute inset-0 border border-white/5 pointer-events-none rounded-2xl" />
    </div>
  );
}
