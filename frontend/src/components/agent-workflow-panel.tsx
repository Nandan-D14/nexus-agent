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
  emptyState = "Waiting for instructions...",
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
      <div className="h-full flex flex-col items-center justify-center p-8">
        <p className="text-[13px] text-zinc-500 font-medium">{emptyState}</p>
      </div>
    );
  }

  const isRunning = run.status === "running";

  return (
    <div className="h-full flex flex-col bg-transparent">
      {/* Sleek, minimal header */}
      <div className="shrink-0 px-5 py-4 border-b border-zinc-800/50 flex items-center justify-between bg-[#111114]/80 backdrop-blur-md z-10 sticky top-0">
        <div className="flex items-center gap-3">
          <h2 className="text-[13px] font-semibold text-zinc-200">
            {run.title || "Agent Execution"}
          </h2>
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-zinc-900 border border-zinc-800">
            <span className="text-[10px] text-zinc-400 font-medium tracking-wide">
              {run.steps.length} {run.steps.length === 1 ? "step" : "steps"}
            </span>
          </div>
        </div>
        {isRunning && (
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-zinc-500 font-medium uppercase tracking-widest">
              Running
            </span>
            <Loader2 className="w-3.5 h-3.5 text-zinc-400 animate-spin" />
          </div>
        )}
      </div>

      {/* Steps feed */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-5 relative scroll-smooth custom-scrollbar"
      >
        {/* Continuous minimal timeline line */}
        <div className="absolute left-[31px] top-6 bottom-8 w-[1px] bg-zinc-800/60" />

        <div className="space-y-1">
          <AnimatePresence initial={false} mode="popLayout">
            {run.steps.map((step, index) => (
              <motion.div
                key={step.step_id}
                initial={{ opacity: 0, filter: "blur(4px)", y: 10 }}
                animate={{ opacity: 1, filter: "blur(0px)", y: 0 }}
                transition={{ duration: 0.3, ease: "easeOut" }}
                className="relative z-10"
              >
                <WorkflowStep
                  step={step}
                  isLast={index === run.steps.length - 1 && !isRunning}
                  stepNumber={index + 1}
                />
              </motion.div>
            ))}
          </AnimatePresence>

          {/* Active running state indicator */}
          <AnimatePresence>
            {isRunning && (
              <motion.div
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.9 }}
                className="relative z-10 flex items-center gap-4 ml-[11px] mt-4 pb-4"
              >
                <div className="w-5 h-5 rounded-full bg-zinc-900 border border-zinc-700 flex items-center justify-center shrink-0 z-10">
                  <div className="w-1.5 h-1.5 rounded-full bg-zinc-400 animate-pulse" />
                </div>
                <div className="text-[13px] text-zinc-500 font-medium">
                  Thinking...
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
