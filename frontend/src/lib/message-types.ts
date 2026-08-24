/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

/**
 * Discriminated union types for all WebSocket messages.
 *
 * Binary frames (audio) are handled separately by the WebSocket hook.
 * These types cover only the JSON text frames.
 */

// ── Server -> Client (Text frames) ─────────────────────────────────

export type PlanQuota = {
  limit: number;
  used: number;
  remaining: number;
  unit: "credits" | string;
  plan_id: string;
  plan_name: string;
  price_usd: number;
  plan?: {
    id: string;
    name: string;
    price_usd: number;
    status: string;
  };
  credits?: {
    limit: number;
    used: number;
    remaining: number;
    unit: "credits" | string;
    unit_usd?: number;
  };
  tokens?: {
    used: number;
    safety_limit: number;
  };
};

export const DEFAULT_PLAN_QUOTA: PlanQuota = {
  limit: 4000,
  used: 0,
  remaining: 4000,
  unit: "credits",
  plan_id: "starter_5",
  plan_name: "$5 Starter",
  price_usd: 5,
  plan: {
    id: "starter_5",
    name: "$5 Starter",
    price_usd: 5,
    status: "active",
  },
  credits: {
    limit: 4000,
    used: 0,
    remaining: 4000,
    unit: "credits",
    unit_usd: 0.001,
  },
  tokens: {
    used: 0,
    safety_limit: 100000,
  },
};

export type WsEventMeta = {
  event_id?: string;
  task_id?: string;
  run_id?: string;
  trace_id?: string;
  step_id?: string;
  parent_step_id?: string;
  provider?: string;
  model?: string;
  seq?: number;
};

