"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AgentWorkflowPanel, WorkflowRun } from "./agent-workflow-panel";
import { DesktopPanel } from "./desktop-panel";
import { Activity, Monitor, Loader2, Sparkles } from "lucide-react";

type Tab = "workflow" | "desktop";

export type UiActionMessage = {
  type: "ui_action";
  action: "switch_tab";
  target: Tab;
  reason?: string;
};

type Props = {
  workflowRun: WorkflowRun | null;
  streamUrl: string | null;
  analysis?: string | null;
  defaultTab?: Tab;
  onTabChange?: (tab: Tab) => void;
  forcedTab?: Tab | null;
  onForcedTabAck?: () => void;
  phase?: "idle" | "thinking" | "acting" | "done";
  agentStatus?: string;
  onStopAgent?: () => void;
};

export function WorkflowDesktopContainer({
  workflowRun,
  streamUrl,
  analysis,
  defaultTab = "workflow",
  onTabChange,
  forcedTab,
  onForcedTabAck,
  phase = "idle",
  agentStatus,
  onStopAgent,
}: Props) {
  const [activeTab, setActiveTab] = useState<Tab>(defaultTab);
  const [agentReason, setAgentReason] = useState<string | null>(null);

  useEffect(() => {
    if (forcedTab) {
      setActiveTab(forcedTab);
      if (forcedTab === "desktop" && workflowRun?.status === "running") {
        setAgentReason("Agent requested desktop view");
      }
      onForcedTabAck?.();
    }
  }, [forcedTab, onForcedTabAck, workflowRun?.status]);

  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab);
    setAgentReason(null);
    onTabChange?.(tab);
  };

  const isStreamActive = !!streamUrl;
  const activeSteps = workflowRun?.steps.filter(s => s.status === "in_progress").length || 0;

  return (
    <div className="h-full flex flex-col bg-[#0a0a0c] rounded-xl border border-zinc-800 overflow-hidden">
      {/* Clean Tab Bar */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-800 bg-[#0f0f11]">
        <div className="flex items-center gap-1">
          {/* Workflow Tab */}
          <button
            onClick={() => handleTabChange("workflow")}
            className={`relative flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
              activeTab === "workflow"
                ? "bg-zinc-800 text-white"
                : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50"
            }`}
          >
            <Activity className={`w-4 h-4 ${activeTab === "workflow" ? "text-cyan-400" : "text-zinc-600"}`} />
            <span>Workflow</span>
            {workflowRun && workflowRun.steps.length > 0 && (
              <span className="ml-1.5 px-1.5 py-0.5 rounded-md bg-zinc-700 text-zinc-300 text-[11px] font-semibold">
                {workflowRun.steps.length}
              </span>
            )}
            {activeSteps > 0 && (
              <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-cyan-400 rounded-full" />
            )}
          </button>

          {/* Desktop Tab */}
          <button
            onClick={() => handleTabChange("desktop")}
            className={`relative flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
              activeTab === "desktop"
                ? "bg-zinc-800 text-white"
                : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50"
            }`}
          >
            <Monitor className={`w-4 h-4 ${activeTab === "desktop" ? "text-emerald-400" : "text-zinc-600"}`} />
            <span>Desktop</span>
            {isStreamActive && (
              <span className="relative flex h-2 w-2 ml-1">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-50" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
              </span>
            )}
          </button>
        </div>

        {/* Agent Activity */}
        <AnimatePresence>
          {agentReason && activeTab === "desktop" && (
            <motion.div
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 10 }}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-zinc-800/80 border border-zinc-700"
            >
              <Loader2 className="w-3.5 h-3.5 text-cyan-400 animate-spin" />
              <span className="text-xs text-zinc-300">{agentReason}</span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Content Area */}
      <div className="flex-1 relative overflow-hidden bg-[#0a0a0c]">
        <AnimatePresence mode="wait">
          {activeTab === "workflow" && (
            <motion.div
              key="workflow"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0"
            >
              <AgentWorkflowPanel
                run={workflowRun}
                emptyState="Start a conversation to see the agent workflow"
              />
            </motion.div>
          )}

          {activeTab === "desktop" && (
            <motion.div
              key="desktop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0"
            >
              <div className="relative w-full h-full rounded-lg overflow-hidden border border-zinc-800">
                <DesktopPanel streamUrl={streamUrl} analysis={analysis} />
                {(phase === "thinking" || phase === "acting") && (
                  <>
                    <div className="absolute inset-0 z-10 bg-black/30 cursor-not-allowed" />
                    <motion.div 
                      initial={{ opacity: 0, y: -10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="absolute top-3 right-3 z-20 flex items-center gap-3 px-4 py-2 rounded-lg bg-[#141416] border border-zinc-700 shadow-xl"
                    >
                      <div className="flex items-center gap-2">
                        <span className={`w-2 h-2 rounded-full ${phase === "thinking" ? "bg-cyan-400" : "bg-amber-400"}`} />
                        <span className="text-xs font-medium text-zinc-300">
                          {agentStatus || (phase === "thinking" ? "Thinking..." : "Working...")}
                        </span>
                      </div>
                      <div className="w-px h-3 bg-zinc-700" />
                      <button
                        onClick={onStopAgent}
                        className="text-[11px] font-semibold text-red-400 hover:text-red-300 transition-colors"
                      >
                        Stop
                      </button>
                    </motion.div>
                  </>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
