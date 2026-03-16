"use client";

type Phase = "idle" | "listening" | "thinking" | "acting" | "done";

type Props = {
  phase: Phase;
  isConnected: boolean;
  tokenQuota?: { limit: number; used: number; remaining: number } | null;
};

const STEPS: { key: Phase; label: string }[] = [
  { key: "listening", label: "Mic" },
  { key: "thinking", label: "Neural" },
  { key: "acting", label: "Kernel" },
  { key: "done", label: "Sync" },
];

const STEP_ORDER: Phase[] = ["listening", "thinking", "acting", "done"];

function getStepState(
  step: Phase,
  currentPhase: Phase,
): "active" | "past" | "future" {
  if (currentPhase === "idle") return "future";
  const currentIdx = STEP_ORDER.indexOf(currentPhase);
  const stepIdx = STEP_ORDER.indexOf(step);
  if (stepIdx === currentIdx) return "active";
  if (stepIdx < currentIdx) return "past";
  return "future";
}

function formatTokenCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function StatusBar({ phase, isConnected, tokenQuota }: Props) {
  const pct = tokenQuota ? Math.min(100, (tokenQuota.used / tokenQuota.limit) * 100) : 0;
  const isWarning = pct >= 80;
  const isExceeded = tokenQuota ? tokenQuota.remaining <= 0 : false;
  return (
    <div className="flex items-center justify-between px-6 py-2 bg-white dark:bg-[#111114] border-t border-zinc-200 dark:border-[#2f2f35] text-[10px] font-medium uppercase tracking-wider relative z-30">
      {/* Phase steps */}
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2 text-zinc-500 mr-2">
          <div className="w-1 h-1 bg-zinc-400 dark:bg-zinc-700" />
          <span>Systems</span>
        </div>
        
        <div className="flex items-center gap-4">
          {STEPS.map((step) => {
            const state = getStepState(step.key, phase);

            return (
              <div key={step.key} className="flex items-center gap-2">
                <div
                  className={`h-1 w-3 transition-all duration-500 rounded-full ${
                    state === "active"
                      ? "bg-cyan-500 shadow-[0_0_8px_rgba(34,211,238,0.5)] w-5"
                      : state === "past"
                        ? "bg-emerald-500/40"
                        : "bg-zinc-200 dark:bg-zinc-800"
                  }`}
                />
                <span
                  className={`transition-colors duration-300 ${
                    state === "active"
                      ? "text-cyan-400"
                      : state === "past"
                        ? "text-emerald-500/60"
                        : "text-muted dark:text-zinc-700"
                  }`}
                >
                  {step.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Token Quota + Connection */}
      <div className="flex items-center gap-6">
        {tokenQuota && (
          <div className="hidden md:flex items-center gap-3 text-muted dark:text-zinc-600 border-r border-card-border dark:border-zinc-800 pr-6">
            <span className="text-[9px]">TOKENS</span>
            <div className="flex items-center gap-2">
              <div className="w-20 h-1.5 bg-zinc-200 dark:bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    isExceeded
                      ? "bg-red-500"
                      : isWarning
                        ? "bg-amber-500"
                        : "bg-cyan-500"
                  }`}
                  style={{ width: `${Math.min(100, pct)}%` }}
                />
              </div>
              <span className={`text-[10px] font-mono ${
                isExceeded
                  ? "text-red-400"
                  : isWarning
                    ? "text-amber-400"
                    : "text-foreground dark:text-zinc-400"
              }`}>
                {formatTokenCount(tokenQuota.used)}/{formatTokenCount(tokenQuota.limit)}
              </span>
            </div>
          </div>
        )}

        <div className="flex items-center gap-2.5">
          <div className="flex flex-col items-end gap-0.5">
            <span className={`leading-none ${isConnected ? "text-emerald-500" : "text-red-500"}`}>
              {isConnected ? "Link Established" : "Link Severed"}
            </span>
          </div>
          <div className="relative flex h-2 w-2">
            {isConnected && (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500 opacity-20" />
            )}
            <div
              className={`h-2 w-2 rounded-full border border-black/20 ${
                isConnected ? "bg-emerald-500" : "bg-red-500"
              }`}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
