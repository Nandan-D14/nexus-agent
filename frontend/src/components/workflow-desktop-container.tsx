/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useState, useEffect, memo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AgentWorkflowPanel, WorkflowRun } from "./agent-workflow-panel";
import { DesktopPanel, type AgentVisualAction } from "./desktop-panel";
import { Activity, Monitor, Loader2, FileText } from "lucide-react";
import { OutputsPanel } from "./outputs-panel";
import { RunArtifact } from "@/lib/message-types";
import { Tabs, Tooltip } from "@heroui/react";

type Tab = "workflow" | "desktop" | "artifacts";

export type UiActionMessage = {
  type: "ui_action";
  action: "switch_tab";
  target: Tab;
  reason?: string;
};

type Props = {
  workflowRun: WorkflowRun | null;
  streamUrl: string | null;
  artifacts?: RunArtifact[];
  analysis?: string | null;
  defaultTab?: Tab;
  onTabChange?: (tab: Tab) => void;
  forcedTab?: Tab | null;
  onForcedTabAck?: () => void;
  phase?: "idle" | "listening" | "thinking" | "acting" | "done";
  agentStatus?: string;
  agentAction?: AgentVisualAction | null;
  onStopAgent?: () => void;
};

export const WorkflowDesktopContainer = memo(function WorkflowDesktopContainer({
  workflowRun,
  streamUrl,
  artifacts = [],
  analysis,
  defaultTab = "workflow",
  onTabChange,
  forcedTab,
  onForcedTabAck,
  phase = "idle",
  agentStatus,
  agentAction,
  onStopAgent,
}: Props) {
  const [activeTab, setActiveTab] = useState<Tab>(defaultTab);
  const [autoRouteTab, setAutoRouteTab] = useState<Tab | null>(null);

  useEffect(() => {
    if (!forcedTab) return;
    const timeout = window.setTimeout(() => {
      setActiveTab(forcedTab);
      setAutoRouteTab(forcedTab);
      onTabChange?.(forcedTab);
      onForcedTabAck?.();
    }, 0);
    return () => window.clearTimeout(timeout);
  }, [forcedTab, onForcedTabAck, onTabChange]);

  useEffect(() => {
    if (!autoRouteTab) return;
    const timeout = window.setTimeout(() => setAutoRouteTab(null), 2400);
    return () => window.clearTimeout(timeout);
  }, [autoRouteTab]);

  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab);
    setAutoRouteTab(null);
    onTabChange?.(tab);
  };

  const isStreamActive = !!streamUrl;
  const activeSteps = workflowRun?.steps.filter(s => s.status === "in_progress").length || 0;
  const agentReason =
    autoRouteTab === "desktop"
      ? "Desktop action detected"
      : autoRouteTab === "workflow"
        ? "Workflow activity detected"
        : null;

  return (
    <div className="h-full flex flex-col bg-[#0a0a0c] rounded-xl border border-zinc-800 overflow-hidden">
      {/* Clean Tab Bar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800/50 bg-transparent shadow-sm z-10 relative">
        <Tabs 
          selectedKey={activeTab} 
          onSelectionChange={(key) => handleTabChange(key as Tab)}
        >
          <Tabs.ListContainer>
            <Tabs.List aria-label="Workspace Tabs" className="flex flex-row items-center gap-1">
              <Tabs.Tab id="workflow" className="flex items-center justify-center px-3 py-2 outline-none cursor-pointer">
                <Tooltip content="Workflow" placement="bottom" delay={0} closeDelay={0}>
                  <div className="relative flex items-center justify-center">
                    <Activity className="w-4 h-4 text-zinc-400 hover:text-zinc-200 transition-colors" />
                    {workflowRun && workflowRun.steps.length > 0 && (
                      <span className="absolute -top-2 -right-3 px-[4px] py-[1px] rounded-md bg-zinc-800 text-zinc-300 text-[9px] font-semibold leading-none border border-zinc-700/50">
                        {workflowRun.steps.length}
                      </span>
                    )}
                    {activeSteps > 0 && (
                      <span className="absolute -top-1 -right-1 w-1.5 h-1.5 bg-cyan-500 rounded-full" />
                    )}
                  </div>
                </Tooltip>
                <Tabs.Indicator className="bg-zinc-700/80" />
              </Tabs.Tab>

              <Tabs.Tab id="desktop" className="flex items-center justify-center px-3 py-2 outline-none cursor-pointer">
                <Tooltip content="Desktop" placement="bottom" delay={0} closeDelay={0}>
                  <div className="relative flex items-center justify-center">
                    <Monitor className="w-4 h-4 text-zinc-400 hover:text-zinc-200 transition-colors" />
                    {isStreamActive && (
                      <span className="absolute -top-1 -right-1 flex h-1.5 w-1.5">
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-50" />
                        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
                      </span>
                    )}
                  </div>
                </Tooltip>
                <Tabs.Indicator className="bg-zinc-700/80" />
              </Tabs.Tab>

              <Tabs.Tab id="artifacts" className="flex items-center justify-center px-3 py-2 outline-none cursor-pointer">
                <Tooltip content="Artifacts" placement="bottom" delay={0} closeDelay={0}>
                  <div className="relative flex items-center justify-center">
                    <FileText className="w-4 h-4 text-zinc-400 hover:text-zinc-200 transition-colors" />
                    {artifacts.length > 0 && (
                      <span className="absolute -top-2 -right-3 px-[4px] py-[1px] rounded-md bg-zinc-800 text-zinc-300 text-[9px] font-semibold leading-none border border-zinc-700/50">
                        {artifacts.length}
                      </span>
                    )}
                  </div>
                </Tooltip>
                <Tabs.Indicator className="bg-zinc-700/80" />
              </Tabs.Tab>
            </Tabs.List>
          </Tabs.ListContainer>
        </Tabs>

        {/* Agent Activity */}
        <AnimatePresence>
          {agentReason && (
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
                <DesktopPanel streamUrl={streamUrl} analysis={analysis} action={agentAction} />
                {(phase === "thinking" || phase === "acting") && (
                  <>
                    <div className="absolute inset-0 z-10 bg-black/30 cursor-not-allowed" />
                    <motion.div 
                      initial={{ opacity: 0, scale: 0.95 }}
                      animate={{ opacity: 1, scale: 1 }}
                      className="absolute top-2 right-2 z-20 flex items-center gap-2 px-2.5 py-1.5 rounded-md bg-[#141416]/90 backdrop-blur border border-zinc-700/50 shadow-md"
                    >
                      <div className="flex items-center gap-1.5">
                        <span className={`w-1.5 h-1.5 rounded-full ${phase === "thinking" ? "bg-cyan-400" : "bg-amber-400"}`} />
                        <span className="text-[10px] font-medium text-zinc-300 uppercase tracking-wide">
                          {agentStatus || (phase === "thinking" ? "Thinking" : "Working")}
                        </span>
                      </div>
                      <div className="w-px h-3 bg-zinc-700" />
                      <button
                        onClick={onStopAgent}
                        className="text-[10px] font-medium text-red-400 hover:text-red-300 transition-colors uppercase tracking-wide"
                      >
                        Stop
                      </button>
                    </motion.div>
                  </>
                )}
              </div>
            </motion.div>
          )}

          {activeTab === "artifacts" && (
            <motion.div
              key="artifacts"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0"
            >
              <OutputsPanel artifacts={artifacts} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
});
