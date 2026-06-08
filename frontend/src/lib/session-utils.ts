/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import type { AgentVisualAction } from "@/components/desktop-panel";
import type {
  ArchivedMessage,
  RunArtifact,
  RunInfo,
  RunStep,
  SessionInfo,
  UploadedInputFile,
  WorkflowTemplateInputField,
} from "@/lib/message-types";
import {
  classifyAgentTool,
  displayAgentToolName,
} from "@/lib/agent-tool-classification";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export type ChatItem =
  | { kind: "message"; role: "user" | "agent"; text: string; ts: number }
  | { kind: "event"; type: string; ts: number; [key: string]: unknown }
  | {
      kind: "permission";
      task_id: string;
      description: string;
      estimated_seconds: number;
      agent: string;
      approval_id?: string;
      durable_task_id?: string;
      ts: number;
    }
  | { kind: "delegation"; from: string; to: string; ts: number };

export type PendingTurnInput = {
  text: string;
  connectorIds?: string[];
  uploadedFiles?: UploadedInputFile[];
};

export type PendingSessionAction =
  | { type: "demo"; payload: PendingTurnInput }
  | { type: "prompt"; payload: PendingTurnInput }
  | { type: "openDesktop" }
  | { type: "startMic" };

export type SessionConnector = {
  connection_id: string;
  connector_type: string;
  provider: string;
  name: string;
  enabled: boolean;
  status: string;
};

export type SessionUploadResponse = {
  path: string;
  artifact: RunArtifact;
  drive_status?: string | null;
  drive_file_id?: string | null;
  drive_web_view_link?: string | null;
  drive_folder_path?: string | null;
};

export type TemplateFormValue = {
  name: string;
  description: string;
  instructions: string;
  inputFields: WorkflowTemplateInputField[];
};

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

export const SYSTEM_CONNECTOR: SessionConnector = {
  connection_id: "system",
  connector_type: "system",
  provider: "system",
  name: "Cloud Desktop Tools",
  enabled: true,
  status: "connected",
};

export const EMPTY_TEMPLATE: TemplateFormValue = {
  name: "",
  description: "",
  instructions: "",
  inputFields: [],
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

export function numericArg(args: Record<string, unknown>, key: string): number | undefined {
  const value = args[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

export function providerLogo(provider: string) {
  switch (provider) {
    case "google_drive":
      return "https://www.gstatic.com/images/branding/product/2x/drive_2020q4_48dp.png";
    case "gmail":
      return "https://www.gstatic.com/images/branding/product/2x/gmail_2020q4_48dp.png";
    case "google_calendar":
      return "https://www.gstatic.com/images/branding/product/2x/calendar_2020q4_48dp.png";
    case "google_tasks":
      return "https://upload.wikimedia.org/wikipedia/commons/5/5f/Google_Tasks_2021.svg";
    case "github":
      return "https://upload.wikimedia.org/wikipedia/commons/9/91/Octicons-mark-github.svg";
    default:
      return null;
  }
}

export function toolAction(tool: string, args: Record<string, unknown>): AgentVisualAction {
  const ts = Date.now();
  const provider = classifyAgentTool(tool);
  if (tool === "left_click" || tool === "right_click" || tool === "double_click") {
    return { kind: "click", label: "Clicking", x: numericArg(args, "x"), y: numericArg(args, "y"), ts };
  }
  if (tool === "move_mouse") {
    return { kind: "move", label: "Moving pointer", x: numericArg(args, "x"), y: numericArg(args, "y"), ts };
  }
  if (tool === "drag") {
    return { kind: "drag", label: "Dragging", x: numericArg(args, "to_x"), y: numericArg(args, "to_y"), ts };
  }
  if (tool === "type_text") return { kind: "typing", label: "Typing", ts };
  if (tool === "press_key") return { kind: "key", label: "Pressing key", ts };
  if (tool === "scroll_screen") {
    return { kind: "scroll", label: "Scrolling", direction: String(args.direction || ""), ts };
  }
  if (tool === "take_screenshot") return { kind: "observe", label: "Observing screen", ts };
  if (tool === "open_browser" || tool === "web_search" || tool === "scrape_web_page") {
    return { kind: "browser", label: tool === "web_search" ? "Searching web" : "Opening page", ts };
  }
  if (tool === "run_command") return { kind: "command", label: "Running command", ts };
  if (tool === "write_todo_list" || tool === "prepare_task_workspace") {
    return { kind: "command", label: "Planning", ts };
  }
  return { kind: "command", label: provider === "generic" ? "Working" : displayAgentToolName(tool), ts };
}

export function displayStepTitle(title: string, tool?: string, stepType?: string): string {
  if (tool) return displayAgentToolName(tool);
  return title || `${stepType || "workflow"} step`;
}

export function upsertRunArtifact(prev: RunArtifact[], nextArtifact: RunArtifact): RunArtifact[] {
  const existingIndex = prev.findIndex((artifact) => artifact.artifact_id === nextArtifact.artifact_id);
  if (existingIndex === -1) {
    return [nextArtifact, ...prev];
  }
  const updated = [...prev];
  updated[existingIndex] = nextArtifact;
  return updated;
}

export function normalizePendingTurnInput(value: unknown): PendingTurnInput | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const record = value as Record<string, unknown>;
  const text = typeof record.text === "string" ? record.text.trim() : "";
  if (!text) {
    return null;
  }
  const connectorIds = Array.isArray(record.connectorIds)
    ? record.connectorIds.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];
  const uploadedFiles = Array.isArray(record.uploadedFiles)
    ? record.uploadedFiles.filter((item): item is UploadedInputFile => Boolean(item && typeof item === "object"))
    : [];
  return { text, connectorIds, uploadedFiles };
}

export function upsertRunStep(prev: RunStep[], nextStep: RunStep): RunStep[] {
  const existingIndex = prev.findIndex((step) => step.step_id === nextStep.step_id);
  if (existingIndex === -1) {
    return [...prev, nextStep].sort((left, right) => left.step_index - right.step_index);
  }
  const updated = [...prev];
  updated[existingIndex] = nextStep;
  return updated.sort((left, right) => left.step_index - right.step_index);
}

export function upsertArtifact(prev: RunArtifact[], artifact: RunArtifact): RunArtifact[] {
  const existingIndex = prev.findIndex((item) => item.artifact_id === artifact.artifact_id);
  if (existingIndex === -1) {
    return [artifact, ...prev];
  }
  const updated = [...prev];
  updated[existingIndex] = artifact;
  return updated;
}

export function mapStoredMessagesToChatItems(messages: ArchivedMessage[]): ChatItem[] {
  return messages.map((message) => {
    const ts = message.created_at ? new Date(message.created_at).getTime() : Date.now();

    if (message.role === "tool_call") {
      const { tool, args } = parseToolCallText(message.text, message.source);
      return {
        kind: "event" as const,
        type: "agent_tool_call",
        tool,
        args,
        ts,
      };
    }

    if (message.role === "tool_result") {
      return {
        kind: "event" as const,
        type: "agent_tool_result",
        tool: message.source || "tool",
        output: message.text,
        ts,
      };
    }

    return {
      kind: "message" as const,
      role: message.role,
      text: message.text,
      ts,
    };
  });
}

function parseToolCallText(text: string, source?: string): { tool: string; args: Record<string, unknown> } {
  const lines = text.split("\n");
  const toolMatch = lines[0]?.match(/^Tool:\s*(.+)$/);
  const tool = toolMatch ? toolMatch[1].trim() : source || "tool";

  let args: Record<string, unknown> = {};
  if (lines.length > 1) {
    const argsLine = lines.slice(1).join("\n").replace(/^Args:\s*/, "");
    try {
      const parsed = JSON.parse(argsLine);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        args = parsed;
      }
    } catch {
      // Ignore parse failures
    }
  }

  return { tool, args };
}