export type WsMessage = WsEventMeta & (
  | { type: "sandbox_status"; status: string }
  | { type: "vnc_url"; url: string }
  | { type: "transcript"; role: "user" | "agent"; text: string }
  | { type: "run_status"; run: RunInfo | null }
  | { type: "step_started"; step: RunStep }
  | { type: "step_completed"; step: RunStep }
  | { type: "step_failed"; step: RunStep }
  | { type: "artifact_created"; artifact: RunArtifact }
  | { type: "agent_thinking"; content: string }
  | {
      type: "agent_tool_call";
      tool: string;
      args: Record<string, unknown>;
      workflow_step_id?: string | null;
      status?: string;
      expected_outcome?: string;
      verification_method?: string;
      retry_policy?: Record<string, unknown>;
      completion_condition?: string;
    }
  | {
      type: "agent_tool_result";
      tool: string;
      output: string;
      workflow_step_id?: string | null;
      result_summary?: Record<string, unknown>;
      status?: string;
      error_code?: string;
      retry_reason?: string;
      latency_ms?: number;
      evidence?: string[];
      artifacts?: Array<Record<string, unknown>>;
      remaining_work?: string[];
      retryable?: boolean;
      verified?: boolean;
    }
  | {
      type: "agent_retry";
      attempt: number;
      max_attempts: number;
      delay_ms: number;
      reason: string;
    }
  | {
      type: "agent_model_fallback";
      from_model: string;
      to_model: string;
      reason: string;
      attempt: number;
    }
  | {
      type: "mcp_http_request" | "mcp_http_response" | "mcp_http_error";
      operation: string;
      tool?: string;
      server: string;
      method?: string;
      status_code?: number;
      latency_ms?: number;
      error_type?: string;
      error?: string;
    }
  | {
      type: "verification_result";
      verified: boolean;
      status: "completed" | "failed" | "partial" | "blocked";
      method: string;
      summary: string;
      error_code?: string;
      evidence?: string[];
      remaining_work?: string[];
      retryable?: boolean;
      action_count?: number;
    }
  | { type: "agent_screenshot"; image_b64: string; analysis: string }
  | { type: "agent_complete"; summary: string }
  | { type: "agent_delegation"; from: string; to: string }
  | {
      type: "generative_ui";
      component_type?: string;
      title?: string;
      component?: unknown;
    }
  | {
      type: "template_draft";
      template_id: string;
      status?: "draft" | "published";
      name?: string;
      description?: string;
      instructions?: string;
      input_fields?: WorkflowTemplateInputField[];
      source_session_id?: string | null;
    }
  | {
      type: "user_question";
      question_id: string;
      question: string;
      timeout_seconds?: number;
      options?: string[];
    }
  | { type: "user_question_resolved"; question_id: string; answered: boolean }
  | {
      type: "permission_request";
      task_id: string;
      description: string;
      estimated_seconds: number;
      agent: string;
      approval_id?: string;
      durable_task_id?: string;
      risk?: string;
    }
  // Durable twin of permission_request, written to the task event log by the
  // approval store. In worker-executed runs this is the ONLY approval signal
  // that reaches the browser (the worker's own socket is a no-op), so it must
  // render the same card. `task_id` here is the durable task, not the approval.
  | {
      type: "approval_requested";
      approval_id: string;
      description?: string;
      risk?: string;
      metadata?: Record<string, unknown>;
    }
  | {
      type: "approval_resolved";
      approval_id: string;
      approved: boolean;
      status?: string;
      action_hash?: string;
    }
  // Durable worker died before (or instead of) producing a normal completion.
  // Without this the client keeps waiting on a run that can never report back.
  | { type: "worker_failed"; error?: string; attempt?: number; origin?: string; reason?: string; error_code?: string }
  // Durable lifecycle: the turn was accepted onto the queue, claimed, or the
  // worker released it. `worker_finished` is terminal for the run.
  | { type: "run_queued"; queue?: Record<string, unknown> }
  // `reattached` marks a claim replayed to a socket that connected while the
  // run was already executing (i.e. after a refresh), not a fresh claim.
  | { type: "worker_claimed"; worker_id?: string; attempt?: number; claim_generation?: number; reattached?: boolean }
  | { type: "worker_finished"; status?: string; summary?: string }
  | { type: "enqueue_rejected"; provider?: string; reason?: string }
  // A prompt arrived while a run was still executing. The server did NOT accept
  // the prompt, but it re-attached this socket to the running run, so live
  // progress follows. Distinct from `error` so the UI shows work in progress
  // rather than a dead end. `pending_text` echoes the refused prompt so the
  // composer can restore it instead of silently dropping it.
  | {
      type: "run_busy";
      code?: string;
      message?: string;
      run_status?: string;
      pending_text?: string;
    }
  // Coarse orchestrator progress that is not tied to a tool call, e.g. a turn
  // waiting behind the previous turn on the same session.
  | { type: "agent_status"; status: string; message?: string }
  | { type: "bg_task_progress"; task_id: string; progress: number; message: string }
  | { type: "bg_task_complete"; task_id: string; success: boolean; result: string }
  | {
      type: "subagent_started";
      subagent_id?: string;
      role?: string;
      type_name?: string;
      status?: string;
    }
  | {
      type: "subagent_progress";
      subagent_id?: string;
      role?: string;
      detail?: string;
      status?: string;
    }
  | {
      type: "subagent_completed";
      subagent_id?: string;
      role?: string;
      result?: string;
      status?: string;
    }
  | {
      type: "subagent_failed";
      subagent_id?: string;
      role?: string;
      error?: string;
      status?: string;
    }
  | { type: "todo_list_updated"; items: Array<{ title: string; status: "pending" | "in_progress" | "done"; note?: string }> }
  | { type: "voice_status"; status: string; message: string }
  | ({ type: "quota_update" } & PlanQuota)
  | {
      type: "token_usage";
      model: string;
      input_tokens: number;
      output_tokens: number;
      total_tokens: number;
      max_tokens: number;
      session_input_tokens?: number;
      session_output_tokens?: number;
      session_total_tokens?: number;
    }
  | {
      type: "budget_warning";
      state: string;
      action: string;
      message: string;
      soft_limit: number;
      hard_limit: number;
      projected_total_tokens?: number;
    }
  | {
      type: "resume_recovery";
      state: string;
      message: string;
      reused_context_digest: string;
    }
  | {
      type: "context_packet";
      stage: string;
      action: string;
      estimated_tokens?: number;
      reasoning_model: string;
      vision_model: string;
      packet: ContextPacket;
    }
  | { type: "error"; code: string; message: string; detail?: string }
  | { type: "pong" }
  | { type: "ui_action"; action: "switch_tab"; target: "canvas" | "workflow" | "desktop" | "terminal" | "editor" | "artifacts" | "files" | "workspace"; reason?: string }
  | { type: "sandbox_terminal"; phase: "start" | "result"; command?: string; cwd?: string; stdout?: string; stderr?: string; exit_code?: number }
  | { type: "sandbox_editor"; phase: "start" | "result"; path?: string; action?: "write" | "read" | "list"; content?: string; append?: boolean; bytes_written?: number }
  | { type: "agent_delta"; delta: string; seq?: number; run_id?: string }
  | { type: "agent_stream_chunk"; chunk: string; seq?: number; run_id?: string }
  | { type: "agent_stream_end"; run_id?: string }
);

