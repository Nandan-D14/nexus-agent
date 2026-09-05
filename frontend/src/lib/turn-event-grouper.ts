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
    /**
     * Full normalized tool payload (`status`/`summary`/`metadata`). `output` is
     * only a human-readable summary line, so rich cards (search results,
     * artifacts) must read their structured data from here.
     */
    resultSummary?: Record<string, unknown>;
  };
  callTs: number;
  status: "running" | "completed" | "failed";
};

export type GroupedEvent =
  | ToolInvocation
  | { kind: "screenshot"; image_b64?: string; analysis?: string; ts: number }
  | { kind: "error"; message: string; code?: string; count: number; ts: number }
  | {
      kind: "retry";
      reason: string;
      attempt?: number;
      model?: string;
      nextModel?: string;
      delayMs?: number;
      ts: number;
    }
  | { kind: "thinking"; text: string; ts: number }
  | {
      kind: "approval";
      approvalId: string;
      description: string;
      agent?: string;
      risk?: string;
      tool?: string;
      decision: "pending" | "approved" | "denied" | "timed_out";
      actionHash?: string;
      decidedAt?: number;
      ts: number;
    }
  | {
      kind: "bg_progress";
      taskId?: string;
      progress?: number;
      message: string;
      complete?: boolean;
      success?: boolean;
      ts: number;
    }
  | {
      kind: "subagent_status";
      role?: string;
      status: "started" | "progress" | "completed" | "failed";
      detail: string;
      ts: number;
    }
  | { kind: "delegation"; from: string; to: string; ts: number };

export type TaskGroup = {
  id: string;
  title: string;
  status: "running" | "completed" | "failed";
  steps: GroupedEvent[];
  ts: number;
  /** Timestamp of the last step, so the UI can show total elapsed time. */
  endTs: number;
};

export type GenerativeUiSegment = {
  kind: "generative_ui";
  component_type?: string;
  title: string;
  component: unknown;
  ts: number;
};

export type ArtifactCreatedSegment = {
  kind: "artifact_created";
  artifact: Record<string, unknown>;
  ts: number;
};

export type AppPreviewSegment = {
  kind: "app_preview";
  url: string;
  port?: number;
  title: string;
  workspacePath?: string;
  ts: number;
};

export type CanvasDocumentSegment = {
  kind: "canvas_document";
  document: Record<string, unknown>;
  ts: number;
};

export type TemplateDraftSegment = {
  kind: "template_draft";
  template_id: string;
  status?: "draft" | "published";
  name?: string;
  description?: string;
  instructions?: string;
  input_fields?: unknown;
  dismissed?: boolean;
  ts: number;
};

export type TurnEventSegment =
  | { kind: "task_group"; data: TaskGroup; ts: number }
  | GenerativeUiSegment
  | ArtifactCreatedSegment
  | AppPreviewSegment
  | CanvasDocumentSegment
  | TemplateDraftSegment;

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
  "todo_list_updated",
  "ui_action",
  "sandbox_terminal",
  "sandbox_editor",
  "vnc_url",
  "transcript",
]);

