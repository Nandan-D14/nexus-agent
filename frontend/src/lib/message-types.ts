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

export type WsMessage =
  | { type: "sandbox_status"; status: string }
  | { type: "vnc_url"; url: string }
  | { type: "transcript"; role: "user" | "agent"; text: string }
  | { type: "run_status"; run: RunInfo | null }
  | { type: "step_started"; step: RunStep }
  | { type: "step_completed"; step: RunStep }
  | { type: "step_failed"; step: RunStep }
  | { type: "artifact_created"; artifact: RunArtifact }
  | { type: "agent_thinking"; content: string }
  | { type: "agent_tool_call"; tool: string; args: Record<string, unknown> }
  | { type: "agent_tool_result"; tool: string; output: string }
  | { type: "agent_screenshot"; image_b64: string; analysis: string }
  | { type: "agent_complete"; summary: string }
  | { type: "agent_delegation"; from: string; to: string }
  | { type: "permission_request"; task_id: string; description: string; estimated_seconds: number; agent: string }
  | { type: "bg_task_progress"; task_id: string; progress: number; message: string }
  | { type: "bg_task_complete"; task_id: string; success: boolean; result: string }
  | { type: "todo_list_updated"; items: Array<{ title: string; status: "pending" | "in_progress" | "done"; note?: string }> }
  | { type: "voice_status"; status: string; message: string }
  | ({ type: "quota_update" } & PlanQuota)
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
  | { type: "ui_action"; action: "switch_tab"; target: "workflow" | "desktop"; reason?: string };

// ── Client -> Server (Text frames) ─────────────────────────────────

export type WsCommand =
  | {
      type: "text_input";
      text: string;
      connector_ids?: string[];
      uploaded_files?: UploadedInputFile[];
    }
  | { type: "analyze_screen" }
  | { type: "stop_agent" }
  | { type: "start_voice" }
  | { type: "permission_response"; task_id: string; approved: boolean }
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

export type SessionInfo = {
  session_id: string;
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
};

export type RecentSession = {
  session_id: string;
  title: string;
  status: SessionStatus | string;
  summary: string | null;
  created_at: string | null;
  updated_at: string | null;
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
  source_session_id: string;
  source_run_id?: string | null;
  instructions: string;
  input_fields: WorkflowTemplateInputField[];
  source_artifacts: string[];
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
  role: "user" | "agent";
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
