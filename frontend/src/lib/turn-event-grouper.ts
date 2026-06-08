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
 * Tool call/result pairing uses FIFO per tool name
 * (mirrors the orchestrator's _tool_step_ids matching logic).
 */

export type ChatEvent = {
  type: string;
  ts: number;
  [key: string]: unknown;
};

export type ToolInvocation = {
  kind: "tool_invocation";
  tool: string;
  args: Record<string, unknown>;
  result?: { output: string; ts: number };
  callTs: number;
  status: "running" | "completed";
};

export type GroupedEvent =
  | ToolInvocation
  | { kind: "screenshot"; image_b64?: string; analysis?: string; ts: number }
  | { kind: "error"; message: string; code?: string; ts: number };

export type TaskGroup = {
  id: string;
  title: string;
  status: "running" | "completed";
  steps: GroupedEvent[];
  summary?: string;
  ts: number;
};

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

export function groupTurnEvents(events: ChatEvent[]): TaskGroup[] {
  const tasks: TaskGroup[] = [];
  const pendingTools = new Map<string, ToolInvocation[]>();
  let currentTask: TaskGroup | null = null;
  let lastThinkingInTask: string | null = null;
  let taskIndex = 0;

  function finalizeTask() {
    if (!currentTask) return;
    if (lastThinkingInTask && currentTask.steps.length > 0) {
      currentTask.summary = lastThinkingInTask;
    }
    const allDone = currentTask.steps.every(
      (s) => s.kind !== "tool_invocation" || s.status === "completed",
    );
    currentTask.status = allDone ? "completed" : "running";
    tasks.push(currentTask);
    currentTask = null;
    lastThinkingInTask = null;
  }

  for (const event of events) {
    if (event.type.startsWith("bg_task") || FILTERED_TYPES.has(event.type)) {
      continue;
    }

    if (event.type === "agent_thinking") {
      const content = typeof event.content === "string" ? event.content : "Thinking...";

      if (currentTask && currentTask.steps.length > 0) {
        finalizeTask();
      }

      if (!currentTask) {
        taskIndex++;
        currentTask = {
          id: `task-${taskIndex}-${event.ts}`,
          title: content.length > 80 ? content.slice(0, 80) + "..." : content,
          status: "running",
          steps: [],
          ts: event.ts,
        };
      }

      lastThinkingInTask = content;
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
        callTs: event.ts,
        status: "running",
      };

      if (!pendingTools.has(tool)) {
        pendingTools.set(tool, []);
      }
      pendingTools.get(tool)!.push(invocation);
      currentTask.steps.push(invocation);
      continue;
    }

    if (event.type === "agent_tool_result") {
      const tool = String(event.tool || "");
      const output = String(event.output || "Success");

      const queue = pendingTools.get(tool);
      if (queue && queue.length > 0) {
        const invocation = queue.shift()!;
        invocation.result = { output, ts: event.ts };
        invocation.status = "completed";
        if (queue.length === 0) {
          pendingTools.delete(tool);
        }
      } else if (currentTask) {
        currentTask.steps.push({
          kind: "tool_invocation",
          tool,
          args: {},
          result: { output, ts: event.ts },
          callTs: event.ts,
          status: "completed",
        });
      }
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
  return tasks;
}
