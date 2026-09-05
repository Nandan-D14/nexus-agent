/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
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
  isWorkflowVisualTool,
} from "@/lib/agent-tool-classification";
import type { WsMessage } from "@/lib/message-types";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export type PermissionDecision = "approved" | "denied" | "timed_out";

export const DEFAULT_ATTACHMENT_PROMPT = "Please review the attached file(s).";

/** Durable/history run statuses that mean a worker may still be executing. */
export const INFLIGHT_RUN_STATUSES = new Set([
  "queued",
  "running",
  "cancelling",
  "waiting_approval",
]);

export function isInflightRunStatus(status: string | null | undefined): boolean {
  return Boolean(status && INFLIGHT_RUN_STATUSES.has(status));
}

export type ChatItem =
  | {
      kind: "message";
      role: "user" | "agent";
      text: string;
      ts: number;
      attachments?: UploadedInputFile[];
    }
  | { kind: "event"; type: string; ts: number; [key: string]: unknown }
  | {
      kind: "permission";
      task_id: string;
      description: string;
      estimated_seconds: number;
      agent: string;
      approval_id?: string;
      durable_task_id?: string;
      /** True when this permission was settled (approve/deny/timeout). */
      resolved?: boolean;
      /** Restored/live outcome for the approval card chrome. */
      decision?: PermissionDecision;
      /** Policy risk tier (low/medium/high) for log + card subtitle. */
      risk?: string;
      /** Opaque fingerprint of the exact approved args. */
      action_hash?: string;
      /** Tool that requested approval, for log lines. */
      tool?: string;
      /** Epoch ms when the decision landed. */
      decided_at?: number;
      ts: number;
    }
  | { kind: "delegation"; from: string; to: string; ts: number }
  | {
      kind: "elicitation";
      elicitation_id: string;
      question_id?: string;
      mode?: "choice" | "suggestion";
      question?: string;
      options?: string[];
      allow_free_text?: boolean;
      title?: string;
      items?: Array<{ name: string; description: string; action_label?: string }>;
      answer?: string;
      answered?: boolean;
      timedOut?: boolean;
      timeout_seconds?: number;
      ts: number;
    }
  | {
      kind: "user_question";
      question_id: string;
      question: string;
      options?: string[];
      answer?: string;
      answered?: boolean;
      timedOut?: boolean;
      timeout_seconds?: number;
      ts: number;
    };

export type TodoListItem = {
  title: string;
  status: "pending" | "in_progress" | "done";
  note?: string;
};

export function upsertTemplateDraftItem(
  prev: ChatItem[],
  payload: {
    template_id: string;
    status?: "draft" | "published";
    name?: string;
    description?: string;
    instructions?: string;
    input_fields?: WorkflowTemplateInputField[];
    source_session_id?: string | null;
    dismissed?: boolean;
  },
  ts: number,
): ChatItem[] {
  const templateId = payload.template_id;
  if (!templateId) return prev;
  const nextFields = Array.isArray(payload.input_fields) ? payload.input_fields : [];
  let replaced = false;
  const mapped = prev.map((item) => {
    if (
      item.kind === "event" &&
      item.type === "template_draft" &&
      item.template_id === templateId
    ) {
      replaced = true;
      return {
        ...item,
        status: payload.status ?? item.status,
        name: payload.name ?? item.name,
        description: payload.description ?? item.description,
        instructions: payload.instructions ?? item.instructions,
        input_fields: payload.input_fields ?? item.input_fields,
        source_session_id: payload.source_session_id ?? item.source_session_id,
        dismissed: payload.dismissed ?? false,
      };
    }
    return item;
  });
  if (replaced) return mapped;
  return [
    ...prev,
    {
      kind: "event",
      type: "template_draft",
      template_id: templateId,
      status: payload.status ?? "draft",
      name: payload.name ?? "",
      description: payload.description ?? "",
      instructions: payload.instructions ?? "",
      input_fields: nextFields,
      source_session_id: payload.source_session_id ?? null,
      dismissed: Boolean(payload.dismissed),
      ts,
    },
  ];
}

export type HistoryMapMode = "full" | "transcript";

export const DEFAULT_ASK_USER_TIMEOUT_SECONDS = 300;

/** Mirrors APPROVAL_TIMEOUT_SECONDS in agent/nexus/tool_gateway.py. */
export const DEFAULT_APPROVAL_TIMEOUT_SECONDS = 120;

