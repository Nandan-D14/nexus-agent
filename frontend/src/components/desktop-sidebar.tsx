"use client";

import type { SessionPhase } from "@/lib/message-types";

/* ------------------------------------------------------------------ */
/*  Types                                                               */
/* ------------------------------------------------------------------ */

type Props = {
  open: boolean;
  onToggle: () => void;
  phase: SessionPhase;
  activeAgent: string;
  isConnected: boolean;
  onAnalyzeScreen: () => void;
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                             */
/* ------------------------------------------------------------------ */

const PHASE_CONFIG: Record<
  SessionPhase,
  { label: string; dotClass: string; textClass: string }
> = {
  idle: {
    label: "Idle",
    dotClass: "bg-zinc-600",
    textClass: "text-zinc-500",
  },
  listening: {
    label: "Listening",
    dotClass: "bg-cyan-400 animate-pulse",
    textClass: "text-cyan-400",
  },
  thinking: {
    label: "Thinking",
    dotClass: "bg-cyan-400 animate-pulse",
    textClass: "text-cyan-400",
  },
  acting: {
    label: "Acting",
    dotClass: "bg-amber-400 animate-pulse",
    textClass: "text-amber-400",
  },
  done: {
    label: "Done",
    dotClass: "bg-emerald-400",
    textClass: "text-emerald-400",
  },
};

/* ------------------------------------------------------------------ */
/*  Icon helpers                                                        */
/* ------------------------------------------------------------------ */

function ScreenshotIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      className={className}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M3 7V5a2 2 0 012-2h2M13 3h2a2 2 0 012 2v2M17 13v2a2 2 0 01-2 2h-2M7 17H5a2 2 0 01-2-2v-2"
      />
      <circle cx="10" cy="10" r="2.5" />
    </svg>
  );
}

function AnalyzeIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      className={className}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M10 12a2 2 0 100-4 2 2 0 000 4z"
      />
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M2 10s3-6 8-6 8 6 8 6-3 6-8 6-8-6-8-6z"
      />
    </svg>
  );
}

function ChevronIcon({
  open,
  className,
}: {
  open: boolean;
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="currentColor"
      className={`${className} transition-transform duration-300 ${open ? "rotate-180" : ""}`}
    >
      <path
        fillRule="evenodd"
        d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
        clipRule="evenodd"
      />
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/*  Component                                                           */
/* ------------------------------------------------------------------ */

export function DesktopSidebar({
  open,
  onToggle,
  phase,
  activeAgent,
  isConnected,
  onAnalyzeScreen,
}: Props) {
  const phaseInfo = PHASE_CONFIG[phase];

  return (
    <div
      className={`
        flex flex-col shrink-0 bg-card dark:bg-[#09090b] border-r border-card-border dark:border-[#1c1c1e]
        transition-all duration-300 ease-in-out overflow-hidden
        ${open ? "w-44" : "w-9"}
      `}
    >
      {/* ── Toggle button ── */}
      <button
        suppressHydrationWarning
        onClick={onToggle}
        className="flex items-center justify-center h-9 w-full border-b border-card-border dark:border-[#1c1c1e] text-muted dark:text-zinc-500 hover:text-foreground dark:hover:text-zinc-200 hover:bg-black/5 dark:hover:bg-zinc-900/50 transition-colors shrink-0"
        title={open ? "Collapse sidebar" : "Expand sidebar"}
      >
        <ChevronIcon open={open} className="w-3.5 h-3.5" />
      </button>

      {/* ── Connection status dot ── */}
      <div
        className={`flex items-center border-b border-card-border dark:border-[#1c1c1e] shrink-0 ${
          open ? "gap-2.5 px-3 py-2" : "justify-center py-2"
        }`}
        title={isConnected ? "Connected" : "Disconnected"}
      >
        <span
          className={`w-2 h-2 rounded-full shrink-0 ${
            isConnected ? "bg-emerald-400 animate-pulse" : "bg-zinc-600"
          }`}
        />
        {open && (
          <span className="text-[10px] font-bold uppercase tracking-widest text-muted dark:text-zinc-400 truncate">
            {isConnected ? "Live" : "Offline"}
          </span>
        )}
      </div>

      {/* ── Phase indicator ── */}
      <div
        className={`flex items-center border-b border-card-border dark:border-[#1c1c1e] shrink-0 ${
          open ? "gap-2.5 px-3 py-2" : "justify-center py-2"
        }`}
        title={`Phase: ${phaseInfo.label}`}
      >
        <span
          className={`w-2 h-2 rounded-full shrink-0 ${phaseInfo.dotClass}`}
        />
        {open && (
          <span
            className={`text-[10px] font-bold uppercase tracking-widest truncate ${phaseInfo.textClass}`}
          >
            {phaseInfo.label}
          </span>
        )}
      </div>

      {/* ── Active agent ── */}
      {activeAgent && activeAgent !== "nexus" && (
        <div
          className={`flex items-center border-b border-card-border dark:border-[#1c1c1e] shrink-0 ${
            open ? "gap-2 px-3 py-2" : "justify-center py-2"
          }`}
          title={`Agent: ${activeAgent}`}
        >
          <span className="w-2 h-2 rounded-full bg-cyan-500 shrink-0" />
          {open && (
            <span className="text-[10px] font-medium text-foreground dark:text-zinc-300 truncate leading-tight">
              {activeAgent.replace(/_/g, " ")}
            </span>
          )}
        </div>
      )}

      {/* ── Spacer ── */}
      <div className="flex-1" />

      {/* ── Action buttons ── */}
      <div className={`flex flex-col border-t border-card-border dark:border-[#1c1c1e] py-2 gap-1 ${open ? "px-2" : "px-1"}`}>
        {/* Analyze screen */}
        <button
          onClick={onAnalyzeScreen}
          disabled={!isConnected}
          title="Analyze screen"
          className={`flex items-center rounded-md text-muted dark:text-zinc-400 hover:text-cyan-600 dark:hover:text-cyan-400 hover:bg-black/5 dark:hover:bg-zinc-800/60 disabled:opacity-30 disabled:cursor-not-allowed transition-colors ${
            open ? "gap-2 px-2 py-1.5" : "justify-center p-1.5"
          }`}
        >
          <AnalyzeIcon className="w-4 h-4 shrink-0" />
          {open && (
            <span className="text-[10px] font-bold uppercase tracking-widest">
              Analyze
            </span>
          )}
        </button>

        {/* Screenshot */}
        <button
          onClick={onAnalyzeScreen}
          disabled={!isConnected}
          title="Take screenshot"
          className={`flex items-center rounded-md text-muted dark:text-zinc-400 hover:text-cyan-600 dark:hover:text-cyan-400 hover:bg-black/5 dark:hover:bg-zinc-800/60 disabled:opacity-30 disabled:cursor-not-allowed transition-colors ${
            open ? "gap-2 px-2 py-1.5" : "justify-center p-1.5"
          }`}
        >
          <ScreenshotIcon className="w-4 h-4 shrink-0" />
          {open && (
            <span className="text-[10px] font-bold uppercase tracking-widest">
              Screenshot
            </span>
          )}
        </button>
      </div>
    </div>
  );
}