// ── Client -> Server (Text frames) ─────────────────────────────────

export type WsCommand =
  | {
      type: "text_input";
      text: string;
      connector_ids?: string[];
      tool_ids?: string[];
      uploaded_files?: UploadedInputFile[];
    }
  | { type: "analyze_screen" }
  | { type: "stop_agent" }
  | { type: "start_voice" }
  | { type: "start_desktop" }
  | { type: "permission_response"; task_id: string; approved: boolean }
  | { type: "user_question_response"; question_id: string; answer: string }
  | { type: "ping" };

// ── Session data returned by the REST API ──────────────────────────

export type SessionStatus =
  | "idle"
  | "creating"
  | "ready"
  | "active"
  | "ended"
  | "error"
  | "destroyed";

export type SessionCreateMode =
  | "fresh"
  | "continue_latest_workspace"
  | "reuse_history_session";

export type HistoryReuseMode = "continue" | "fresh";

export type HandoffSummary = {
  headline: string;
  preview: string;
  goal: string;
  current_status: string;
  completed_work: string[];
  open_tasks: string[];
  important_facts: string[];
  artifacts: string[];
  recommended_next_step: string;
};

export type ContextPacket = {
  version: number;
  built_at: string;
  summary: string;
  goal: string;
  open_tasks: string[];
  recent_turns: string[];
  latest_run_summary: string;
  artifact_refs: string[];
  tool_memory: string[];
  workspace_state: string;
  digest: string;
};

export type SessionData = {
  session_id: string;
  task_id?: string | null;
  stream_url: string | null;
  ws_ticket: string;
  status: SessionStatus | string;
  created_at: string | null;
  handoff_summary?: HandoffSummary | null;
  resume_source_session_id?: string | null;
  current_run_id?: string | null;
  run_status?: string | null;
  artifact_count?: number;
  can_continue_conversation?: boolean;
  exact_workspace_resume_available?: boolean;
  continuation_mode?: string | null;
};

export type SessionTokenTotals = {
  input: number;
  output: number;
  total: number;
};

export type SessionLastUsage = {
  model: string;
  source: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
};

export type SessionInfo = {
  session_id: string;
  task_id?: string | null;
  status: SessionStatus | string;
  is_live: boolean;
  stream_url: string | null;
  created_at: string | null;
  ended_at?: string | null;
  summary?: string | null;
  message_count: number;
  handoff_summary?: HandoffSummary | null;
  can_continue_workspace?: boolean;
  has_artifacts?: boolean;
  resume_state?: string | null;
  workspace_owner_session_id?: string | null;
  resume_source_session_id?: string | null;
  current_run_id?: string | null;
  run_status?: string | null;
  artifact_count?: number;
  can_continue_conversation?: boolean;
  exact_workspace_resume_available?: boolean;
  continuation_mode?: string | null;
  context_packet?: ContextPacket | null;
  token_totals?: SessionTokenTotals | null;
  model_context_limit?: number | null;
  last_usage?: SessionLastUsage | null;
};

export type RecentSession = {
  session_id: string;
  title: string;
  status: SessionStatus | string;
  summary: string | null;
  created_at: string | null;
  updated_at: string | null;
  ended_at?: string | null;
  message_count: number;
  handoff_summary?: HandoffSummary | null;
  can_continue_workspace?: boolean;
  has_artifacts?: boolean;
  resume_state?: string | null;
  workspace_owner_session_id?: string | null;
  current_run_id?: string | null;
  run_status?: string | null;
  artifact_count?: number;
  can_continue_conversation?: boolean;
  exact_workspace_resume_available?: boolean;
  continuation_mode?: string | null;
  context_packet?: { summary?: string | null } | null;
};

export type RunInfo = {
  run_id: string;
  session_id: string;
  owner_id: string;
  status: string;
  created_at: string | null;
  updated_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  last_step_at?: string | null;
  step_count: number;
  artifact_count: number;
  title: string;
  source_session_id?: string | null;
};

export type RunStep = {
  step_id: string;
  run_id: string;
  session_id: string;
  step_type: string;
  status: string;
  title: string;
  detail: string;
  created_at: string | null;
  updated_at?: string | null;
  completed_at?: string | null;
  step_index: number;
  source?: string | null;
  error?: string | null;
  external_ref?: string | null;
  metadata: Record<string, unknown>;
};