export type PendingTurnInput = {
  text: string;
  connectorIds?: string[];
  toolIds?: string[];
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

export { providerLogo } from "@/lib/connectors";

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

function mergeArtifactIds(prev: RunArtifact, next: RunArtifact): RunArtifact {
  // Never clobber durable IDs with empty strings on rehydration - the
  // backend fast path needs session_id+run_id to avoid index queries.
  return {
    ...next,
    session_id: next.session_id || prev.session_id || "",
    run_id: next.run_id || prev.run_id || "",
    path: next.path || prev.path || null,
    url: next.url || prev.url || null,
    metadata: { ...(prev.metadata || {}), ...(next.metadata || {}) },
  };
}

export function upsertRunArtifact(prev: RunArtifact[], nextArtifact: RunArtifact): RunArtifact[] {
  const existingIndex = prev.findIndex((artifact) => artifact.artifact_id === nextArtifact.artifact_id);
  if (existingIndex === -1) {
    return [nextArtifact, ...prev];
  }
  const updated = [...prev];
  updated[existingIndex] = mergeArtifactIds(prev[existingIndex], nextArtifact);
  return updated;
}

export function parseUploadedFiles(value: unknown): UploadedInputFile[] {
  if (!Array.isArray(value)) return [];
  const files: UploadedInputFile[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") continue;
    const record = item as Record<string, unknown>;
    const name = typeof record.name === "string" ? record.name.trim() : "";
    const path = typeof record.path === "string" ? record.path.trim() : "";
    if (!name && !path) continue;
    const previewUrl = typeof record.previewUrl === "string" ? record.previewUrl : undefined;
    files.push({
      artifact_id: typeof record.artifact_id === "string" ? record.artifact_id : undefined,
      name: name || path.split("/").pop() || "file",
      path,
      mime_type: typeof record.mime_type === "string" ? record.mime_type : null,
      size: typeof record.size === "number" ? record.size : null,
      drive_status: typeof record.drive_status === "string" ? record.drive_status : null,
      drive_file_id: typeof record.drive_file_id === "string" ? record.drive_file_id : null,
      drive_web_view_link: typeof record.drive_web_view_link === "string" ? record.drive_web_view_link : null,
      drive_folder_path: typeof record.drive_folder_path === "string" ? record.drive_folder_path : null,
      previewUrl,
    });
  }
  return files;
}

export function userVisibleCaption(text: string): string {
  const trimmed = text.trim();
  if (!trimmed || trimmed === DEFAULT_ATTACHMENT_PROMPT) return "";
  return text;
}

export function uploadedFilesForTransport(files: UploadedInputFile[]): UploadedInputFile[] {
  return files
    .filter((file) => !file.uploading)
    .map((file) => {
      const { previewUrl: _previewUrl, uploading: _uploading, ...rest } = file;
      return rest;
    });
}

export function hasPendingComposerUpload(files: UploadedInputFile[], isUploadingFile = false): boolean {
  return isUploadingFile || files.some((file) => file.uploading);
}

export function normalizePendingTurnInput(value: unknown): PendingTurnInput | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const record = value as Record<string, unknown>;
  const uploadedFiles = parseUploadedFiles(record.uploadedFiles);
  const text = typeof record.text === "string" ? record.text.trim() : "";
  if (!text && uploadedFiles.length === 0) {
    return null;
  }
  const connectorIds = Array.isArray(record.connectorIds)
    ? record.connectorIds.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];
  const toolIds = Array.isArray(record.toolIds)
    ? record.toolIds.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];
  return {
    text: text || DEFAULT_ATTACHMENT_PROMPT,
    connectorIds,
    toolIds,
    uploadedFiles,
  };
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
  updated[existingIndex] = mergeArtifactIds(prev[existingIndex], artifact);
  return updated;
}

