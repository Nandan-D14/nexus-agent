/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useState, useEffect, memo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AgentWorkflowPanel, WorkflowRun } from "./agent-workflow-panel";
import { DesktopPanel, type AgentVisualAction } from "./desktop-panel";
import { Activity, Monitor, Loader2, FileText, Folder, LayoutGrid, Terminal, FileCode, BookOpen, Globe, RotateCcw } from "lucide-react";
import { OutputsPanel } from "./outputs-panel";
import { WorkspacePanel } from "./workspace-panel";
import { SandboxFilesPanel } from "./sandbox-files-panel";
import { SandboxTerminalPane } from "./session/sandbox-terminal-pane";
import { SandboxEditorPane } from "./session/sandbox-editor-pane";
import { AppPreviewPane } from "./session/app-preview-pane";
import { SessionCanvas } from "./session/session-canvas";
import type {
  AppPreviewState,
  EditorSessionState,
  TerminalSessionState,
} from "@/lib/sandbox-session";
import { RunArtifact } from "@/lib/message-types";
import { Tabs, Tooltip } from "@heroui/react";
import { useSessionCanvas } from "@/lib/session-canvas-context";
import { isCanvasArtifact } from "@/lib/session-canvas";

export type Tab = "canvas" | "workflow" | "desktop" | "terminal" | "editor" | "preview" | "artifacts" | "files" | "workspace";

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
  sessionId?: string | null;
  isFullscreen?: boolean;
  terminalSession?: TerminalSessionState | null;
  editorSession?: EditorSessionState | null;
  appPreview?: AppPreviewState | null;
  filesRefreshKey?: number;
  onOpenWorkspaceFile?: (state: EditorSessionState) => void;
  sandboxRestarting?: boolean;
  onRestartSandbox?: () => void;
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
  sessionId,
  isFullscreen,
  terminalSession = null,
  editorSession = null,
  appPreview = null,
  filesRefreshKey = 0,
  onOpenWorkspaceFile,
  sandboxRestarting = false,
  onRestartSandbox,
}: Props) {
  const [activeTab, setActiveTab] = useState<Tab>(defaultTab);
  const [autoRouteTab, setAutoRouteTab] = useState<Tab | null>(null);
  const canvas = useSessionCanvas();
  const canvasCount =
    (canvas?.documents.length ?? 0) || artifacts.filter(isCanvasArtifact).length;
  const showCanvasTab = canvasCount > 0 || activeTab === "canvas";

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
    if (autoRouteTab === "terminal" && terminalSession && !terminalSession.running) {
      setAutoRouteTab(null);
    }
    if (autoRouteTab === "editor" && editorSession && !editorSession.running) {
      setAutoRouteTab(null);
    }
  }, [autoRouteTab, terminalSession, editorSession]);

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
      : autoRouteTab === "terminal"
        ? "Terminal activity detected"
        : autoRouteTab === "editor"
          ? "Editing file"
          : autoRouteTab === "preview"
            ? "App preview ready"
            : autoRouteTab === "canvas"
          ? "Document ready"
          : autoRouteTab === "workflow"
            ? "Workflow activity detected"
            : null;

  return (
    <div className="flex h-full flex-col overflow-hidden bg-background-full">
      {/* Clean Tab Bar */}
      <div className="relative z-10 flex items-center justify-between border-b border-separator-border bg-background-full px-4 py-2">
        <Tabs 
          selectedKey={activeTab} 
          onSelectionChange={(key) => handleTabChange(key as Tab)}
        >
          <Tabs.ListContainer>
            <Tabs.List aria-label="Workspace Tabs" className="flex flex-row items-center gap-1">
              {showCanvasTab ? (
                <Tabs.Tab id="canvas" className="flex items-center justify-center px-3 py-2 outline-none cursor-pointer">
                  <Tooltip delay={0} closeDelay={0}>
                    <Tooltip.Trigger>
                      <div className="relative flex items-center justify-center">
                        <BookOpen className="w-4 h-4 text-zinc-400 transition-colors hover:text-zinc-700 dark:hover:text-zinc-200" />
                        {canvasCount > 0 && (
                          <span className="absolute -top-2 -right-3 px-[4px] py-[1px] rounded-md bg-zinc-800 text-zinc-300 text-[9px] font-semibold leading-none border border-zinc-700/50">
                            {canvasCount}
                          </span>
                        )}
                      </div>
                    </Tooltip.Trigger>
                    <Tooltip.Content className="px-2 py-1 text-xs font-medium rounded-md bg-zinc-900 text-zinc-100 dark:bg-zinc-800 dark:text-zinc-100 border border-zinc-800 dark:border-zinc-700 shadow-md">
                      Canvas
                    </Tooltip.Content>
                  </Tooltip>
                  <Tabs.Indicator className="bg-zinc-700/80" />
                </Tabs.Tab>
              ) : null}

              <Tabs.Tab id="workflow" className="flex items-center justify-center px-3 py-2 outline-none cursor-pointer">
                <Tooltip delay={0} closeDelay={0}>
                  <Tooltip.Trigger>
                    <div className="relative flex items-center justify-center">
                      <Activity className="w-4 h-4 text-zinc-400 transition-colors hover:text-zinc-700 dark:hover:text-zinc-200" />
                      {workflowRun && workflowRun.steps.length > 0 && (
                        <span className="absolute -top-2 -right-3 px-[4px] py-[1px] rounded-md bg-zinc-800 text-zinc-300 text-[9px] font-semibold leading-none border border-zinc-700/50">
                          {workflowRun.steps.length}
                        </span>
                      )}
                      {activeSteps > 0 && (
                        <span className="absolute -top-1 -right-1 w-1.5 h-1.5 bg-cyan-500 rounded-full" />
                      )}
                    </div>
                  </Tooltip.Trigger>
                  <Tooltip.Content className="px-2 py-1 text-xs font-medium rounded-md bg-zinc-900 text-zinc-100 dark:bg-zinc-800 dark:text-zinc-100 border border-zinc-800 dark:border-zinc-700 shadow-md">
                    Workflow
                  </Tooltip.Content>
                </Tooltip>
                <Tabs.Indicator className="bg-zinc-700/80" />
              </Tabs.Tab>

              <Tabs.Tab id="desktop" className="flex items-center justify-center px-3 py-2 outline-none cursor-pointer">
                <Tooltip delay={0} closeDelay={0}>
                  <Tooltip.Trigger>
                    <div className="relative flex items-center justify-center">
                      <Monitor className="w-4 h-4 text-zinc-400 transition-colors hover:text-zinc-700 dark:hover:text-zinc-200" />
                      {isStreamActive && (
                        <span className="absolute -top-1 -right-1 flex h-1.5 w-1.5">
                          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-50" />
                          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
                        </span>
                      )}
                    </div>
                  </Tooltip.Trigger>
                  <Tooltip.Content className="px-2 py-1 text-xs font-medium rounded-md bg-zinc-900 text-zinc-100 dark:bg-zinc-800 dark:text-zinc-100 border border-zinc-800 dark:border-zinc-700 shadow-md">
                    Desktop
                  </Tooltip.Content>
                </Tooltip>
                <Tabs.Indicator className="bg-zinc-700/80" />
              </Tabs.Tab>

              <Tabs.Tab id="terminal" className="flex items-center justify-center px-3 py-2 outline-none cursor-pointer">
                <Tooltip delay={0} closeDelay={0}>
                  <Tooltip.Trigger>
                    <div className="relative flex items-center justify-center">
                      <Terminal className="w-4 h-4 text-zinc-400 transition-colors hover:text-zinc-700 dark:hover:text-zinc-200" />
                      {terminalSession?.running && (
                        <span className="absolute -top-1 -right-1 w-1.5 h-1.5 bg-cyan-500 rounded-full" />
                      )}
                    </div>
                  </Tooltip.Trigger>
                  <Tooltip.Content className="px-2 py-1 text-xs font-medium rounded-md bg-zinc-900 text-zinc-100 dark:bg-zinc-800 dark:text-zinc-100 border border-zinc-800 dark:border-zinc-700 shadow-md">
                    Terminal
                  </Tooltip.Content>
                </Tooltip>
                <Tabs.Indicator className="bg-zinc-700/80" />
              </Tabs.Tab>

              <Tabs.Tab id="editor" className="flex items-center justify-center px-3 py-2 outline-none cursor-pointer">
                <Tooltip delay={0} closeDelay={0}>
                  <Tooltip.Trigger>
                    <div className="relative flex items-center justify-center">
                      <FileCode className="w-4 h-4 text-zinc-400 transition-colors hover:text-zinc-700 dark:hover:text-zinc-200" />
                      {editorSession?.running && (
                        <span className="absolute -top-1 -right-1 w-1.5 h-1.5 bg-amber-400 rounded-full" />
                      )}
                    </div>
                  </Tooltip.Trigger>
                  <Tooltip.Content className="px-2 py-1 text-xs font-medium rounded-md bg-zinc-900 text-zinc-100 dark:bg-zinc-800 dark:text-zinc-100 border border-zinc-800 dark:border-zinc-700 shadow-md">
                    Editor
                  </Tooltip.Content>
                </Tooltip>
                <Tabs.Indicator className="bg-zinc-700/80" />
              </Tabs.Tab>

              <Tabs.Tab id="preview" className="flex items-center justify-center px-3 py-2 outline-none cursor-pointer">
                <Tooltip delay={0} closeDelay={0}>
                  <Tooltip.Trigger>
                    <div className="relative flex items-center justify-center">
                      <Globe className="w-4 h-4 text-zinc-400 transition-colors hover:text-zinc-700 dark:hover:text-zinc-200" />
                      {appPreview && !appPreview.expired && (
                        <span className="absolute -top-1 -right-1 flex h-1.5 w-1.5">
                          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-50" />
                          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
                        </span>
                      )}
                    </div>
                  </Tooltip.Trigger>
                  <Tooltip.Content className="px-2 py-1 text-xs font-medium rounded-md bg-zinc-900 text-zinc-100 dark:bg-zinc-800 dark:text-zinc-100 border border-zinc-800 dark:border-zinc-700 shadow-md">
                    Preview
                  </Tooltip.Content>
                </Tooltip>
                <Tabs.Indicator className="bg-zinc-700/80" />
              </Tabs.Tab>

              <Tabs.Tab id="artifacts" className="flex items-center justify-center px-3 py-2 outline-none cursor-pointer">
                <Tooltip delay={0} closeDelay={0}>
                  <Tooltip.Trigger>
                    <div className="relative flex items-center justify-center">
                      <FileText className="w-4 h-4 text-zinc-400 transition-colors hover:text-zinc-700 dark:hover:text-zinc-200" />
                      {artifacts.length > 0 && (
                        <span className="absolute -top-2 -right-3 px-[4px] py-[1px] rounded-md bg-zinc-800 text-zinc-300 text-[9px] font-semibold leading-none border border-zinc-700/50">
                          {artifacts.length}
                        </span>
                      )}
                    </div>
                  </Tooltip.Trigger>
                  <Tooltip.Content className="px-2 py-1 text-xs font-medium rounded-md bg-zinc-900 text-zinc-100 dark:bg-zinc-800 dark:text-zinc-100 border border-zinc-800 dark:border-zinc-700 shadow-md">
                    Artifacts
                  </Tooltip.Content>
                </Tooltip>
                <Tabs.Indicator className="bg-zinc-700/80" />
              </Tabs.Tab>

              <Tabs.Tab id="files" className="flex items-center justify-center px-3 py-2 outline-none cursor-pointer">
                <Tooltip delay={0} closeDelay={0}>
                  <Tooltip.Trigger>
                    <div className="relative flex items-center justify-center">
                      <Folder className="w-4 h-4 text-zinc-400 transition-colors hover:text-zinc-700 dark:hover:text-zinc-200" />
                    </div>
                  </Tooltip.Trigger>
                  <Tooltip.Content className="px-2 py-1 text-xs font-medium rounded-md bg-zinc-900 text-zinc-100 dark:bg-zinc-800 dark:text-zinc-100 border border-zinc-800 dark:border-zinc-700 shadow-md">
                    Files
                  </Tooltip.Content>
                </Tooltip>
                <Tabs.Indicator className="bg-zinc-700/80" />
              </Tabs.Tab>

              <Tabs.Tab id="workspace" className="flex items-center justify-center px-3 py-2 outline-none cursor-pointer">
                <Tooltip delay={0} closeDelay={0}>
                  <Tooltip.Trigger>
                    <div className="relative flex items-center justify-center">
                      <LayoutGrid className="w-4 h-4 text-zinc-400 transition-colors hover:text-zinc-700 dark:hover:text-zinc-200" />
                    </div>
                  </Tooltip.Trigger>
                  <Tooltip.Content className="px-2 py-1 text-xs font-medium rounded-md bg-zinc-900 text-zinc-100 dark:bg-zinc-800 dark:text-zinc-100 border border-zinc-800 dark:border-zinc-700 shadow-md">
                    Workspace Apps
                  </Tooltip.Content>
                </Tooltip>
                <Tabs.Indicator className="bg-zinc-700/80" />
              </Tabs.Tab>
            </Tabs.List>
          </Tabs.ListContainer>
        </Tabs>

        <div className="flex items-center gap-2">
          {onRestartSandbox ? (
            <Tooltip delay={0} closeDelay={0}>
              <Tooltip.Trigger>
                <button
                  type="button"
                  onClick={onRestartSandbox}
                  disabled={sandboxRestarting}
                  aria-label="Restart sandbox"
                  className="inline-flex items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-900/70 px-2 py-1 text-[11px] font-medium text-zinc-300 transition-colors hover:border-zinc-700 hover:text-zinc-100 disabled:opacity-40"
                >
                  {sandboxRestarting ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <RotateCcw className="h-3.5 w-3.5" />
                  )}
                  Restart
                </button>
              </Tooltip.Trigger>
              <Tooltip.Content className="px-2 py-1 text-xs font-medium rounded-md bg-zinc-900 text-zinc-100 dark:bg-zinc-800 dark:text-zinc-100 border border-zinc-800 dark:border-zinc-700 shadow-md">
                Restart sandbox
              </Tooltip.Content>
            </Tooltip>
          ) : null}
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
      </div>

      {/* Content Area */}
      <div className="relative min-h-0 flex-1 overflow-hidden bg-background-full">
        <AnimatePresence mode="wait">
          {activeTab === "canvas" && (
            <motion.div
              key="canvas"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0"
            >
              <SessionCanvas artifacts={artifacts} />
            </motion.div>
          )}

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
                <DesktopPanel
                  streamUrl={streamUrl}
                  analysis={analysis}
                  action={agentAction}
                  sessionId={sessionId}
                  isAgentIdle={phase === "idle" || phase === "done"}
                  isFullscreen={isFullscreen}
                />
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

          {activeTab === "terminal" && (
            <motion.div
              key="terminal"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0"
            >
              <SandboxTerminalPane session={terminalSession} />
            </motion.div>
          )}

          {activeTab === "editor" && (
            <motion.div
              key="editor"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0"
            >
              <SandboxEditorPane session={editorSession} />
            </motion.div>
          )}

          {activeTab === "preview" && (
            <motion.div
              key="preview"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0"
            >
              <AppPreviewPane
                preview={appPreview}
                restarting={sandboxRestarting}
                onRestartSandbox={onRestartSandbox}
              />
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

          {activeTab === "files" && (
            <motion.div
              key="files"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0"
            >
              <SandboxFilesPanel
                sessionId={sessionId}
                active={activeTab === "files"}
                refreshKey={filesRefreshKey}
                onOpenFile={onOpenWorkspaceFile}
              />
            </motion.div>
          )}

          {activeTab === "workspace" && (
            <motion.div
              key="workspace"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0"
            >
              <WorkspacePanel />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
});
