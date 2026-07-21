/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

/**
 * Groups flat turn events into a hierarchy of task groups.
 *
 * Each task group starts with an agent_thinking event and contains
 * all subsequent tool calls, results, and screenshots until the
 * next thinking event that follows a tool result.
 *
 * Generative UI (Thesys C1) events are returned as standalone timeline
 * segments so they render outside the thought/log accordion.
 *
 * Tool call/result pairing uses FIFO per tool name
 * (mirrors the orchestrator's _tool_step_ids matching logic).
 */

export type ChatEvent = {
  type: string;
  ts: number;
  [key: string]: unknown;
};

/**
 * Defense in depth for displayed model-influenced text. A model gateway can
 * leak JS coercion artifacts (a stringified reasoning payload becomes
 * "[object Object]") into thinking/tool text. The backend sanitizes too, but
 * the UI must never render this garbage. Also coerces non-strings safely.
 */
export function sanitizeDisplayText(value: unknown): string {
  const text =
    typeof value === "string" ? value : value == null ? "" : String(value);
  if (!text) return "";
  return text
    .replace(/\s*,?\s*\[object (?:Object|Array|Null|Undefined)\]\s*,?/gi, " ")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/ *\n */g, "\n")
    .trim();
}

export type ToolInvocation = {
  kind: "tool_invocation";
  tool: string;
  args: Record<string, unknown>;
  stepId?: string;
  result?: {
    output: string;
    ts: number;
    status?: string;
    errorCode?: string;
    retryReason?: string;
    latencyMs?: number;
  };
  callTs: number;
  status: "running" | "completed" | "failed";
};

export type GroupedEvent =
  | ToolInvocation
  | { kind: "screenshot"; image_b64?: string; analysis?: string; ts: number }
  | { kind: "error"; message: string; code?: string; ts: number }
  | {
      kind: "retry";
      reason: string;
      attempt?: number;
      model?: string;
      nextModel?: string;
      delayMs?: number;
      ts: number;
    }
  | { kind: "thinking"; text: string; ts: number };

export type TaskGroup = {
  id: string;
  title: string;
  status: "running" | "completed" | "failed";
  steps: GroupedEvent[];
  ts: number;
};

export type GenerativeUiSegment = {
  kind: "generative_ui";
  component_type?: string;
  title: string;
  component: unknown;
  ts: number;
};

export type TurnEventSegment =
  | { kind: "task_group"; data: TaskGroup; ts: number }
  | GenerativeUiSegment;

const FILTERED_TYPES = new Set([
  "agent_complete",
  "context_packet",
  "sandbox_status",
  "voice_status",
  "budget_warning",
  "resume_recovery",
  "pong",
  "quota_update",
  "run_status",
  "step_started",
  "step_completed",
  "step_failed",
  "artifact_created",
  "todo_list_updated",
  "ui_action",
  "vnc_url",
  "transcript",
]);