export type RunArtifact = {
  artifact_id: string;
  run_id: string;
  session_id: string;
  kind: string;
  title: string;
  preview: string;
  created_at: string | null;
  source_step_id?: string | null;
  path?: string | null;
  url?: string | null;
  metadata: Record<string, unknown>;
};

export type LibraryCategory =
  | "slides"
  | "documents"
  | "spreadsheets"
  | "images"
  | "media"
  | "others";

export type LibraryItem = {
  artifact: RunArtifact;
  session_id: string;
  session_title: string;
  category: LibraryCategory;
};

export type UploadedInputFile = {
  artifact_id?: string;
  name: string;
  path: string;
  mime_type?: string | null;
  size?: number | null;
  drive_status?: string | null;
  drive_file_id?: string | null;
  drive_web_view_link?: string | null;
  drive_folder_path?: string | null;
};

export type WorkflowTemplateInputField = {
  key: string;
  label: string;
  placeholder: string;
  required: boolean;
};

export type WorkflowTemplateData = {
  template_id: string;
  owner_id: string;
  name: string;
  description: string;
  source_session_id?: string | null;
  source_run_id?: string | null;
  instructions: string;
  input_fields: WorkflowTemplateInputField[];
  source_artifacts: string[];
  status?: "draft" | "published";
  created_at: string | null;
  updated_at: string | null;
  last_used_at?: string | null;
};

export type WorkflowTemplateRunResult = {
  session: SessionData;
  initial_prompt: string;
};

export type WorkspaceResumeState = {
  available: boolean;
  session: SessionInfo | null;
};

export type ArchivedMessage = {
  id: string;
  role: "user" | "agent" | "tool_call" | "tool_result" | "thinking" | "agent_thinking";
  text: string;
  source?: string;
  turn_index: number;
  created_at: string | null;
};

// ── Backward-compatible aliases ────────────────────────────────────

/** @deprecated Use WsMessage */
export type ServerMessage = WsMessage;

/** @deprecated Use WsCommand */
export type ClientCommand = WsCommand;

/** Individual named message types extracted from WsMessage for convenience. */
export type SandboxStatusMessage = Extract<WsMessage, { type: "sandbox_status" }>;
export type VncUrlMessage = Extract<WsMessage, { type: "vnc_url" }>;
export type TranscriptMessage = Extract<WsMessage, { type: "transcript" }>;
export type AgentThinkingMessage = Extract<WsMessage, { type: "agent_thinking" }>;
export type AgentToolCallMessage = Extract<WsMessage, { type: "agent_tool_call" }>;
export type AgentToolResultMessage = Extract<WsMessage, { type: "agent_tool_result" }>;
export type AgentScreenshotMessage = Extract<WsMessage, { type: "agent_screenshot" }>;
export type AgentCompleteMessage = Extract<WsMessage, { type: "agent_complete" }>;
export type AgentDelegationMessage = Extract<WsMessage, { type: "agent_delegation" }>;
export type UiActionMessage = Extract<WsMessage, { type: "ui_action" }>;
export type PermissionRequestMessage = Extract<WsMessage, { type: "permission_request" }>;
export type BgTaskProgressMessage = Extract<WsMessage, { type: "bg_task_progress" }>;
export type BgTaskCompleteMessage = Extract<WsMessage, { type: "bg_task_complete" }>;
export type ErrorMessage = Extract<WsMessage, { type: "error" }>;
export type QuotaUpdateMessage = Extract<WsMessage, { type: "quota_update" }>;

// ── Activity feed item ─────────────────────────────────────────────

export type ActivityItem = {
  id: string;
  timestamp: number;
  message: WsMessage;
};

// ── Session phase ──────────────────────────────────────────────────

export type SessionPhase = "idle" | "listening" | "thinking" | "acting" | "done";

// ── Unified chat item (used by the unified chat panel) ─────────────

export type ChatItem =
  | { kind: "message"; role: "user" | "agent"; text: string; ts: number }
  | { kind: "event"; event: { type: string; timestamp: number; [key: string]: unknown } }
  | { kind: "permission"; request: PermissionRequestMessage; ts: number }
  | { kind: "delegation"; from: string; to: string; ts: number }
  | { kind: "bg_progress"; task_id: string; progress: number; message: string; ts: number }
  | { kind: "bg_complete"; task_id: string; success: boolean; result: string; ts: number };