export function mapStoredMessagesToChatItems(
  messages: ArchivedMessage[],
  options?: { mode?: HistoryMapMode },
): ChatItem[] {
  const mode = options?.mode ?? "full";
  let items: ChatItem[] = [];

  for (let index = 0; index < messages.length; index += 1) {
    const message = messages[index];
    const ts = message.created_at ? new Date(message.created_at).getTime() : Date.now();

    if (message.role === "tool_call") {
      if (mode === "transcript") {
        continue;
      }
      const { tool, args } = parseToolCallText(message.text, message.source);
      if (isWorkflowVisualTool(tool)) {
        continue;
      }
      items.push({
        kind: "event",
        type: "agent_tool_call",
        tool,
        args,
        ts,
      });
      continue;
    }

    if (message.role === "tool_result") {
      if (message.source === "generative_ui") {
        try {
          const parsed = JSON.parse(message.text) as {
            component_type?: string;
            title?: string;
            component?: unknown;
          };
          items.push({
            kind: "event",
            type: "generative_ui",
            component_type: parsed.component_type,
            title: parsed.title || "Generated visual",
            component: parsed.component,
            ts,
          });
        } catch {
          items.push({
            kind: "event",
            type: "generative_ui",
            title: "Generated visual",
            component: message.text,
            ts,
          });
        }
        continue;
      }

      if (message.source === "template_draft") {
        try {
          const parsed = JSON.parse(message.text) as {
            template_id?: string;
            status?: "draft" | "published";
            name?: string;
            description?: string;
            instructions?: string;
            input_fields?: WorkflowTemplateInputField[];
            source_session_id?: string | null;
          };
          if (parsed.template_id) {
            items = upsertTemplateDraftItem(items, parsed as { template_id: string }, ts);
          }
        } catch {
          // Ignore malformed template draft history rows.
        }
        continue;
      }

      if (mode === "transcript") {
        continue;
      }

      items.push({
        kind: "event",
        type: "agent_tool_result",
        tool: message.source || "tool",
        output: message.text,
        ts,
      });
      continue;
    }

    if (message.role === "thinking" || message.role === "agent_thinking") {
      if (mode === "transcript") {
        continue;
      }
      items.push({
        kind: "event",
        type: "agent_thinking",
        content: message.text,
        ts,
      });
      continue;
    }

    // Elicitations: ask_choice, suggest_options, ask_user
    if (
      message.role === "agent" &&
      (message.source === "ask_choice" ||
        message.source === "suggest_options" ||
        message.source === "ask_user")
    ) {
      if (mode === "transcript") {
        // Durable hydrate supplies elicitation cards; skip the plain agent bubble.
        continue;
      }
      const next = messages[index + 1];
      const answered =
        next?.role === "user" &&
        (next.source === "elicitation_response" || next.source === "ask_user_response");
      const timeoutSeconds = DEFAULT_ASK_USER_TIMEOUT_SECONDS;
      const elapsedSec = (Date.now() - ts) / 1000;
      const isSuggestion = message.source === "suggest_options";

      items.push({
        kind: "elicitation",
        elicitation_id: `history-el-${message.id}`,
        question_id: `history-el-${message.id}`,
        mode: isSuggestion ? "suggestion" : "choice",
        question: isSuggestion ? undefined : message.text,
        title: isSuggestion ? message.text.split("\n")[0] : undefined,
        answer: answered ? next?.text : undefined,
        answered,
        timedOut: !answered && elapsedSec >= timeoutSeconds,
        timeout_seconds: timeoutSeconds,
        ts,
      });
      if (answered) {
        index += 1; // consume response; card already marked answered
      }
      continue;
    }

    if (
      message.role === "user" &&
      (message.source === "elicitation_response" || message.source === "ask_user_response")
    ) {
      // Orphan response without a preceding elicitation card — keep as user text in full,
      // skip in transcript (durable path owns the card).
      if (mode === "transcript") {
        continue;
      }
      items.push({
        kind: "message",
        role: "user",
        text: message.text,
        ts,
        attachments: parseUploadedFiles(message.attachments),
      });
      continue;
    }

    if (message.role === "user" || message.role === "agent") {
      const attachments = parseUploadedFiles(message.attachments);
      items.push({
        kind: "message",
        role: message.role,
        text: message.text,
        ts,
        ...(attachments.length > 0 ? { attachments } : {}),
      });
    }
  }

  return items;
}

/**
 * Infer permission card outcome from a bg_task_complete payload.
 * Timeout completes are explicit; any other complete means the user approved
 * (denied requests never emit bg_task_complete from request_permission).
 */
export function inferPermissionDecisionFromComplete(
  success: boolean,
  result: string,
): PermissionDecision {
  const text = (result || "").toLowerCase();
  if (
    text.includes("timed out") ||
    text.includes("did not respond") ||
    text.includes("user did not respond")
  ) {
    return "timed_out";
  }
  // Task outcome (success) is independent of approval; presence of complete
  // after a non-timeout path implies the user approved and work ran.
  void success;
  return "approved";
}

