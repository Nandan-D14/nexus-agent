"use client";

import { useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { WorkflowStep, WorkflowStepData } from "./workflow-step";
import { Loader2 } from "lucide-react";

export type WorkflowRun = {
  run_id: string;
  title: string;
  status: "running" | "completed" | "failed" | "pending";
  steps: WorkflowStepData[];
  started_at?: string;
  completed_at?: string;
};

type Props = {
  run: WorkflowRun | null;
  emptyState?: string;
};

export function AgentWorkflowPanel({
  run,
  emptyState = "Agent is ready...",
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, [run?.steps.length, run?.status]);

  if (!run || run.steps.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-[13px] text-zinc-500 font-medium">{emptyState}</p>
      </div>
    );
  }

  const isRunning = run.status === "running";

  return (
    <div className="h-full flex flex-col bg-[#0e0e10]">
      {/* Minimal Header */}
      <div className="shrink-0 px-6 py-4 flex items-center justify-between bg-[#0e0e10]/90 backdrop-blur-lg z-20 sticky top-0 border-b border-white/[0.03]">
        <div className="flex items-center gap-3">
          <h2 className="text-[14px] font-semibold text-zinc-200 tracking-tight">
            {run.title || "Execution Log"}
          </h2>
          <div className="flex items-center justify-center px-1.5 py-0.5 rounded bg-zinc-800/50 border border-zinc-700/50">
            <span className="text-[10px] text-zinc-400 font-bold tracking-widest uppercase">
              {run.steps.length} {run.steps.length === 1 ? "step" : "steps"}
            </span>
          </div>
        </div>
        {isRunning && (
          <div className="flex items-center gap-2.5">
            <span className="text-[11px] text-cyan-500 font-bold uppercase tracking-widest flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500"></span>
              </span>
              Active
            </span>
          </div>
        )}
      </div>

      {/* Steps Feed */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-6 py-6 relative scroll-smooth custom-scrollbar"
      >
        {/* Continuous minimal timeline line */}
        <div className="absolute left-[38px] top-8 bottom-8 w-[1px] bg-zinc-800/40" />

        <div className="space-y-3 relative z-10">
          <AnimatePresence initial={false} mode="popLayout">
            {run.steps.map((step, index) => (
              <motion.div
                key={step.step_id}
                initial={{ opacity: 0, y: 8, filter: "blur(2px)" }}
                animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                transition={{ duration: 0.3, ease: [0.23, 1, 0.32, 1] }}
                className="relative"
              >
                <WorkflowStep
                  step={step}
                  isLast={index === run.steps.length - 1 && !isRunning}
                  stepNumber={index + 1}
                />
              </motion.div>
            ))}
          </AnimatePresence>

          {/* Active indicator */}
          <AnimatePresence>
            {isRunning && (
              <motion.div
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.9 }}
                className="relative flex items-start gap-4 ml-1.5 mt-2"
              >
                <div className="w-6 h-6 rounded-full bg-[#161618] border border-zinc-700/50 shadow-sm flex items-center justify-center shrink-0 z-10 mt-[2px]">
                  <Loader2 className="w-3.5 h-3.5 text-zinc-400 animate-spin" />
                </div>
                <div className="text-[13px] text-zinc-500 font-medium py-1 italic">
                  Agent is reasoning...
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