export function groupTurnEvents(events: ChatEvent[]): TurnEventSegment[] {
  const segments: TurnEventSegment[] = [];
  const pendingTools = new Map<string, ToolInvocation[]>();
  const pendingToolsByStep = new Map<string, ToolInvocation>();
  let currentTask: TaskGroup | null = null;
  let taskIndex = 0;

  function finalizeTask() {
    if (!currentTask) return;
    const anyFailed = currentTask.steps.some(
      (s) => s.kind === "tool_invocation" && s.status === "failed",
    );
    const allDone = currentTask.steps.every(
      (s) => s.kind !== "tool_invocation" || s.status !== "running",
    );
    currentTask.status = anyFailed ? "failed" : allDone ? "completed" : "running";
    segments.push({ kind: "task_group", data: currentTask, ts: currentTask.ts });
    currentTask = null;
  }

  for (const event of events) {
    if (event.type.startsWith("bg_task") || FILTERED_TYPES.has(event.type)) {
      continue;
    }

    if (event.type === "generative_ui") {
      finalizeTask();
      segments.push({
        kind: "generative_ui",
        component_type:
          typeof event.component_type === "string" ? event.component_type : undefined,
        title:
          typeof event.title === "string" && event.title.trim()
            ? event.title
            : "Generated visual",
        component: event.component,
        ts: event.ts,
      });
      continue;
    }

    if (event.type === "agent_thinking") {
      const content = sanitizeDisplayText(event.content) || "Thinking...";

      if (!currentTask) {
        taskIndex++;
        currentTask = {
          id: `task-${taskIndex}-${event.ts}`,
          title: content.length > 80 ? content.slice(0, 80) + "..." : content,
          status: "running",
          steps: [],
          ts: event.ts,
        };
      } else {
        currentTask.steps.push({
          kind: "thinking",
          text: content,
          ts: event.ts,
        });
      }
      continue;
    }

    if (event.type === "agent_tool_call") {
      const tool = String(event.tool || "");
      if (!currentTask) {
        taskIndex++;
        currentTask = {
          id: `task-${taskIndex}-${event.ts}`,
          title: tool
            ? tool
                .split("_")
                .filter(Boolean)
                .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
                .join(" ")
            : "Tool Call",
          status: "running",
          steps: [],
          ts: event.ts,
        };
      }
      const args =
        event.args && typeof event.args === "object" && !Array.isArray(event.args)
          ? (event.args as Record<string, unknown>)
          : {};

      const invocation: ToolInvocation = {
        kind: "tool_invocation",
        tool,
        args,
        stepId: typeof event.step_id === "string" ? event.step_id : undefined,
        callTs: event.ts,
        status: "running",
      };

      if (!pendingTools.has(tool)) {
        pendingTools.set(tool, []);
      }
      pendingTools.get(tool)!.push(invocation);
      if (invocation.stepId) {
        pendingToolsByStep.set(invocation.stepId, invocation);
      }
      currentTask.steps.push(invocation);
      continue;
    }

    if (event.type === "agent_tool_result") {
      const tool = String(event.tool || "");
      const output = sanitizeDisplayText(event.output) || "Success";
      const stepId = typeof event.step_id === "string" ? event.step_id : undefined;
      const status = typeof event.status === "string" ? event.status : "success";

      const queue = pendingTools.get(tool);
      const matchedByStep = stepId ? pendingToolsByStep.get(stepId) : undefined;
      if (matchedByStep || (queue && queue.length > 0)) {
        const invocation = matchedByStep ?? queue!.shift()!;
        if (matchedByStep && queue) {
          const index = queue.indexOf(matchedByStep);
          if (index >= 0) queue.splice(index, 1);
        }
        if (invocation.stepId) pendingToolsByStep.delete(invocation.stepId);
        invocation.result = {
          output,
          ts: event.ts,
          status,
          errorCode: typeof event.error_code === "string" ? event.error_code : undefined,
          retryReason:
            typeof event.retry_reason === "string" ? event.retry_reason : undefined,
          latencyMs:
            typeof event.latency_ms === "number" ? event.latency_ms : undefined,
        };
        invocation.status = ["error", "failed", "cancelled", "denied"].includes(status)
          ? "failed"
          : "completed";
        if (queue && queue.length === 0) {
          pendingTools.delete(tool);
        }
      } else if (currentTask) {
        currentTask.steps.push({
          kind: "tool_invocation",
          tool,
          args: {},
          result: { output, ts: event.ts },
          callTs: event.ts,
          status: ["error", "failed", "cancelled", "denied"].includes(status)
            ? "failed"
            : "completed",
        });
      }
      continue;
    }

    if (event.type === "agent_retry" || event.type === "agent_model_fallback") {
      if (!currentTask) {
        taskIndex++;
        currentTask = {
          id: `task-${taskIndex}-${event.ts}`,
          title: "Recovering from failed step",
          status: "running",
          steps: [],
          ts: event.ts,
        };
      }
      currentTask.steps.push({
        kind: "retry",
        reason: String(event.reason || "Retrying after a failed step"),
        attempt: typeof event.attempt === "number" ? event.attempt : undefined,
        model: typeof event.model === "string"
          ? event.model
          : typeof event.from_model === "string"
            ? event.from_model
            : undefined,
        nextModel: typeof event.to_model === "string" ? event.to_model : undefined,
        delayMs: typeof event.delay_ms === "number" ? event.delay_ms : undefined,
        ts: event.ts,
      });
      continue;
    }

    if (event.type === "mcp_http_error") {
      if (!currentTask) {
        taskIndex++;
        currentTask = {
          id: `task-${taskIndex}-${event.ts}`,
          title: "Connector request failed",
          status: "running",
          steps: [],
          ts: event.ts,
        };
      }
      currentTask.steps.push({
        kind: "error",
        message: String(event.error || "MCP request failed"),
        code: typeof event.error_type === "string" ? event.error_type : "MCP_HTTP_ERROR",
        ts: event.ts,
      });
      continue;
    }

    if (event.type === "agent_screenshot") {
      if (!currentTask) {
        taskIndex++;
        currentTask = {
          id: `task-${taskIndex}-${event.ts}`,
          title: "Analyzing screen",
          status: "running",
          steps: [],
          ts: event.ts,
        };
      }
      currentTask.steps.push({
        kind: "screenshot",
        image_b64: typeof event.image_b64 === "string" ? event.image_b64 : undefined,
        analysis: typeof event.analysis === "string" ? event.analysis : undefined,
        ts: event.ts,
      });
      continue;
    }

    if (event.type === "error") {
      if (!currentTask) {
        taskIndex++;
        currentTask = {
          id: `task-${taskIndex}-${event.ts}`,
          title: "Error",
          status: "running",
          steps: [],
          ts: event.ts,
        };
      }
      currentTask.steps.push({
        kind: "error",
        message: String(event.message || "Failed"),
        code: typeof event.code === "string" ? event.code : undefined,
        ts: event.ts,
      });
      continue;
    }
  }

  finalizeTask();
  return segments;
}