export function groupTurnEvents(events: ChatEvent[]): TurnEventSegment[] {
  const segments: TurnEventSegment[] = [];
  const pendingTools = new Map<string, ToolInvocation[]>();
  const pendingToolsByStep = new Map<string, ToolInvocation>();
  /** Identical errors within a task collapse into one counted row. */
  const errorSteps = new Map<string, Extract<GroupedEvent, { kind: "error" }>>();
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
    currentTask.endTs = currentTask.steps.reduce((latest, step) => {
      const stepEnd =
        step.kind === "tool_invocation" ? (step.result?.ts ?? step.callTs) : step.ts;
      return Math.max(latest, stepEnd);
    }, currentTask.ts);
    segments.push({ kind: "task_group", data: currentTask, ts: currentTask.ts });
    errorSteps.clear();
    currentTask = null;
  }

  /**
   * Repeats of the same failure (a retried step that keeps hitting the same
   * wall) collapse onto one row with a count instead of stacking identical
   * lines, which they did whenever another step landed in between.
   */
  function pushError(message: string, code: string | undefined, ts: number) {
    const task = currentTask;
    if (!task) return;
    const key = `${code ?? ""}::${message}`;
    const existing = errorSteps.get(key);
    if (existing) {
      existing.count += 1;
      return;
    }
    const step: Extract<GroupedEvent, { kind: "error" }> = {
      kind: "error",
      message,
      code,
      count: 1,
      ts,
    };
    errorSteps.set(key, step);
    task.steps.push(step);
  }

  for (const event of events) {
    if (FILTERED_TYPES.has(event.type)) {
      continue;
    }

    if (event.type === "artifact_created") {
      finalizeTask();
      const artifact =
        event.artifact && typeof event.artifact === "object"
          ? (event.artifact as Record<string, unknown>)
          : null;
      if (artifact) {
        segments.push({
          kind: "artifact_created",
          artifact,
          ts: event.ts,
        });
      }
      continue;
    }

    if (event.type === "app_preview") {
      finalizeTask();
      const url = typeof event.url === "string" ? event.url.trim() : "";
      if (url) {
        segments.push({
          kind: "app_preview",
          url,
          port: typeof event.port === "number" ? event.port : undefined,
          title:
            typeof event.title === "string" && event.title.trim()
              ? event.title
              : "App preview",
          workspacePath:
            typeof event.workspace_path === "string"
              ? event.workspace_path
              : undefined,
          ts: event.ts,
        });
      }
      continue;
    }

    if (event.type === "canvas_document") {
      finalizeTask();
      const document =
        event.document && typeof event.document === "object"
          ? (event.document as Record<string, unknown>)
          : null;
      if (document) {
        segments.push({
          kind: "canvas_document",
          document,
          ts: event.ts,
        });
      }
      continue;
    }

    if (event.type === "template_draft") {
      finalizeTask();
      const templateId = typeof event.template_id === "string" ? event.template_id : "";
      if (templateId) {
        segments.push({
          kind: "template_draft",
          template_id: templateId,
          status: event.status === "published" ? "published" : "draft",
          name: typeof event.name === "string" ? event.name : "",
          description: typeof event.description === "string" ? event.description : "",
          instructions: typeof event.instructions === "string" ? event.instructions : "",
          input_fields: event.input_fields,
          dismissed: Boolean(event.dismissed),
          ts: event.ts,
        });
      }
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
          endTs: event.ts,
        };
      }
      // Always record thinking as a step — including the first event that opens
      // the task. Previously the opener only set `title`, so single-chunk (and
      // the start of multi-chunk) reasoning never reached ThinkingReasoning.
      const task = currentTask;
      task.steps.push({
        kind: "thinking",
        text: content,
        ts: event.ts,
      });
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
          endTs: event.ts,
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
      const resultSummary =
        event.result_summary && typeof event.result_summary === "object"
          ? (event.result_summary as Record<string, unknown>)
          : undefined;

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
          resultSummary,
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
          result: { output, ts: event.ts, resultSummary },
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
          endTs: event.ts,
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
          endTs: event.ts,
        };
      }
      pushError(
        String(event.error || "MCP request failed"),
        typeof event.error_type === "string" ? event.error_type : "MCP_HTTP_ERROR",
        event.ts,
      );
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
          endTs: event.ts,
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

    if (event.type === "bg_task_progress" || event.type === "bg_task_complete") {
      if (!currentTask) {
        taskIndex++;
        currentTask = {
          id: `task-${taskIndex}-${event.ts}`,
          title: "Background task",
          status: "running",
          steps: [],
          ts: event.ts,
          endTs: event.ts,
        };
      }
      const complete = event.type === "bg_task_complete";
      const message = complete
        ? String(event.result || (event.success ? "Background task finished." : "Background task failed."))
        : String(event.message || "Background task running...");
      currentTask.steps.push({
        kind: "bg_progress",
        taskId: typeof event.task_id === "string" ? event.task_id : undefined,
        progress: typeof event.progress === "number" ? event.progress : undefined,
        message,
        complete,
        success: typeof event.success === "boolean" ? event.success : undefined,
        ts: event.ts,
      });
      continue;
    }

    if (
      event.type === "subagent_started" ||
      event.type === "subagent_progress" ||
      event.type === "subagent_completed" ||
      event.type === "subagent_failed"
    ) {
      if (!currentTask) {
        taskIndex++;
        currentTask = {
          id: `task-${taskIndex}-${event.ts}`,
          title: "Background agents",
          status: "running",
          steps: [],
          ts: event.ts,
          endTs: event.ts,
        };
      }
      const status =
        event.type === "subagent_started"
          ? "started"
          : event.type === "subagent_progress"
            ? "progress"
            : event.type === "subagent_completed"
              ? "completed"
              : "failed";
      const detail = String(
        event.detail || event.result || event.error ||
          (status === "started" ? "started" : status === "completed" ? "finished" : "working..."),
      );
      currentTask.steps.push({
        kind: "subagent_status",
        role: typeof event.role === "string" ? event.role : undefined,
        status,
        detail,
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
          endTs: event.ts,
        };
      }
      pushError(
        String(event.message || "Failed"),
        typeof event.code === "string" ? event.code : undefined,
        event.ts,
      );
      continue;
    }

    if (event.type === "agent_delegation") {
      if (!currentTask) {
        taskIndex++;
        currentTask = {
          id: `task-${taskIndex}-${event.ts}`,
          title: "Agent handoff",
          status: "running",
          steps: [],
          ts: event.ts,
          endTs: event.ts,
        };
      }
      currentTask.steps.push({
        kind: "delegation",
        from: String(event.from || ""),
        to: String(event.to || ""),
        ts: event.ts,
      });
      continue;
    }

    if (event.type === "permission_request" || event.type === "approval_requested") {
      if (!currentTask) {
        taskIndex++;
        currentTask = {
          id: `task-${taskIndex}-${event.ts}`,
          title: "Awaiting approval",
          status: "running",
          steps: [],
          ts: event.ts,
          endTs: event.ts,
        };
      }
      const rawId =
        typeof event.approval_id === "string" && event.approval_id
          ? event.approval_id
          : typeof event.task_id === "string" && event.task_id
            ? event.task_id
            : `approval-${event.ts}`;
      const meta =
        event.metadata && typeof event.metadata === "object" && !Array.isArray(event.metadata)
          ? (event.metadata as Record<string, unknown>)
          : {};
      const description =
        (typeof event.description === "string" && event.description.trim()) ||
        "Approval required to continue.";
      currentTask.steps.push({
        kind: "approval",
        approvalId: String(rawId),
        description: sanitizeDisplayText(description) || "Approval required to continue.",
        agent: typeof event.agent === "string" ? event.agent : "policy",
        risk:
          typeof event.risk === "string"
            ? event.risk
            : typeof meta.risk === "string"
              ? String(meta.risk)
              : undefined,
        tool:
          typeof event.tool === "string"
            ? String(event.tool)
            : typeof meta.tool === "string"
              ? String(meta.tool)
              : undefined,
        decision: "pending",
        actionHash:
          typeof event.action_hash === "string"
            ? String(event.action_hash)
            : typeof meta.action_hash === "string"
              ? String(meta.action_hash)
              : undefined,
        ts: event.ts,
      });
      continue;
    }

    if (event.type === "approval_resolved") {
      const rawId =
        typeof event.approval_id === "string" && event.approval_id
          ? String(event.approval_id)
          : typeof event.task_id === "string" && event.task_id
            ? String(event.task_id)
            : null;
      const approved = event.approved === true;
      const statusText =
        typeof event.status === "string" ? event.status.toLowerCase() : "";
      const timedOut =
        statusText.includes("timeout") ||
        statusText.includes("expired") ||
        (typeof event.reason === "string" &&
          String(event.reason).toLowerCase().includes("timeout"));
      const decision = timedOut ? "timed_out" : approved ? "approved" : "denied";
      let matched = false;
      if (rawId && currentTask) {
        for (const step of currentTask.steps) {
          if (step.kind === "approval" && step.approvalId === rawId) {
            step.decision = decision;
            step.decidedAt = event.ts;
            if (typeof event.action_hash === "string") {
              step.actionHash = String(event.action_hash);
            }
            matched = true;
            break;
          }
        }
      }
      if (!matched) {
        if (!currentTask) {
          taskIndex++;
          currentTask = {
            id: `task-${taskIndex}-${event.ts}`,
            title: "Approval resolved",
            status: "running",
            steps: [],
            ts: event.ts,
            endTs: event.ts,
          };
        }
        currentTask.steps.push({
          kind: "approval",
          approvalId: rawId ?? `approval-${event.ts}`,
          description: "Approval resolved",
          decision,
          decidedAt: event.ts,
          actionHash:
            typeof event.action_hash === "string" ? String(event.action_hash) : undefined,
          ts: event.ts,
        });
      }
      continue;
    }
  }

  finalizeTask();
  return segments;
}