/**
 * A live `permission_request` and its durable `approval_requested` twin can both
 * reach the client for the same approval. Both identify the approval by id, so
 * match on either slot to keep exactly one card.
 */
function isPermissionCardFor(item: ChatItem, approvalId: string): boolean {
  return (
    item.kind === "permission" &&
    (item.approval_id === approvalId || item.task_id === approvalId)
  );
}

function hasPermissionCard(items: ChatItem[], approvalId: string | undefined): boolean {
  if (!approvalId) {
    return false;
  }
  return items.some((item) => isPermissionCardFor(item, approvalId));
}

/** Map run-step permission_request rows → task_id decisions for hydrate. */
export function permissionDecisionsFromRunSteps(
  steps: RunStep[],
): Map<string, PermissionDecision> {
  const decisions = new Map<string, PermissionDecision>();
  for (const step of steps) {
    if (step.step_type !== "permission_request") {
      continue;
    }
    const taskId = step.external_ref;
    if (!taskId) {
      continue;
    }
    const approved = step.metadata?.approved;
    if (approved === true || step.status === "completed") {
      decisions.set(taskId, "approved");
      continue;
    }
    if (approved === false || step.status === "cancelled" || step.status === "failed") {
      const detail = `${step.detail || ""} ${step.error || ""}`.toLowerCase();
      decisions.set(
        taskId,
        detail.includes("timed out") ? "timed_out" : "denied",
      );
    }
  }
  return decisions;
}

export type PermissionStepDetail = {
  taskId: string;
  description: string;
  agent: string;
  estimatedSeconds: number;
  decision?: PermissionDecision;
  decidedAt?: number;
  ts: number;
};

/** Synthesize permission cards from run steps so approvals survive even when
 * durable working-log events are truncated. Cards are deduped by task_id
 * against live/durable cards via isPermissionCardFor. */
export function permissionItemsFromRunSteps(steps: RunStep[]): PermissionStepDetail[] {
  const out: PermissionStepDetail[] = [];
  for (const step of steps) {
    if (step.step_type !== "permission_request") continue;
    const taskId = step.external_ref;
    if (!taskId) continue;
    const meta = step.metadata && typeof step.metadata === "object" ? step.metadata : {};
    const estimatedRaw = (meta as Record<string, unknown>).estimated_seconds;
    const estimatedSeconds =
      typeof estimatedRaw === "number" && Number.isFinite(estimatedRaw) ? estimatedRaw : 120;
    const approved = (meta as Record<string, unknown>).approved;
    let decision: PermissionDecision | undefined;
    if (approved === true || step.status === "completed") decision = "approved";
    else if (approved === false || step.status === "cancelled" || step.status === "failed") {
      const detail = `${step.detail || ""} ${step.error || ""}`.toLowerCase();
      decision = detail.includes("timed out") ? "timed_out" : "denied";
    }
    const ts = step.created_at ? new Date(step.created_at).getTime() : Date.now();
    const decidedAt = step.completed_at ? new Date(step.completed_at).getTime() : undefined;
    out.push({
      taskId,
      description: step.title || step.detail || "Approval required to continue.",
      agent: step.source || "policy",
      estimatedSeconds,
      decision,
      decidedAt: Number.isFinite(decidedAt) ? decidedAt : undefined,
      ts: Number.isFinite(ts) ? ts : Date.now(),
    });
  }
  return out;
}

export type ReduceWorkingLogResult = {
  chatItems: ChatItem[];
  /** Present only when this message updates todos. */
  todoItems?: TodoListItem[];
};

/**
 * Apply one working-log WS message onto chat/todo state using the same shapes
 * as live session handling. Returns null when the message is not a working-log
 * chat/todo mutation (transcript, generative_ui, run APIs, ephemeral, etc.).
 */
