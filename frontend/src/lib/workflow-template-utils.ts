"use client";

import type {
  ContextPacket,
  HandoffSummary,
  WorkflowTemplateInputField,
} from "./message-types";

type TemplateDraftSource = {
  title?: string | null;
  summary?: string | null;
  handoffSummary?: HandoffSummary | null;
  contextPacket?: ContextPacket | null;
  artifactTitles?: string[];
};

export type WorkflowTemplateDraft = {
  name: string;
  description: string;
  instructions: string;
  inputFields: WorkflowTemplateInputField[];
};

export function queuePendingSessionPrompt(sessionId: string, text: string) {
  if (typeof window === "undefined") {
    return;
  }
  window.sessionStorage.setItem(
    `nexus.pendingSessionAction:${sessionId}`,
    JSON.stringify({ type: "prompt", text }),
  );
}

export function buildWorkflowTemplateDraft(
  source: TemplateDraftSource,
): WorkflowTemplateDraft {
  const handoff = source.handoffSummary;
  const packet = source.contextPacket;
  const summary =
    handoff?.preview ||
    source.summary ||
    packet?.summary ||
    "Reusable workflow saved from a prior CoComputer session.";
  const goal = handoff?.goal || packet?.goal || "";
  const completed = handoff?.completed_work ?? [];
  const openTasks = handoff?.open_tasks ?? packet?.open_tasks ?? [];
  const artifactTitles = (source.artifactTitles ?? []).filter(Boolean).slice(0, 4);

  const lines = [
    "Use this saved CoComputer workflow as the execution pattern for the new task.",
  ];
  if (goal) {
    lines.push(`Original goal: ${goal}`);
  }
  if (summary) {
    lines.push(`Saved summary: ${summary}`);
  }
  if (completed.length > 0) {
    lines.push("Successful workflow steps to preserve:");
    completed.slice(0, 3).forEach((item) => lines.push(`- ${item}`));
  }
  if (openTasks.length > 0) {
    lines.push("Open tasks or follow-ups to consider:");
    openTasks.slice(0, 3).forEach((item) => lines.push(`- ${item}`));
  }
  if (artifactTitles.length > 0) {
    lines.push("Reference artifacts from the source session:");
    artifactTitles.forEach((item) => lines.push(`- ${item}`));
  }
  lines.push(
    "When this template is run, use the provided template input values and execute the workflow without asking the user to restate the saved context.",
  );

  return {
    name: source.title?.trim() || handoff?.headline || "Workflow template",
    description: summary,
    instructions: lines.join("\n").trim(),
    inputFields: [],
  };
}
