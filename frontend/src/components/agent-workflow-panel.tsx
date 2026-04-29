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
      <div className="h-full flex items-center justify-center p-12 text-center">
        <p className="text-[13px] text-zinc-600 font-medium tracking-tight leading-relaxed max-w-[180px]">
          {emptyState}
        </p>
      </div>
    );
  }

  const isRunning = run.status === "running";

  return (
    <div className="h-full flex flex-col bg-[#09090b]">
      {/* Ultra-minimal header */}
      <div className="shrink-0 px-6 py-4 flex items-center justify-between bg-[#09090b]/80 backdrop-blur-xl z-20 sticky top-0 border-b border-white/[0.03]">
        <div className="flex items-center gap-4">
          <h2 className="text-[13px] font-bold text-zinc-100 tracking-tight">
            {run.title || "Execution Log"}
          </h2>
          <div className="h-3 w-[1px] bg-zinc-800" />
          <span className="text-[10px] text-zinc-500 font-bold tracking-widest uppercase">
            {run.steps.length} {run.steps.length === 1 ? "step" : "steps"}
          </span>
        </div>
        
        {isRunning && (
          <div className="flex items-center gap-2.5">
            <div className="flex items-center gap-2 px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/20">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-cyan-500"></span>
              </span>
              <span className="text-[9px] text-cyan-400 font-black uppercase tracking-[0.15em]">
                Live
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Steps Feed */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-6 py-8 relative scroll-smooth custom-scrollbar"
      >
        {/* Continuous minimal timeline line */}
        <div className="absolute left-[36px] top-10 bottom-10 w-[1px] bg-zinc-800/40" />

        <div className="space-y-1 relative z-10">
          <AnimatePresence initial={false} mode="popLayout">
            {run.steps.map((step, index) => (
              <motion.div
                key={step.step_id}
                initial={{ opacity: 0, y: 4, filter: "blur(1px)" }}
                animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                transition={{ duration: 0.25, ease: [0.23, 1, 0.32, 1] }}
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
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="relative flex items-center gap-4 ml-1.5 py-4"
              >
                <div className="w-5 h-5 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center shrink-0 z-10">
                  <div className="w-1 h-1 rounded-full bg-zinc-500 animate-pulse" />
                </div>
                <div className="text-[13px] text-zinc-500 font-medium italic tracking-tight">
                  Reasoning...
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