export function reduceWorkingLogMessage(
  prevChatItems: ChatItem[],
  msg: WsMessage,
  ts: number,
  options?: {
    prevTodoItems?: TodoListItem[];
    /** Precomputed decisions (e.g. from run steps) applied when the card is created. */
    permissionDecisions?: ReadonlyMap<string, PermissionDecision>;
  },
): ReduceWorkingLogResult | null {
  const permissionDecisions = options?.permissionDecisions;

  switch (msg.type) {
    case "agent_thinking":
      return {
        chatItems: [
          ...prevChatItems,
          { kind: "event", type: msg.type, content: msg.content, ts },
        ],
      };

    case "agent_tool_call":
      if (isWorkflowVisualTool(msg.tool)) {
        return { chatItems: prevChatItems };
      }
      return {
        chatItems: [
          ...prevChatItems,
          {
            kind: "event",
            type: msg.type,
            tool: msg.tool,
            args: msg.args,
            ts,
          },
        ],
      };

    case "agent_tool_result":
      if (isWorkflowVisualTool(msg.tool)) {
        return { chatItems: prevChatItems };
      }
      return {
        chatItems: [
          ...prevChatItems,
          {
            kind: "event",
            type: msg.type,
            tool: msg.tool,
            output: msg.output,
            // `output` is only a one-line summary. The structured payload
            // (search results, artifacts, metadata) lives here and is what
            // rich tool cards render from.
            result_summary: msg.result_summary,
            ts,
          },
        ],
      };

    case "agent_retry":
      return {
        chatItems: [
          ...prevChatItems,
          {
            kind: "event",
            type: msg.type,
            reason: msg.reason,
            attempt: msg.attempt,
            model: msg.model,
            delay_ms: msg.delay_ms,
            trace_id: msg.trace_id,
            ts,
          },
        ],
      };

    case "agent_model_fallback":
      return {
        chatItems: [
          ...prevChatItems,
          {
            kind: "event",
            type: msg.type,
            reason: msg.reason,
            attempt: msg.attempt,
            from_model: msg.from_model,
            to_model: msg.to_model,
            trace_id: msg.trace_id,
            ts,
          },
        ],
      };

    case "mcp_http_request":
    case "mcp_http_response":
    case "mcp_http_error":
    case "verification_result":
      return { chatItems: [...prevChatItems, { kind: "event", ...msg, ts }] };

    case "agent_screenshot":
      return {
        chatItems: [
          ...prevChatItems,
          {
            kind: "event",
            type: msg.type,
            image_b64: msg.image_b64,
            analysis: msg.analysis,
            ts,
          },
        ],
      };

    case "agent_complete":
      return {
        chatItems: [
          ...prevChatItems,
          { kind: "event", type: msg.type, summary: msg.summary, ts },
        ],
      };

    case "agent_delegation":
      return {
        chatItems: [
          ...prevChatItems,
          { kind: "event", type: msg.type, from: msg.from, to: msg.to, ts },
        ],
      };

    case "elicitation_request": {
      const timeoutSeconds =
        typeof msg.timeout_seconds === "number" && msg.timeout_seconds > 0
          ? msg.timeout_seconds
          : DEFAULT_ASK_USER_TIMEOUT_SECONDS;
      const elapsedSec = (Date.now() - ts) / 1000;
      return {
        chatItems: [
          ...prevChatItems,
          {
            kind: "elicitation",
            elicitation_id: msg.elicitation_id,
            question_id: msg.elicitation_id,
            mode: msg.mode,
            question: msg.question,
            options: msg.options,
            allow_free_text: msg.allow_free_text,
            title: msg.title,
            items: msg.items,
            answered: false,
            timedOut: elapsedSec >= timeoutSeconds,
            timeout_seconds: timeoutSeconds,
            ts,
          },
        ],
      };
    }

    case "elicitation_resolved": {
      return {
        chatItems: prevChatItems.map((item) => {
          if (
            item.kind === "elicitation" &&
            (item.elicitation_id === msg.elicitation_id ||
              item.question_id === msg.elicitation_id)
          ) {
            return {
              ...item,
              answered: msg.answered,
              timedOut: !msg.answered,
            };
          }
          if (item.kind === "user_question" && item.question_id === msg.elicitation_id) {
            return {
              ...item,
              answered: msg.answered,
              timedOut: !msg.answered,
            };
          }
          return item;
        }),
      };
    }

    case "user_question": {
      const timeoutSeconds =
        typeof msg.timeout_seconds === "number" && msg.timeout_seconds > 0
          ? msg.timeout_seconds
          : DEFAULT_ASK_USER_TIMEOUT_SECONDS;
      const elapsedSec = (Date.now() - ts) / 1000;
      return {
        chatItems: [
          ...prevChatItems,
          {
            kind: "elicitation",
            elicitation_id: msg.question_id,
            question_id: msg.question_id,
            mode: "choice",
            question: msg.question,
            options: msg.options,
            answered: false,
            timedOut: elapsedSec >= timeoutSeconds,
            timeout_seconds: timeoutSeconds,
            ts,
          },
        ],
      };
    }

    case "user_question_resolved": {
      return {
        chatItems: prevChatItems.map((item) =>
          (item.kind === "elicitation" && (item.elicitation_id === msg.question_id || item.question_id === msg.question_id)) ||
          (item.kind === "user_question" && item.question_id === msg.question_id)
            ? {
                ...item,
                answered: msg.answered,
                timedOut: !msg.answered,
              }
            : item,
        ),
      };
    }

    case "permission_request": {
      if (hasPermissionCard(prevChatItems, msg.approval_id ?? msg.task_id)) {
        return { chatItems: prevChatItems };
      }
      const decision = permissionDecisions?.get(msg.task_id);
      const elapsedSec = (Date.now() - ts) / 1000;
      const budget = Math.max(1, msg.estimated_seconds || 120);
      const timedOutByClock = !decision && elapsedSec >= budget;
      return {
        chatItems: [
          ...prevChatItems,
          {
            kind: "permission",
            task_id: msg.task_id,
            approval_id: msg.approval_id,
            durable_task_id: msg.durable_task_id,
            description: msg.description,
            estimated_seconds: msg.estimated_seconds,
            agent: msg.agent,
            risk: typeof msg.risk === "string" ? msg.risk : undefined,
            action_hash: typeof msg.action_hash === "string" ? msg.action_hash : undefined,
            tool: typeof msg.tool === "string" ? msg.tool : undefined,
            resolved: Boolean(decision) || timedOutByClock,
            decision: decision ?? (timedOutByClock ? "timed_out" : undefined),
            ts,
          },
        ],
      };
    }

    case "approval_requested": {
      const approvalId = msg.approval_id;
      // The durable task id rides on the event envelope, not the payload.
      const durableTaskId = msg.task_id;
      if (!approvalId || hasPermissionCard(prevChatItems, approvalId)) {
        return { chatItems: prevChatItems };
      }
      const decision = permissionDecisions?.get(approvalId);
      const elapsedSec = (Date.now() - ts) / 1000;
      const timedOutByClock = !decision && elapsedSec >= DEFAULT_APPROVAL_TIMEOUT_SECONDS;
      const meta = msg.metadata && typeof msg.metadata === "object" ? (msg.metadata as Record<string, unknown>) : {};
      const metaActionHash = typeof meta.action_hash === "string" ? (meta.action_hash as string) : undefined;
      const metaTool = typeof meta.tool === "string" ? (meta.tool as string) : undefined;
      return {
        chatItems: [
          ...prevChatItems,
          {
            kind: "permission",
            task_id: approvalId,
            approval_id: approvalId,
            durable_task_id: durableTaskId,
            description: msg.description || "Approval required to continue.",
            estimated_seconds: DEFAULT_APPROVAL_TIMEOUT_SECONDS,
            agent: "policy",
            risk: typeof msg.risk === "string" ? msg.risk : typeof meta.risk === "string" ? (meta.risk as string) : undefined,
            action_hash: typeof msg.action_hash === "string" ? msg.action_hash : metaActionHash,
            tool: typeof msg.tool === "string" ? msg.tool : metaTool,
            resolved: Boolean(decision) || timedOutByClock,
            decision: decision ?? (timedOutByClock ? "timed_out" : undefined),
            ts,
          },
        ],
      };
    }

    case "approval_resolved": {
      const approvalId = msg.approval_id;
      if (!approvalId) {
        return { chatItems: prevChatItems };
      }
      const decidedAt =
        typeof msg.decided_at === "number" && Number.isFinite(msg.decided_at)
          ? msg.decided_at
          : Date.now();
      return {
        chatItems: prevChatItems.map((item) =>
          isPermissionCardFor(item, approvalId)
            ? {
                ...item,
                resolved: true,
                decision: msg.approved ? "approved" : "denied",
                decided_at: decidedAt,
                ...(typeof msg.action_hash === "string" ? { action_hash: msg.action_hash } : {}),
              }
            : item,
        ),
      };
    }

    case "bg_task_progress":
      return {
        chatItems: [
          ...prevChatItems,
          {
            kind: "event",
            type: msg.type,
            task_id: msg.task_id,
            progress: msg.progress,
            message: msg.message,
            ts,
          },
        ],
      };

    case "bg_task_complete": {
      const decision = inferPermissionDecisionFromComplete(msg.success, msg.result);
      const withDecision: ChatItem[] = prevChatItems.map((item) => {
        if (item.kind !== "permission" || item.task_id !== msg.task_id) {
          return item;
        }
        const nextDecision: PermissionDecision =
          decision === "timed_out"
            ? "timed_out"
            : item.decision === "denied"
              ? "denied"
              : decision;
        return {
          ...item,
          resolved: true,
          decision: nextDecision,
          decided_at: item.decided_at ?? ts,
        };
      });
      return {
        chatItems: [
          ...withDecision,
          {
            kind: "event",
            type: msg.type,
            task_id: msg.task_id,
            success: msg.success,
            result: msg.result,
            ts,
          },
        ],
      };
    }

    case "subagent_started":
    case "subagent_progress":
    case "subagent_completed":
    case "subagent_failed":
      return {
        chatItems: [
          ...prevChatItems,
          {
            kind: "event",
            type: msg.type,
            subagent_id: msg.subagent_id,
            role: msg.role,
            detail: "detail" in msg ? msg.detail : undefined,
            result: "result" in msg ? msg.result : undefined,
            error: "error" in msg ? msg.error : undefined,
            status: msg.status,
            ts,
          },
        ],
      };

    case "budget_warning":
      return {
        chatItems: [
          ...prevChatItems,
          {
            kind: "event",
            type: msg.type,
            state: msg.state,
            action: msg.action,
            message: msg.message,
            soft_limit: msg.soft_limit,
            hard_limit: msg.hard_limit,
            projected_total_tokens: msg.projected_total_tokens,
            ts,
          },
        ],
      };

    case "resume_recovery":
      return {
        chatItems: [
          ...prevChatItems,
          {
            kind: "event",
            type: msg.type,
            state: msg.state,
            message: msg.message,
            reused_context_digest: msg.reused_context_digest,
            ts,
          },
        ],
      };

    case "context_packet":
      return {
        chatItems: [
          ...prevChatItems,
          {
            kind: "event",
            type: msg.type,
            stage: msg.stage,
            action: msg.action,
            estimated_tokens: msg.estimated_tokens,
            reasoning_model: msg.reasoning_model,
            vision_model: msg.vision_model,
            packet: msg.packet,
            ts,
          },
        ],
      };

    case "todo_list_updated":
      return {
        chatItems: prevChatItems,
        todoItems: Array.isArray(msg.items) ? msg.items : [],
      };

    case "agent_delta": {
      const delta = typeof (msg as unknown as { delta?: unknown }).delta === "string" ? (msg as unknown as { delta: string }).delta : "";
      if (!delta) return { chatItems: prevChatItems };
      const lastIdx = prevChatItems.length - 1;
      const last = prevChatItems[lastIdx];
      if (last && last.kind === "message" && last.role === "agent") {
        const updated = [...prevChatItems];
        updated[lastIdx] = { ...last, text: last.text + delta };
        return { chatItems: updated };
      }
      return { chatItems: [...prevChatItems, { kind: "message", role: "agent", text: delta, ts }] };
    }

    case "agent_stream_chunk": {
      const chunk = typeof (msg as unknown as { chunk?: unknown }).chunk === "string" ? (msg as unknown as { chunk: string }).chunk : "";
      if (!chunk) return { chatItems: prevChatItems };
      const lastIdx = prevChatItems.length - 1;
      const last = prevChatItems[lastIdx];
      if (last && last.kind === "message" && last.role === "agent") {
        const updated = [...prevChatItems];
        updated[lastIdx] = { ...last, text: last.text + chunk };
        return { chatItems: updated };
      }
      return { chatItems: [...prevChatItems, { kind: "message", role: "agent", text: chunk, ts }] };
    }

    case "agent_stream_end":
      return { chatItems: prevChatItems };

    case "error": {
      const last = prevChatItems[prevChatItems.length - 1];
      if (
        last &&
        last.kind === "event" &&
        last.type === "error" &&
        last.message === msg.message &&
        last.code === msg.code
      ) {
        return { chatItems: prevChatItems };
      }
      return {
        chatItems: [
          ...prevChatItems,
          {
            kind: "event",
            type: msg.type,
            code: msg.code,
            message: msg.message,
            detail: msg.detail,
            ts,
          },
        ],
      };
    }

    case "app_preview": {
      const url = typeof msg.url === "string" ? msg.url.trim() : "";
      if (!url) {
        return { chatItems: prevChatItems };
      }
      return {
        chatItems: [
          ...prevChatItems,
          {
            kind: "event",
            type: "app_preview",
            url,
            port: typeof msg.port === "number" ? msg.port : undefined,
            title:
              typeof msg.title === "string" && msg.title.trim()
                ? msg.title
                : "App preview",
            workspace_path:
              typeof msg.workspace_path === "string" ? msg.workspace_path : "",
            ts,
          },
        ],
      };
    }

    // Skipped on purpose (history / REST / ephemeral / page-owned side effects):
    // transcript, generative_ui, template_draft, artifact_created, run_status, step_*,
    // sandbox_status, voice_status, pong, quota_update, ui_action, vnc_url,
    // token_usage, worker_claimed/worker_finished and other durable lifecycle
    // types the working log does not render.
    default:
      return null;
  }
}

