"use client";

import { useState } from "react";

type Props = {
  taskId: string;
  description: string;
  estimatedSeconds: number;
  agent: string;
  onRespond: (taskId: string, approved: boolean) => void;
};

function formatEstimatedTime(seconds: number): string {
  if (seconds < 60) return `${seconds} sec`;
  return `~${Math.round(seconds / 60)} min`;
}

export function PermissionCard({
  taskId,
  description,
  estimatedSeconds,
  agent,
  onRespond,
}: Props) {
  const [response, setResponse] = useState<"approved" | "denied" | null>(null);

  function handleRespond(approved: boolean) {
    setResponse(approved ? "approved" : "denied");
    onRespond(taskId, approved);
  }

  const resolved = response !== null;

  return (
    <div
      className={[
        "relative rounded-lg border bg-[#09090b] p-3 space-y-2.5 max-w-sm",
        "transition-all duration-300",
        resolved
          ? response === "approved"
            ? "border-emerald-500/30"
            : "border-red-500/30"
          : "border-amber-500/40 shadow-[0_0_12px_rgba(245,158,11,0.06)]",
      ].join(" ")}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div
            className={[
              "w-1.5 h-1.5 rounded-full transition-colors duration-300",
              resolved
                ? response === "approved"
                  ? "bg-emerald-500"
                  : "bg-red-500"
                : "bg-amber-500 animate-pulse",
            ].join(" ")}
          />
          <span className="text-[9px] font-black uppercase tracking-[0.15em] text-amber-500">
            Permission Request
          </span>
        </div>
        {resolved && (
          <span
            className={[
              "text-[9px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded",
              "transition-opacity duration-300",
              response === "approved"
                ? "bg-emerald-500/10 text-emerald-400"
                : "bg-red-500/10 text-red-400",
            ].join(" ")}
          >
            {response === "approved" ? "Approved" : "Denied"}
          </span>
        )}
      </div>

      {/* Description */}
      <p className="text-zinc-300 text-sm leading-relaxed">{description}</p>

      {/* Meta row */}
      <div className="flex items-center gap-3 text-[10px] font-bold uppercase tracking-wider text-zinc-500">
        <div className="flex items-center gap-1.5">
          <span className="text-zinc-600">Agent</span>
          <span className="text-zinc-300">{agent}</span>
        </div>
        <div className="w-px h-3 bg-zinc-800" />
        <div className="flex items-center gap-1.5">
          <span className="text-zinc-600">Est.</span>
          <span className="text-zinc-300">
            {formatEstimatedTime(estimatedSeconds)}
          </span>
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-2 pt-0.5">
        <button
          disabled={resolved}
          onClick={() => handleRespond(true)}
          className={[
            "flex-1 text-[11px] font-bold uppercase tracking-widest py-1.5 px-3 rounded-md",
            "border transition-all duration-200",
            resolved
              ? response === "approved"
                ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400 cursor-default"
                : "bg-zinc-900 border-zinc-800 text-zinc-600 cursor-default"
              : "bg-emerald-500/10 border-emerald-500/25 text-emerald-400 hover:bg-emerald-500/20 hover:border-emerald-500/40 hover:shadow-[0_0_10px_rgba(16,185,129,0.1)] active:scale-[0.98]",
          ].join(" ")}
        >
          {resolved && response === "approved" ? "Approved" : "Approve"}
        </button>
        <button
          disabled={resolved}
          onClick={() => handleRespond(false)}
          className={[
            "flex-1 text-[11px] font-bold uppercase tracking-widest py-1.5 px-3 rounded-md",
            "border transition-all duration-200",
            resolved
              ? response === "denied"
                ? "bg-red-500/10 border-red-500/20 text-red-400 cursor-default"
                : "bg-zinc-900 border-zinc-800 text-zinc-600 cursor-default"
              : "bg-red-500/5 border-zinc-800 text-red-400 hover:bg-red-500/10 hover:border-red-500/30 hover:shadow-[0_0_10px_rgba(239,68,68,0.08)] active:scale-[0.98]",
          ].join(" ")}
        >
          {resolved && response === "denied" ? "Denied" : "Deny"}
        </button>
      </div>
    </div>
  );
}
