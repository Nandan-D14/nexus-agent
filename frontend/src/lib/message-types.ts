/**
 * Discriminated union types for all WebSocket messages.
 *
 * Binary frames (audio) are handled separately by the WebSocket hook.
 * These types cover only the JSON text frames.
 */

// ── Server -> Client (Text frames) ─────────────────────────────────

export type WsMessage =
  | { type: "sandbox_status"; status: string }
  | { type: "vnc_url"; url: string }
  | { type: "transcript"; role: "user" | "agent"; text: string }
  | { type: "agent_thinking"; content: string }
  | { type: "agent_tool_call"; tool: string; args: Record<string, unknown> }
  | { type: "agent_tool_result"; tool: string; output: string }
  | { type: "agent_screenshot"; image_b64: string; analysis: string }
  | { type: "agent_complete"; summary: string }
  | { type: "agent_delegation"; from: string; to: string }
  | { type: "permission_request"; task_id: string; description: string; estimated_seconds: number; agent: string }
  | { type: "bg_task_progress"; task_id: string; progress: number; message: string }
  | { type: "bg_task_complete"; task_id: string; success: boolean; result: string }
  | { type: "voice_status"; status: string; message: string }
  | { type: "error"; code: string; message: string }
  | { type: "pong" };

// ── Client -> Server (Text frames) ─────────────────────────────────

export type WsCommand =
  | { type: "text_input"; text: string }
  | { type: "analyze_screen" }
  | { type: "stop_agent" }
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

export type SessionData = {
  session_id: string;
  stream_url: string | null;
  ws_ticket: string;
  status: SessionStatus | string;
  created_at: string | null;
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
};

export type RecentSession = {
  session_id: string;
  title: string;
  status: SessionStatus | string;
  summary: string | null;
  created_at: string | null;
  updated_at: string | null;
  message_count: number;
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
export type PermissionRequestMessage = Extract<WsMessage, { type: "permission_request" }>;
export type BgTaskProgressMessage = Extract<WsMessage, { type: "bg_task_progress" }>;
export type BgTaskCompleteMessage = Extract<WsMessage, { type: "bg_task_complete" }>;
export type ErrorMessage = Extract<WsMessage, { type: "error" }>;

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