/**
 * Fold durable WS working-log events into chat/todo state using the same shapes
 * as the live session page handler. Skips transcript / generative_ui / run APIs
 * (history + REST remain source of truth for those).
 */
export function foldDurableWorkingLogEvents(
  events: Array<{ message: WsMessage; ts: number }>,
  options?: {
    permissionDecisions?: ReadonlyMap<string, PermissionDecision>;
  },
): { chatItems: ChatItem[]; todoItems: TodoListItem[] } {
  let chatItems: ChatItem[] = [];
  let todoItems: TodoListItem[] = [];
  const permissionDecisions = options?.permissionDecisions;

  for (const { message, ts } of events) {
    const reduced = reduceWorkingLogMessage(chatItems, message, ts, {
      prevTodoItems: todoItems,
      permissionDecisions,
    });
    if (!reduced) {
      continue;
    }
    chatItems = reduced.chatItems;
    if (reduced.todoItems) {
      todoItems = reduced.todoItems;
    }
  }

  return { chatItems, todoItems };
}

/** Best-effort todo restore from history when no durable todo_list_updated exists. */
export function extractTodoItemsFromHistory(messages: ArchivedMessage[]): TodoListItem[] {
  let writeIndex = -1;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role !== "tool_call") continue;
    const { tool } = parseToolCallText(message.text, message.source);
    if (tool === "write_todo_list") {
      writeIndex = index;
      break;
    }
  }
  if (writeIndex < 0) return [];

  const writeMessage = messages[writeIndex];
  const { args: writeArgs } = parseToolCallText(writeMessage.text, writeMessage.source);
  const rawItems = writeArgs.items;
  if (!Array.isArray(rawItems)) return [];

  const items: TodoListItem[] = rawItems
    .filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    .map((title) => ({ title: title.trim(), status: "pending" as const }));

  if (items.length === 0) return [];

  for (let index = writeIndex + 1; index < messages.length; index += 1) {
    const message = messages[index];
    if (message.role !== "tool_call") continue;
    const { tool, args } = parseToolCallText(message.text, message.source);
    if (tool !== "update_todo_item") continue;

    const rawIndex = args.item_index;
    const itemIndex =
      typeof rawIndex === "number"
        ? rawIndex
        : typeof rawIndex === "string"
          ? Number.parseInt(rawIndex, 10)
          : NaN;
    if (!Number.isFinite(itemIndex) || itemIndex < 1 || itemIndex > items.length) {
      continue;
    }

    const status = args.status;
    if (status !== "pending" && status !== "in_progress" && status !== "done") {
      continue;
    }

    const target = items[itemIndex - 1];
    target.status = status;
    if (typeof args.note === "string" && args.note.trim()) {
      target.note = args.note.trim();
    }
  }

  return items;
}

/** Merge transcript history items with durable working-log items by timestamp. */
export function mergeChatItemsByTimestamp(
  historyItems: ChatItem[],
  durableItems: ChatItem[],
): ChatItem[] {
  if (durableItems.length === 0) {
    return historyItems;
  }
  if (historyItems.length === 0) {
    return durableItems;
  }
  const merged = [...historyItems, ...durableItems];
  merged.sort((left, right) => left.ts - right.ts);
  return merged;
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
