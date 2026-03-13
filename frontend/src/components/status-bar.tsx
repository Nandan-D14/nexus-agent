"use client";

type Phase = "idle" | "listening" | "thinking" | "acting" | "done";

type Props = {
  phase: Phase;
  isConnected: boolean;
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

export function StatusBar({ phase, isConnected }: Props) {
  return (
    <div className="flex items-center justify-between px-6 py-2 bg-card dark:bg-zinc-950 border-t border-card-border dark:border-zinc-800 text-[10px] font-bold uppercase tracking-[0.15em] glass relative z-30">
      {/* Phase steps */}
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2 text-muted dark:text-zinc-500 mr-2">
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

      {/* Stats/Connection */}
      <div className="flex items-center gap-6">
        <div className="hidden md:flex items-center gap-4 text-muted dark:text-zinc-600 border-r border-card-border dark:border-zinc-800 pr-6">
          <div className="flex items-center gap-1.5">
            <span className="text-[9px]">LATENCY</span>
            <span className="text-foreground dark:text-zinc-400">24MS</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[9px]">UPTIME</span>
            <span className="text-foreground dark:text-zinc-400">00:12:45</span>
          </div>
        </div>

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