export function buildSessionTemplateDraft(
  sessionInfo: SessionInfo | null,
  runInfo: RunInfo | null,
  runSteps: RunStep[],
  runArtifacts: RunArtifact[],
): TemplateFormValue {
  const name =
    sessionInfo?.handoff_summary?.headline ||
    sessionInfo?.summary ||
    sessionInfo?.context_packet?.summary ||
    "Workflow template";

  const description =
    sessionInfo?.handoff_summary?.preview ||
    sessionInfo?.summary ||
    sessionInfo?.context_packet?.summary ||
    "";

  const lines = [
    "Use this saved CoComputer workflow as the execution pattern for the new task.",
  ];

  const goal =
    sessionInfo?.handoff_summary?.goal ||
    sessionInfo?.context_packet?.goal ||
    "";
  if (goal.trim()) {
    lines.push(`Original goal: ${goal.trim()}`);
  }

  if (runInfo?.title?.trim()) {
    lines.push(`Run title: ${runInfo.title.trim()}`);
  }

  if (description.trim()) {
    lines.push(`Saved summary: ${description.trim()}`);
  }

  const latestSteps = runSteps
    .filter((step) => step.status === "completed")
    .slice(-3)
    .map((step) => (step.detail || step.title).trim())
    .filter(Boolean);
  if (latestSteps.length > 0) {
    lines.push("Successful workflow steps to preserve:");
    lines.push(...latestSteps.map((step) => `- ${step}`));
  }

  const artifacts = (sessionInfo?.handoff_summary?.artifacts || [])
    .slice(0, 4)
    .filter(Boolean);
  const artifactRefs = (sessionInfo?.context_packet?.artifact_refs || [])
    .slice(0, 4)
    .filter(Boolean);
  const outputRefs = artifacts.length > 0 ? artifacts : artifactRefs;
  if (outputRefs.length > 0) {
    lines.push("Reference outputs from this workflow:");
    lines.push(...outputRefs.map((item) => `- ${item}`));
  } else if (runArtifacts.length > 0) {
    lines.push("Reference outputs from this workflow:");
    lines.push(
      ...runArtifacts.slice(0, 4).map((artifact) => `- ${artifact.title || artifact.preview || artifact.kind}`),
    );
  }

  const recentTurns = sessionInfo?.context_packet?.recent_turns || [];
  if (recentTurns.length > 0) {
    lines.push("Recent conversation context:");
    lines.push(...recentTurns.slice(-4).map((turn) => `- ${turn}`));
  }

  lines.push(
    "When this template is run, use the provided template input values and execute the workflow without asking the user to repeat the saved context.",
  );

  return {
    name: name.slice(0, 80),
    description: description.slice(0, 240),
    instructions: lines.join("\n").trim(),
    inputFields: [],
  };
}
