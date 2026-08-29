/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useRouter, useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";
import {
  type ChangeEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  Check,
  ChevronDown,
  Link2,
  Paperclip,
  X,
  Plus,
  Monitor,
  Mic,
  ArrowUp,
  Square,
  Signal,
  Globe,
  User,
  Settings,
  Search,
} from "lucide-react";
import Image from "next/image";
import { motion, AnimatePresence } from "framer-motion";

import { UnifiedChatPanel } from "@/components/unified-chat-panel";
import { TodoList } from "@/components/todo-list";
import { useToast } from "@/components/toast-provider";
import { useLiveDesktop } from "@/components/live-desktop-provider";
import type { WorkflowRun } from "@/components/agent-workflow-panel";
import type { StepType, WorkflowStepData } from "@/components/workflow-step";
import { useAuth } from "@/lib/auth-context";
import { AudioPlayer } from "@/lib/audio-playback";
import type {
  ArchivedMessage,
  RunArtifact,
  RunInfo,
  RunStep,
  SessionData,
  SessionInfo,
  SessionPhase,
  UploadedInputFile,
  WsMessage,
} from "@/lib/message-types";
import { authenticatedFetch, parseApiError } from "@/lib/api-client";
import { useMicrophone } from "@/lib/use-microphone";
import { useSession } from "@/lib/use-session";
import { useSettings } from "@/lib/settings-context";
import { useLandingChrome } from "@/lib/landing-chrome-context";
import {
  classifyAgentTool,
  displayAgentToolName,
  surfaceForAgentTool,
} from "@/lib/agent-tool-classification";
import type { EditorSessionState, TerminalSessionState } from "@/lib/sandbox-session";
import type { Tab } from "@/components/workflow-desktop-container";

import {
  type ChatItem,
  type PendingSessionAction,
  type PendingTurnInput,
  type SessionConnector,
  type SessionUploadResponse,
  SYSTEM_CONNECTOR,
  providerLogo,
  toolAction,
  displayStepTitle,
  upsertRunArtifact,
  normalizePendingTurnInput,
  upsertRunStep,
  upsertArtifact,
  mapStoredMessagesToChatItems,
  foldDurableWorkingLogEvents,
  reduceWorkingLogMessage,
  permissionDecisionsFromRunSteps,
  extractTodoItemsFromHistory,
  mergeChatItemsByTimestamp,
  upsertTemplateDraftItem,
} from "@/lib/session-utils";
import { withSchedulingConnectors } from "@/lib/scheduling-intent";
import { isDeliverableArtifact } from "@/lib/artifact-url";
import { sessionPath } from "@/lib/app-paths";
import { useWebSocket, replayEventToMessage } from "@/lib/use-websocket";
import {
  SessionCanvasProvider,
  type SessionCanvasApi,
} from "@/lib/session-canvas-context";
import {
  isCanvasArtifact,
  isCanvasWorkspacePath,
  isCanvasWorkspaceWrite,
  type SessionCanvasDocument,
  type SessionCanvasOpenReason,
} from "@/lib/session-canvas";

import { SessionHeader } from "@/components/session/session-header";
import { CREATE_TEMPLATE_PROMPT } from "@/lib/workflow-template-utils";
import type { SessionContextUsageState } from "@/components/session/session-context-usage";
import { SessionLandingView } from "@/components/session/session-landing-view";
import { ChatComposer } from "@/components/session/chat-composer";

import type { AgentVisualAction } from "@/components/desktop-panel";

/* ------------------------------------------------------------------ */
/*  Page component                                                     */
/* ------------------------------------------------------------------ */

/** Connected integrations rarely change mid-session; reuse them this long. */
const CONNECTORS_TTL_MS = 60_000;

/**
 * How long the agent may go completely silent while the UI shows a busy phase
 * before we assume the turn was lost and hand control back to the user. Long
 * enough to cover a slow model call or a cold sandbox boot.
 */
const AGENT_STALL_TIMEOUT_MS = 180_000;
const AGENT_STALL_POLL_MS = 5_000;
const LIVE_WORK_TABS = new Set<Tab>(["desktop", "terminal", "editor"]);

const WorkflowDesktopContainer = dynamic(
  () =>
    import("@/components/workflow-desktop-container").then(
      (mod) => mod.WorkflowDesktopContainer,
    ),
  { ssr: false },
);

/** Run states a durable worker may still be actively progressing through. */
const EXECUTING_RUN_STATUSES = new Set(["queued", "running", "cancelling"]);

function isRunStillExecuting(runStatus: string | null | undefined): boolean {
  return typeof runStatus === "string" && EXECUTING_RUN_STATUSES.has(runStatus);
}

function appendCanvasDocumentItem(
  prev: ChatItem[],
  document: SessionCanvasDocument,
  ts: number,
): ChatItem[] {
  const exists = prev.some(
    (item) =>
      item.kind === "event" &&
      item.type === "canvas_document" &&
      (item as { document?: { id?: string } }).document?.id === document.id,
  );
  if (exists) return prev;
  return [...prev, { kind: "event", type: "canvas_document", document, ts }];
}

export function SessionWorkspace({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, isLoading: authLoading } = useAuth();
  const { ensureByokReady } = useSettings();
  const { setLandingChrome } = useLandingChrome();
  const {
    createSession,
    continueSession,
    getSession,
    getSessionMessages,
    getSessionArtifacts,
    getSessionRun,
    getSessionRunSteps,
    listDurableTaskEvents,
    refreshTicket,
    isLoading,
    error,
  } = useSession();
  const { toast, removeToast } = useToast();
  const isNewSession = sessionId === "new";
  const shouldAutoResume = searchParams.get("resume") === "1";
  const shouldAutoContinue = searchParams.get("continue") === "1";

  const [sessionInfo, setSessionInfo] = useState<SessionInfo | null>(null);
  const [sessionData, setSessionData] = useState<SessionData | null>(null);
  const [runInfo, setRunInfo] = useState<RunInfo | null>(null);
  const [runSteps, setRunSteps] = useState<RunStep[]>([]);
  const [workflowRun, setWorkflowRun] = useState<WorkflowRun | null>(null);
  const [forcedTab, setForcedTab] = useState<Tab | null>(null);
  const [workspaceTab, setWorkspaceTab] = useState<Tab>("workflow");
  const workspaceTabRef = useRef<Tab>("workflow");
  const canvasApiRef = useRef<SessionCanvasApi | null>(null);
  const [terminalSession, setTerminalSession] = useState<TerminalSessionState | null>(null);
  const [editorSession, setEditorSession] = useState<EditorSessionState | null>(null);
  const [runArtifacts, setRunArtifacts] = useState<RunArtifact[]>([]);
  const [genUiSteps, setGenUiSteps] = useState<WorkflowStepData[]>([]);
  const [viewMode, setViewMode] = useState<"live" | "archived">("live");
  const [pageError, setPageError] = useState<string | null>(null);
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [phase, setPhase] = useState<SessionPhase>("idle");
  const [chatItems, setChatItems] = useState<ChatItem[]>([]);
  const [textInput, setTextInput] = useState("");
  const [availableConnectors, setAvailableConnectors] = useState<SessionConnector[]>([SYSTEM_CONNECTOR]);
  const [selectedConnectorIds, setSelectedConnectorIds] = useState<string[]>([]);
  const [selectedToolIds, setSelectedToolIds] = useState<string[]>([]);
  const [connectorsLoading, setConnectorsLoading] = useState(false);
  const connectorsFetchedAtRef = useRef(0);
  const connectorsInFlightRef = useRef<Promise<void> | null>(null);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedInputFile[]>([]);
  const [todoItems, setTodoItems] = useState<Array<{ title: string; status: "pending" | "in_progress" | "done"; note?: string }>>([]);
  const [contextUsage, setContextUsage] = useState<SessionContextUsageState | null>(null);
  const [isUploadingFile, setIsUploadingFile] = useState(false);
  const [hasActivatedSession, setHasActivatedSession] = useState(false);
  const [isContinuingThread, setIsContinuingThread] = useState(false);
  const [isDesktopVisible, setIsDesktopVisible] = useState(false);
  const [isDesktopFullscreen, setIsDesktopFullscreen] = useState(false);
  const [pendingText, setPendingText] = useState<PendingTurnInput | null>(null);
  const [pendingMicStart, setPendingMicStart] = useState(false);
  const [pendingDesktopStart, setPendingDesktopStart] = useState(false);
  const [agentStatus, setAgentStatus] = useState("");
  const [agentAction, setAgentAction] = useState<AgentVisualAction | null>(null);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [voiceStatus, setVoiceStatus] = useState<
    "available" | "unavailable" | "connecting" | "connected" | "reconnecting" | "disconnected"
  >("disconnected");
  const audioPlayer = useRef(new AudioPlayer());
  const inputRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const landingInputRef = useRef<HTMLDivElement>(null);
  const autoResumeTriggeredRef = useRef(false);
  // The first prompt of a brand-new session is handed off through sessionStorage
  // and must outlive the session-load reset below. Keeping it in a ref (rather
  // than only in `pendingText`) means a second pass of that effect -- React
  // StrictMode double-mounts it in dev -- cannot swallow the prompt, because the
  // storage key has already been consumed by then. Cleared only once it is sent.
  const armedActionRef = useRef<{ sessionId: string; action: PendingSessionAction } | null>(null);
  // Bumped by the session-load reset so the armed action re-applies itself.
  const [sessionResetToken, setSessionResetToken] = useState(0);
  // Text of a user bubble rendered before the server echoed it back, so the
  // echo can be recognised and dropped instead of duplicating the message.
  const optimisticUserTextRef = useRef<string | null>(null);
  // Guards against a double-submit creating two threads from one click.
  const createThreadInFlightRef = useRef(false);
  // Wall clock of the last frame received from the backend. Drives the stall
  // watchdog so a lost terminal event can never strand the thinking indicator.
  const lastServerActivityRef = useRef(Date.now());
  const { registerDesktop, clearDesktop } = useLiveDesktop();
  const wsUrl =
    typeof window !== "undefined"
      ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${process.env.NEXT_PUBLIC_AGENT_WS_URL?.replace(/^wss?:\/\//, "") || "localhost:8000"}/ws/${sessionId}`
      : null;

  const shouldConnectWs =
    !isNewSession &&
    viewMode === "live" &&
    Boolean(sessionData?.ws_ticket);
  const durableTaskId =
    sessionData?.task_id && sessionData.task_id.startsWith("task_")
      ? sessionData.task_id
      : null;

  const lastToastedPageErrorRef = useRef<string | null>(null);
  const lastToastedErrorRef = useRef<string | null>(null);
  const lastToastedLoadingRef = useRef<boolean>(false);

  useEffect(() => {
    if (pageError && pageError !== lastToastedPageErrorRef.current) {
      lastToastedPageErrorRef.current = pageError;
      toast(pageError, "error");
    } else if (!pageError) {
      lastToastedPageErrorRef.current = null;
    }
  }, [pageError, toast]);

  useEffect(() => {
    if (error && error !== lastToastedErrorRef.current) {
      lastToastedErrorRef.current = error;
      toast(error, "error");
    } else if (!error) {
      lastToastedErrorRef.current = null;
    }
  }, [error, toast]);

  useEffect(() => {
    if (isLoading && !lastToastedLoadingRef.current) {
      lastToastedLoadingRef.current = true;
      toast("Loading session...", "info");
    } else if (!isLoading) {
      lastToastedLoadingRef.current = false;
    }
  }, [isLoading, toast]);

  const {
    sendBinary,
    sendJson,
    isConnected,
    onBinaryMessageRef,
    onJsonMessageRef,
    seedDurableCursor,
    connectionLost,
    reconnect,
  } = useWebSocket(shouldConnectWs ? wsUrl : null, {
    ticket: sessionData?.ws_ticket ?? null,
    durableTaskId,
  });
  useEffect(() => {
    const id = "connection-lost";
    if (viewMode === "live" && connectionLost) {
      toast(
        "Disconnected from the agent. Any running task continues on the server, but live updates have stopped.",
        "warning",
        { id, persistent: true, action: { label: "Reconnect", onClick: reconnect } }
      );
      return () => removeToast(id);
    }
    removeToast(id);
  }, [viewMode, connectionLost, toast, removeToast, reconnect]);

  const handleSpeechStart = useCallback(() => {
    audioPlayer.current.stop();
  }, []);

  const { start: startMic, stop: stopMic, isRecording } =
    useMicrophone(sendBinary, handleSpeechStart);

  const refreshConnectors = useCallback(
    async (options?: { force?: boolean }) => {
      if (authLoading || !user) {
        setAvailableConnectors([SYSTEM_CONNECTOR]);
        setConnectorsLoading(false);
        return;
      }

      const isFirstLoad = connectorsFetchedAtRef.current === 0;
      const isFresh =
        !isFirstLoad && Date.now() - connectorsFetchedAtRef.current < CONNECTORS_TTL_MS;
      if (!options?.force && isFresh) return;
      // Coalesce concurrent callers (menu open racing the mount fetch).
      if (connectorsInFlightRef.current) return connectorsInFlightRef.current;

      // Skeleton only on the very first load; later refreshes update silently
      // so reopening the menu never flashes an empty list.
      if (isFirstLoad) setConnectorsLoading(true);

      const request = (async () => {
        try {
          const response = await authenticatedFetch("/v1/integrations/connections");
          if (!response.ok) {
            throw new Error(await parseApiError(response));
          }
          const body = (await response.json()) as { connections?: SessionConnector[] };
          const usable = (body.connections ?? []).filter(
            (connection) => connection.enabled && connection.status === "connected",
          );
          const nextConnectors = [SYSTEM_CONNECTOR, ...usable];
          setAvailableConnectors(nextConnectors);
          setSelectedConnectorIds((prev) =>
            prev.filter((id) => nextConnectors.some((connector) => connector.connection_id === id)),
          );
          connectorsFetchedAtRef.current = Date.now();
        } catch (error) {
          console.warn("[session] Failed to load connectors", error);
          if (isFirstLoad) {
            setAvailableConnectors([SYSTEM_CONNECTOR]);
            setSelectedConnectorIds((prev) =>
              prev.filter((id) => id === SYSTEM_CONNECTOR.connection_id),
            );
          }
        } finally {
          if (isFirstLoad) setConnectorsLoading(false);
          connectorsInFlightRef.current = null;
        }
      })();

      connectorsInFlightRef.current = request;
      return request;
    },
    [authLoading, user],
  );

  useEffect(() => {
    void refreshConnectors();
  }, [refreshConnectors]);

  /* ---- Audio playback ---- */
  useEffect(() => {
    onBinaryMessageRef.current = (data: ArrayBuffer) => {
      audioPlayer.current.play(data);
    };
  }, [onBinaryMessageRef]);

  /* ---- Keyboard shortcut: "/" to focus input ---- */
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const active = document.activeElement as HTMLElement | null;
      if (
        e.key === "/" &&
        !["INPUT", "TEXTAREA"].includes(active?.tagName ?? "") &&
        !active?.isContentEditable
      ) {
        e.preventDefault();
        inputRef.current?.focus();
        landingInputRef.current?.focus();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(() => {
    autoResumeTriggeredRef.current = false;
    // Drop an action armed for a session we have navigated away from.
    if (armedActionRef.current && armedActionRef.current.sessionId !== sessionId) {
      armedActionRef.current = null;
    }
  }, [sessionId]);

  /* ---- WS message handler ---- */
  const handleLastMessage = useCallback((msg: WsMessage) => {
    const ts = Date.now();
    // "pong" is a keepalive the client itself triggers, so it must not count as
    // agent progress — otherwise the stall watchdog would never fire.
    if (msg.type !== "pong") {
      lastServerActivityRef.current = ts;
    }

    const applyWorkingLogChat = () => {
      setChatItems((prev) => {
        const reduced = reduceWorkingLogMessage(prev, msg, ts);
        return reduced ? reduced.chatItems : prev;
      });
      if (msg.type === "todo_list_updated" && Array.isArray(msg.items)) {
        setTodoItems(msg.items);
      }
    };

    switch (msg.type) {
      case "sandbox_status":
        setChatItems((prev) => [
          ...prev,
          { kind: "event", type: msg.type, status: msg.status, ts },
        ]);
        break;

      case "run_status":
        setRunInfo(msg.run);
        // Safety net: reset phase when the run reaches a terminal state,
        // even if agent_complete was never sent (e.g. crash, disconnect, quota).
        if (msg.run?.status === "completed" || msg.run?.status === "failed" || msg.run?.status === "cancelled") {
          setPhase("done");
          setAgentStatus("");
          setAgentAction(null);
        }
        setSessionInfo((prev) =>
          prev
            ? {
                ...prev,
                current_run_id: msg.run?.run_id ?? prev.current_run_id,
                run_status: msg.run?.status ?? prev.run_status,
                artifact_count: msg.run?.artifact_count ?? prev.artifact_count,
              }
            : prev,
        );
        break;

      case "step_started":
      case "step_completed":
      case "step_failed":
        setRunSteps((prev) => upsertRunStep(prev, msg.step));
        setRunInfo((prev) =>
          prev
            ? {
                ...prev,
                step_count: Math.max(prev.step_count, msg.step.step_index),
                status:
                  msg.type === "step_failed"
                    ? msg.step.status
                    : prev.status,
              }
            : prev,
        );
        break;

      case "generative_ui": {
        const genMsg = msg as unknown as {
          component_type?: string;
          title?: string;
          component?: unknown;
        };
        const nowIso = new Date().toISOString();
        const genStep: WorkflowStepData = {
          step_id: `genui-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          step_type: "generative_ui",
          status: "completed",
          title: genMsg.title || "Generated visual",
          created_at: nowIso,
          completed_at: nowIso,
          tool: "render_ui",
          metadata: {
            tool: "render_ui",
            component_type: genMsg.component_type || "card",
            component: genMsg.component,
            title: genMsg.title || "Generated visual",
          },
        };
        setGenUiSteps((prev) => [...prev, genStep]);
        setChatItems((prev) => [
          ...prev,
          {
            kind: "event",
            type: "generative_ui",
            component_type: genMsg.component_type || "card",
            title: genMsg.title || "Generated visual",
            component: genMsg.component,
            ts,
          },
        ]);
        setForcedTab("workflow");
        break;
      }

      case "template_draft": {
        const draft = msg as Extract<WsMessage, { type: "template_draft" }>;
        setChatItems((prev) =>
          upsertTemplateDraftItem(
            prev,
            {
              template_id: draft.template_id,
              status: draft.status,
              name: draft.name,
              description: draft.description,
              instructions: draft.instructions,
              input_fields: draft.input_fields,
              source_session_id: draft.source_session_id,
            },
            ts,
          ),
        );
        break;
      }

      case "artifact_created":
        setRunArtifacts((prev) => upsertArtifact(prev, msg.artifact));
        // SaaS-style: only deliverables (PDF/DOCX/HTML/images) get chat cards.
        // Sources (search/scrape/summaries) stay in the Artifacts panel only.
        if (isDeliverableArtifact(msg.artifact)) {
          setChatItems((prev) => [
            ...prev,
            { kind: "event", type: "artifact_created", artifact: msg.artifact, ts },
          ]);
        }
        if (isCanvasArtifact(msg.artifact)) {
          canvasApiRef.current?.openFromArtifact(msg.artifact, "agent");
        }
        setRunInfo((prev) =>
          prev
            ? { ...prev, artifact_count: prev.artifact_count + 1 }
            : prev,
        );
        setSessionInfo((prev) =>
          prev
            ? {
                ...prev,
                has_artifacts: true,
                artifact_count: (prev.artifact_count ?? 0) + 1,
              }
            : prev,
        );
        break;

      case "vnc_url":
        setStreamUrl(msg.url);
        registerDesktop({ sessionId, streamUrl: msg.url });
        break;

      case "agent_delta":
      case "agent_stream_chunk": {
        const chunk = (msg as unknown as { delta?: string; chunk?: string }).delta ?? (msg as unknown as { chunk?: string }).chunk ?? "";
        if (!chunk) break;
        setPhase("thinking");
        setChatItems((prev) => {
          const lastIdx = prev.length - 1;
          const last = prev[lastIdx];
          if (last && last.kind === "message" && last.role === "agent") {
            const updated = [...prev];
            updated[lastIdx] = { ...last, text: last.text + chunk };
            return updated;
          }
          return [...prev, { kind: "message", role: "agent", text: chunk, ts }];
        });
        break;
      }

      case "agent_stream_end":
        setPhase("done");
        setAgentStatus("");
        setAgentAction(null);
        break;

      case "transcript":
        if (
          msg.role === "user" &&
          optimisticUserTextRef.current !== null &&
          optimisticUserTextRef.current === msg.text
        ) {
          optimisticUserTextRef.current = null;
          break;
        }
        if (msg.role === "agent") {
          setChatItems((prev) => {
            const lastIdx = prev.length - 1;
            const last = prev[lastIdx];
            if (last && last.kind === "message" && last.role === "agent") {
              const updated = [...prev];
              updated[lastIdx] = { ...last, text: msg.text };
              return updated;
            }
            return [...prev, { kind: "message", role: msg.role, text: msg.text, ts }];
          });
          setPhase("done");
          setAgentAction(null);
          break;
        }
        setChatItems((prev) => [
          ...prev,
          { kind: "message", role: msg.role, text: msg.text, ts },
        ]);
        break;

      case "agent_thinking":
        setPhase("thinking");
        setAgentStatus("Thinking...");
        applyWorkingLogChat();
        break;

      case "agent_tool_call": {
        const surface = surfaceForAgentTool(msg.tool);
        const args = msg.args && typeof msg.args === "object" ? msg.args : {};
        setPhase("acting");
        setAgentStatus(`Running ${displayAgentToolName(msg.tool)}...`);
        if (surface === "desktop") {
          setAgentAction(toolAction(msg.tool, args));
          setIsDesktopVisible(true);
        } else {
          setAgentAction(null);
        }
        if (surface === "terminal") {
          setIsDesktopVisible(true);
          if (msg.tool === "run_command") {
            setTerminalSession((prev) => ({
              command: prev?.command || "",
              cwd: prev?.cwd || "~",
              stdout: prev?.stdout || "",
              stderr: prev?.stderr || "",
              exitCode: null,
              running: true,
              ts,
            }));
          }
        }
        if (surface === "editor") {
          const path = typeof args.relative_path === "string" ? args.relative_path : "";
          const content = typeof args.content === "string" ? args.content : "";
          const append = Boolean(args.append);
          if (
            msg.tool === "write_workspace_file" &&
            isCanvasWorkspacePath(path) &&
            !append
          ) {
            if (isCanvasWorkspaceWrite(path, content, false)) {
              const doc = canvasApiRef.current?.openFromWorkspaceFile(
                path,
                content,
                "agent",
              );
              if (doc) {
                setChatItems((prev) => appendCanvasDocumentItem(prev, doc, ts));
              }
            }
            applyWorkingLogChat();
            break;
          }
          setIsDesktopVisible(true);
          setEditorSession((prev) => ({
            path: path || prev?.path || "",
            action: msg.tool === "read_workspace_file" ? "read" : "write",
            content: content || prev?.content || "",
            append,
            bytesWritten: prev?.bytesWritten ?? null,
            running: true,
            ts,
          }));
        }
        if (surface === "desktop" || surface === "terminal" || surface === "editor") {
          setForcedTab(surface);
        }
        applyWorkingLogChat();
        break;
      }

      case "agent_tool_result":
        applyWorkingLogChat();
        if (msg.tool === "run_command") {
          setTerminalSession((prev) => (prev ? { ...prev, running: false } : prev));
        }
        if (msg.tool === "write_workspace_file" || msg.tool === "read_workspace_file") {
          setEditorSession((prev) => (prev ? { ...prev, running: false } : prev));
        }
        break;

      case "agent_retry":
        setAgentStatus(`Retrying${msg.model ? ` ${msg.model}` : ""}...`);
        applyWorkingLogChat();
        break;

      case "agent_model_fallback":
        setAgentStatus(`Switching to ${msg.to_model}...`);
        applyWorkingLogChat();
        break;

      case "mcp_http_request":
      case "mcp_http_response":
      case "mcp_http_error":
      case "verification_result":
        applyWorkingLogChat();
        break;

      case "agent_screenshot":
        setAgentAction({ kind: "observe", label: "Observing screen", ts });
        setForcedTab("desktop");
        applyWorkingLogChat();
        break;

      case "agent_complete":
        setPhase("done");
        setAgentStatus("");
        setAgentAction(null);
        applyWorkingLogChat();
        toast("Task completed successfully!", "success");
        break;

      case "agent_delegation":
        setActiveAgent(msg.to);
        applyWorkingLogChat();
        break;

      case "user_question":
        setPhase("idle");
        setAgentStatus("Waiting for your answer...");
        applyWorkingLogChat();
        break;

      case "user_question_resolved":
        applyWorkingLogChat();
        if (!msg.answered) {
          setAgentStatus("");
        }
        break;

      // Both the live request and its durable twin block the run until the user
      // answers, so stop showing "Thinking..." and point at the approval card.
      case "permission_request":
      case "approval_requested":
        setPhase("idle");
        setAgentStatus("Waiting for your approval...");
        setAgentAction(null);
        applyWorkingLogChat();
        break;

      case "approval_resolved":
        setAgentStatus("");
        applyWorkingLogChat();
        break;

      case "bg_task_progress":
      case "bg_task_complete":
        applyWorkingLogChat();
        break;

      case "subagent_started":
        setAgentStatus(
          msg.role ? `${msg.role} started` : "Background agent started",
        );
        applyWorkingLogChat();
        break;

      case "subagent_progress":
        setAgentStatus(
          (typeof msg.detail === "string" && msg.detail.trim())
            || (msg.role ? `${msg.role} working...` : "Background agent working..."),
        );
        applyWorkingLogChat();
        break;

      case "subagent_completed":
        setAgentStatus(
          msg.role ? `${msg.role} finished` : "Background agent finished",
        );
        applyWorkingLogChat();
        break;

      case "subagent_failed":
        setAgentStatus(
          (typeof msg.error === "string" && msg.error.trim())
            || (msg.role ? `${msg.role} failed` : "Background agent failed"),
        );
        applyWorkingLogChat();
        break;

      case "voice_status":
        if (
          msg.status === "available" ||
          msg.status === "unavailable" ||
          msg.status === "connecting" ||
          msg.status === "connected" ||
          msg.status === "reconnecting" ||
          msg.status === "disconnected"
        ) {
          setVoiceStatus(msg.status);
        }
        setChatItems((prev) => [
          ...prev,
          { kind: "event", type: msg.type, status: msg.status, message: msg.message, ts },
        ]);
        break;

      case "budget_warning":
        setAgentStatus(msg.message);
        applyWorkingLogChat();
        break;

      case "resume_recovery":
        applyWorkingLogChat();
        break;

      case "context_packet":
        setSessionInfo((prev) =>
          prev
            ? {
                ...prev,
                context_packet: msg.packet,
              }
            : prev,
        );
        applyWorkingLogChat();
        break;

      case "todo_list_updated":
        applyWorkingLogChat();
        break;

      case "error":
        const errDetail = msg.detail || msg.message || "Agent error occurred";
        setPageError(errDetail);
        setPhase("done");
        setAgentStatus("");
        setAgentAction(null);
        applyWorkingLogChat();
        break;

      case "worker_failed":
        const workerErrDetail =
          msg.error || msg.reason || "The agent run stopped unexpectedly.";
        setPageError(workerErrDetail);
        toast(workerErrDetail, "error");
        setPhase("done");
        setAgentStatus("");
        setAgentAction(null);
        break;

      case "enqueue_rejected": {
        const rejectDetail =
          msg.reason || "The request could not be queued. Please try again.";
        setPageError(rejectDetail);
        toast(rejectDetail, "error");
        setPhase("done");
        setAgentStatus("");
        setAgentAction(null);
        break;
      }

      // Terminal for a durable run: the worker released the turn. Clearing the
      // phase here keeps the composer usable even if agent_complete was lost.
      case "worker_finished":
        setPhase("done");
        setAgentStatus("");
        setAgentAction(null);
        break;

      case "run_queued":
        setAgentStatus("Queued...");
        break;

      // A prompt arrived while a run was still executing. The prompt was not
      // accepted, but the server re-attached us to that run, so show it as live
      // work rather than an error the user can only retry into. Put the typed
      // text back in the composer so it is not silently lost; it was already
      // cleared in handleTextSubmit / sendTextOrQueue before the server
      // responded.
      case "run_busy": {
        const pending = (msg as { pending_text?: string }).pending_text;
        if (typeof pending === "string" && pending.trim()) {
          setTextInput(pending);
        }
        setPhase("acting");
        setAgentStatus(msg.message || "Still working on the previous request...");
        toast(
          msg.message ||
            "Still working on the previous request — live progress is shown in the chat.",
          "info",
        );
        break;
      }

      case "worker_claimed":
        if (msg.reattached) {
          // The run kept going while this tab was away. Show it as live work so
          // the composer stays locked and the thinking indicator is honest.
          setPhase("acting");
          setAgentStatus("Reconnected — still working...");
        } else {
          setAgentStatus("Starting...");
        }
        break;

      case "agent_status":
        setAgentStatus(msg.message || msg.status);
        break;

      case "token_usage":
        setContextUsage({
          maxTokens: Math.max(1, Number(msg.max_tokens) || 1),
          usedTokens: Math.max(0, Number(msg.input_tokens) || 0),
          model: typeof msg.model === "string" ? msg.model : undefined,
          usage: {
            inputTokens: Math.max(0, Number(msg.input_tokens) || 0),
            outputTokens: Math.max(0, Number(msg.output_tokens) || 0),
            totalTokens: Math.max(0, Number(msg.total_tokens) || 0),
          },
        });
        break;

      case "quota_update":
        break;

      case "pong":
        break;

      case "ui_action":
        if (msg.action === "switch_tab") {
          setForcedTab(msg.target);
          if (
            msg.target === "canvas" ||
            msg.target === "desktop" ||
            msg.target === "terminal" ||
            msg.target === "editor"
          ) {
            setIsDesktopVisible(true);
          }
        }
        break;

      case "sandbox_terminal": {
        const command = typeof msg.command === "string" ? msg.command : "";
        const cwd = typeof msg.cwd === "string" && msg.cwd ? msg.cwd : "~";
        const stdout = typeof msg.stdout === "string" ? msg.stdout : "";
        const stderr = typeof msg.stderr === "string" ? msg.stderr : "";
        const exitCode = typeof msg.exit_code === "number" ? msg.exit_code : null;
        setIsDesktopVisible(true);
        setForcedTab("terminal");
        setTerminalSession((prev) => ({
          command: command || prev?.command || "",
          cwd,
          stdout: msg.phase === "result" ? stdout : prev?.stdout || "",
          stderr: msg.phase === "result" ? stderr : prev?.stderr || "",
          exitCode: msg.phase === "result" ? exitCode : null,
          running: msg.phase === "start",
          ts,
        }));
        break;
      }

      case "sandbox_editor": {
        const path = typeof msg.path === "string" ? msg.path : "";
        const action = msg.action === "read" || msg.action === "list" ? msg.action : "write";
        const content = typeof msg.content === "string" ? msg.content : "";
        const append = Boolean(msg.append);
        if (action === "write" && isCanvasWorkspacePath(path) && !append) {
          if (isCanvasWorkspaceWrite(path, content, false)) {
            const doc = canvasApiRef.current?.openFromWorkspaceFile(
              path,
              content,
              "agent",
            );
            if (doc) {
              setChatItems((prev) => appendCanvasDocumentItem(prev, doc, ts));
            }
          }
          break;
        }
        setIsDesktopVisible(true);
        setForcedTab("editor");
        setEditorSession((prev) => ({
          path: path || prev?.path || "",
          action,
          content: content || (msg.phase === "start" ? prev?.content || "" : prev?.content || ""),
          append,
          bytesWritten:
            typeof msg.bytes_written === "number" ? msg.bytes_written : prev?.bytesWritten ?? null,
          running: msg.phase === "start",
          ts,
        }));
        break;
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---- Wire up JSON message handler via ref (avoids React batching loss) ---- */
  useEffect(() => {
    onJsonMessageRef.current = handleLastMessage;
  }, [handleLastMessage, onJsonMessageRef]);

  /* ---- Stall watchdog ----
   * The thinking indicator is set optimistically on send and cleared by a
   * terminal event. If that event never arrives (dropped frame, backend that
   * bailed out silently, worker that died) the composer would stay locked
   * forever. After a long quiet period, unlock the UI and say so plainly.
   *
   * A durable run is exempt: it is owned by a worker, keeps writing events
   * regardless of this socket, and the server settles it if it is truly dead.
   * Unlocking here would only invite a resend that the server refuses because
   * the run is still in flight.
   */
  useEffect(() => {
    if (viewMode !== "live") {
      return;
    }
    if (phase !== "thinking" && phase !== "acting") {
      return;
    }
    if (durableTaskId && isRunStillExecuting(sessionInfo?.run_status)) {
      return;
    }

    lastServerActivityRef.current = Date.now();
    const interval = setInterval(() => {
      const idleMs = Date.now() - lastServerActivityRef.current;
      if (idleMs < AGENT_STALL_TIMEOUT_MS) {
        return;
      }
      setPhase("done");
      setAgentStatus("");
      setAgentAction(null);
      setPageError(
        "The agent stopped sending updates. Your message may not have been processed — please send it again.",
      );
    }, AGENT_STALL_POLL_MS);

    return () => clearInterval(interval);
  }, [durableTaskId, phase, sessionInfo?.run_status, viewMode]);

  useEffect(() => {
    if (isNewSession || viewMode !== "live" || !streamUrl) {
      return;
    }

    registerDesktop({ sessionId, streamUrl });
  }, [isNewSession, registerDesktop, sessionId, streamUrl, viewMode]);

  useEffect(() => {
    const player = audioPlayer.current;

    return () => {
      player.stop();
      stopMic();
    };
  }, [sessionId, stopMic]);

  useEffect(() => {
    if (isRecording && (voiceStatus === "disconnected" || voiceStatus === "reconnecting")) {
      stopMic();
    }
  }, [isRecording, stopMic, voiceStatus]);

  /* ---- Convert runInfo/runSteps to workflowRun ---- */
  useEffect(() => {
    if (!runInfo) {
      setWorkflowRun(genUiSteps.length ? {
        run_id: "genui",
        title: "Agent Workflow",
        status: "running",
        steps: [...genUiSteps],
      } : null);
      return;
    }

    const runStatusMap: Record<string, "pending" | "running" | "completed" | "failed"> = {
      "pending": "pending",
      "running": "running",
      "completed": "completed",
      "failed": "failed",
      "cancelled": "failed",
      "success": "completed",
      "error": "failed",
    };
    const stepStatusMap: Record<string, "pending" | "in_progress" | "completed" | "failed"> = {
      "pending": "pending",
      "running": "in_progress",
      "in_progress": "in_progress",
      "completed": "completed",
      "failed": "failed",
      "cancelled": "failed",
      "success": "completed",
      "error": "failed",
    };

    const toWorkflowStepType = (stepType: string, tool?: string): StepType => {
      const provider = classifyAgentTool(tool);
      if (provider === "gmail") return "gmail";
      if (provider === "calendar") return "calendar";
      if (provider === "tasks") return "tasks";
      if (provider === "mcp") return "mcp";
      if (tool === "run_command") return "terminal";
      if (tool === "publish_html_artifact") return "html_artifact";
      if (tool === "render_ui") return "generative_ui";
      if (tool === "web_search" || tool === "scrape_web_page" || tool === "open_browser") return "browser";
      if (
        tool === "write_workspace_file" ||
        tool === "read_workspace_file" ||
        tool === "list_workspace_files"
      ) return "file_created";
      if (tool === "take_screenshot") return "screenshot";

      if (
        stepType === "thinking" ||
        stepType === "tool_call" ||
        stepType === "tool_result" ||
        stepType === "screenshot" ||
        stepType === "file_created" ||
        stepType === "browser" ||
        stepType === "error" ||
        stepType === "terminal" ||
        stepType === "observation" ||
        stepType === "completion" ||
        stepType === "generative_ui" ||
        stepType === "html_artifact"
      ) {
        return stepType;
      }
      return "observation";
    };

    const mappedSteps: WorkflowStepData[] = runSteps.map((step) => {
        const metadata = step.metadata ?? {};
        const args = metadata.args;
        const result = metadata.result;
        const tool = typeof metadata.tool === "string"
          ? metadata.tool
          : result && typeof result === "object" && !Array.isArray(result) && typeof (result as Record<string, unknown>).tool === "string"
            ? String((result as Record<string, unknown>).tool)
            : undefined;

        return {
          step_id: step.step_id,
          step_type: toWorkflowStepType(step.step_type, tool),
          status: stepStatusMap[step.status] || "pending",
          title: displayStepTitle(step.title, tool, step.step_type),
          detail: step.detail || "",
          created_at: step.created_at ?? new Date().toISOString(),
          command: typeof metadata.command === "string" ? metadata.command : undefined,
          args: args && typeof args === "object" && !Array.isArray(args) ? args as Record<string, unknown> : undefined,
          output: typeof metadata.output === "string" ? metadata.output : step.detail || undefined,
          error: step.error ?? undefined,
          image_b64: typeof metadata.image_b64 === "string" ? metadata.image_b64 : undefined,
          metadata: metadata && typeof metadata === "object" && !Array.isArray(metadata) ? metadata : undefined,
          tool,
        };
      });

    const combinedSteps = [...mappedSteps, ...genUiSteps].sort(
      (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    );

    setWorkflowRun({
      run_id: runInfo.run_id,
      title: runInfo.title || "Agent Workflow",
      status: runStatusMap[runInfo.status] || "running",
      steps: combinedSteps,
    });
  }, [runInfo, runSteps, genUiSteps]);

  /* ---- Session lifecycle ---- */
  useEffect(() => {
    let cancelled = false;

    async function loadSessionState() {
      if (authLoading) return;
      if (!user) {
        router.push("/");
        return;
      }

      setPageError(null);
      setPhase("idle");
      setChatItems([]);
      setTodoItems([]);
      setContextUsage(null);
      setRunInfo(null);
      setRunSteps([]);
      setRunArtifacts([]);
      setStreamUrl(null);
      setSessionData(null);
      setSessionInfo(null);
      setVoiceStatus("connected");
      setHasActivatedSession(false);
      setIsDesktopVisible(false);
      setPendingText(null);
      setPendingDesktopStart(false);
      setPendingMicStart(false);
      setViewMode("live");
      // The resets above also clear an auto-action that was already applied for
      // this session. Bump the token so it re-arms itself instead of being lost.
      setSessionResetToken((token) => token + 1);

      if (isNewSession) {
        return;
      }

      const info = await getSession(sessionId);
      if (cancelled) return;
      if (!info) {
        clearDesktop(sessionId);
        setPageError("Session not found");
        return;
      }

      setSessionInfo(info);
      if (info.last_usage && (info.model_context_limit || info.last_usage.input_tokens > 0)) {
        setContextUsage({
          maxTokens: Math.max(1, Number(info.model_context_limit) || 262144),
          usedTokens: Math.max(0, Number(info.last_usage.input_tokens) || 0),
          model: info.last_usage.model || undefined,
          usage: {
            inputTokens: Math.max(0, Number(info.last_usage.input_tokens) || 0),
            outputTokens: Math.max(0, Number(info.last_usage.output_tokens) || 0),
            totalTokens: Math.max(0, Number(info.last_usage.total_tokens) || 0),
          },
        });
      } else {
        setContextUsage(null);
      }
      const durableTaskIdFromSession =
        typeof info.task_id === "string" && info.task_id.startsWith("task_")
          ? info.task_id
          : null;

      const [messages, run, steps, artifacts, durablePage] = await Promise.all([
        getSessionMessages(sessionId),
        getSessionRun(sessionId),
        getSessionRunSteps(sessionId),
        getSessionArtifacts(sessionId),
        durableTaskIdFromSession
          ? listDurableTaskEvents(durableTaskIdFromSession)
          : Promise.resolve(null),
      ]);
      if (cancelled) return;

      const durableHydrateSucceeded = durablePage !== null;
      const historyMode = durableHydrateSucceeded ? "transcript" : "full";
      const historyChatItems = mapStoredMessagesToChatItems(messages, {
        mode: historyMode,
      }).filter((item) => {
        if (item.kind === "event" && item.type === "artifact_created") {
          const art = (item as { artifact?: RunArtifact }).artifact;
          return art ? isDeliverableArtifact(art) : false;
        }
        return true;
      });

      let durableChatItems: ChatItem[] = [];
      let hydratedTodos: Array<{
        title: string;
        status: "pending" | "in_progress" | "done";
        note?: string;
      }> = [];
      let durableLastSeq = 0;

      if (durablePage) {
        const folded = foldDurableWorkingLogEvents(
          durablePage.events
            .map((event) => {
              const message = replayEventToMessage(event);
              if (!message) {
                return null;
              }
              const ts = event.created_at
                ? new Date(event.created_at).getTime()
                : Date.now();
              return { message, ts };
            })
            .filter(
              (entry): entry is { message: NonNullable<ReturnType<typeof replayEventToMessage>>; ts: number } =>
                entry !== null,
            ),
          {
            permissionDecisions: permissionDecisionsFromRunSteps(steps),
          },
        );
        durableChatItems = folded.chatItems;
        hydratedTodos = folded.todoItems;
        durableLastSeq = durablePage.last_seq;
        seedDurableCursor(durableLastSeq);
      } else {
        hydratedTodos = extractTodoItemsFromHistory(messages);
      }

      const nextChatItems = mergeChatItemsByTimestamp(
        historyChatItems,
        durableChatItems,
      );
      const existingArtifactIds = new Set(
        nextChatItems
          .filter((item) => item.kind === "event" && item.type === "artifact_created")
          .map((item) => {
            const art = (item as { artifact?: { artifact_id?: string } }).artifact;
            return art?.artifact_id;
          })
          .filter(Boolean),
      );
      const artifactChatItems = artifacts
        .filter((a) => isDeliverableArtifact(a) && !existingArtifactIds.has(a.artifact_id))
        .map((a, index) => ({
          kind: "event" as const,
          type: "artifact_created",
          artifact: a,
          // Stagger slightly after messages so cards sort at end of the last turn
          ts: Date.now() - (artifacts.length - index) * 10,
        }));
      setChatItems((prev) => {
        if (nextChatItems.length > 0 || artifactChatItems.length > 0) {
          return [...nextChatItems, ...artifactChatItems];
        }
        return prev.length > 0 ? prev : [];
      });
      setTodoItems(hydratedTodos);
      setRunInfo(run);
      setRunSteps(steps);
      setRunArtifacts(artifacts);

      if (!info.is_live) {
        clearDesktop(sessionId);
        if (!cancelled) {
          setViewMode("archived");
          setPhase("done");
        }
        return;
      }

      const wsTicket = await refreshTicket(sessionId);
      if (cancelled) {
        return;
      }

      if (!wsTicket) {
        clearDesktop(sessionId);
        if (!cancelled) {
          setViewMode("archived");
          setPhase("done");
        }
        return;
      }

      if (!cancelled) {
        setViewMode("live");
        setSessionData({
          session_id: info.session_id,
          task_id: durableTaskIdFromSession ?? info.task_id ?? null,
          stream_url: info.stream_url,
          ws_ticket: wsTicket,
          status: info.status,
          created_at: info.created_at,
          current_run_id: info.current_run_id,
          run_status: info.run_status,
          artifact_count: info.artifact_count,
        });
        // Re-seed after sessionData.task_id lands so the durableTaskId effect
        // cannot wipe the cursor back to 0.
        if (durableHydrateSucceeded) {
          seedDurableCursor(durableLastSeq);
        }
        setStreamUrl(info.stream_url);

        // If the session is already active with a stream URL,
        // auto-activate so the desktop renders immediately on reconnect
        if (info.stream_url && (info.status === "active" || info.status === "ready")) {
          setHasActivatedSession(true);
          setIsDesktopVisible(true);
        }

        // A run still executing on a worker (we just refreshed away from it) can
        // only be re-attached over the socket, and the socket is gated on
        // activation. Sandbox-free turns have no stream_url, so activate on the
        // run state too and show the work as live.
        if (isRunStillExecuting(info.run_status)) {
          setHasActivatedSession(true);
          setPhase("acting");
          setAgentStatus("Reconnecting to the running task...");
        }
      }
    }

    void loadSessionState();

    return () => {
      cancelled = true;
    };
  }, [
    authLoading,
    clearDesktop,
    getSessionMessages,
    getSessionArtifacts,
    getSessionRun,
    getSessionRunSteps,
    getSession,
    isNewSession,
    listDurableTaskEvents,
    refreshTicket,
    router,
    seedDurableCursor,
    sessionId,
    user,
  ]);

  useEffect(() => {
    if (!isConnected || viewMode !== "live") {
      return;
    }

    if (pendingText) {
      sendJson({
        type: "text_input",
        text: pendingText.text,
        connector_ids: pendingText.connectorIds,
        tool_ids: pendingText.toolIds,
        uploaded_files: pendingText.uploadedFiles,
      });
      setPendingText(null);
      // Delivered: stop re-arming it on the next session-state reset.
      armedActionRef.current = null;
    }

    if (pendingMicStart && voiceStatus === "connected") {
      startMic();
      setPendingMicStart(false);
      setPhase("listening");
      armedActionRef.current = null;
    }

    if (pendingDesktopStart) {
      sendJson({ type: "start_desktop" });
      setPendingDesktopStart(false);
      armedActionRef.current = null;
    }
  }, [isConnected, pendingDesktopStart, pendingMicStart, pendingText, sendJson, startMic, viewMode, voiceStatus]);

  useEffect(() => {
    if (!sessionData?.session_id || viewMode !== "live" || isNewSession) {
      return;
    }

    const interval = setInterval(async () => {
      const wsTicket = await refreshTicket(sessionData.session_id);
      if (!wsTicket) {
        return;
      }
      setSessionData((prev) => {
        if (!prev || prev.ws_ticket === wsTicket) {
          return prev;
        }
        return { ...prev, ws_ticket: wsTicket };
      });
    }, 8 * 60 * 1000);

    return () => clearInterval(interval);
  }, [isNewSession, refreshTicket, sessionData?.session_id, viewMode]);

  const loadRunState = useCallback(async (targetSessionId: string) => {
    const [run, steps, artifacts] = await Promise.all([
      getSessionRun(targetSessionId),
      getSessionRunSteps(targetSessionId),
      getSessionArtifacts(targetSessionId),
    ]);
    setRunInfo(run);
    setRunSteps(steps);
    setRunArtifacts(artifacts);
  }, [getSessionArtifacts, getSessionRun, getSessionRunSteps]);

  const continueCurrentThread = useCallback(
    async (options?: {
      prompt?: PendingTurnInput;
      demo?: PendingTurnInput;
      openDesktop?: boolean;
      startMic?: boolean;
    }) => {
      if (isNewSession || viewMode === "live" || isContinuingThread) {
        return true;
      }
      if (authLoading) return false;
      if (!user) {
        router.push("/");
        return false;
      }

      setIsContinuingThread(true);
      setPageError(null);
      try {
        const session = await continueSession(sessionId);
        if (!session) {
          return false;
        }

        setSessionData(session);
        setSessionInfo((prev) =>
          prev
            ? {
                ...prev,
                status: session.status,
                current_run_id: session.current_run_id ?? prev.current_run_id,
                run_status: session.run_status ?? prev.run_status,
                artifact_count: session.artifact_count ?? prev.artifact_count,
                can_continue_conversation:
                  session.can_continue_conversation ?? prev.can_continue_conversation,
                exact_workspace_resume_available:
                  session.exact_workspace_resume_available ?? prev.exact_workspace_resume_available,
                continuation_mode:
                  session.continuation_mode ?? prev.continuation_mode,
              }
            : prev,
        );
        setViewMode("live");
        setIsDesktopFullscreen(false);
        setHasActivatedSession(true);
        if (options?.openDesktop || shouldAutoResume) {
          setIsDesktopVisible(true);
          setPendingDesktopStart(true);
        } else {
          setIsDesktopVisible(false);
        }
        await loadRunState(sessionId);

        if (options?.prompt) {
          setPendingText(options.prompt);
          setPhase("thinking");
        } else if (options?.demo) {
          setPendingText(options.demo);
          setPhase("thinking");
        } else if (options?.startMic) {
          setPendingMicStart(true);
          setPhase("listening");
        }
        return true;
      } finally {
        setIsContinuingThread(false);
      }
    },
    [
      authLoading,
      continueSession,
      isContinuingThread,
      isNewSession,
      loadRunState,
      router,
      sessionId,
      shouldAutoResume,
      user,
      viewMode,
    ],
  );

  const createThreadFromAction = useCallback(
    async (action: PendingSessionAction): Promise<boolean> => {
      // Only a concurrent create is a reason to bail. Gating on the shared
      // `isLoading` flag used to drop the very first prompt of a new session
      // whenever any unrelated request happened to be in flight.
      if (createThreadInFlightRef.current) {
        return false;
      }

      if (action.type === "prompt" || action.type === "demo") {
        const payload = normalizePendingTurnInput(action.payload);
        if (!payload) {
          return false;
        }
        action = { ...action, payload };
      }

      createThreadInFlightRef.current = true;
      setPageError(null);
      let session: SessionData | null = null;
      try {
        session = await createSession({ mode: "fresh" });
      } finally {
        createThreadInFlightRef.current = false;
      }
      if (!session) {
        setPageError("Failed to create a new thread. Your message was not sent.");
        return false;
      }

      // Hand the action to the created session. If storage is unavailable the
      // prompt would silently vanish after the redirect, so keep the user on the
      // page with their text intact instead.
      try {
        sessionStorage.setItem(
          `nexus.pendingSessionAction:${session.session_id}`,
          JSON.stringify(action),
        );
      } catch {
        setPageError(
          "This browser blocked session storage, so the thread could not be started. Please retry.",
        );
        return false;
      }

      router.replace(sessionPath(session.session_id));
      return true;
    },
    [createSession, router],
  );

  const createThreadFromPrompt = useCallback(
    async (payload: PendingTurnInput): Promise<boolean> => {
      const nextPayload = normalizePendingTurnInput(payload);
      if (!nextPayload) {
        return false;
      }

      return createThreadFromAction({ type: "prompt", payload: nextPayload });
    },
    [createThreadFromAction],
  );

  const sendTextOrQueue = useCallback(
    (payload: PendingTurnInput) => {
      const nextPayload = normalizePendingTurnInput(payload);
      if (!nextPayload) {
        return;
      }
      if (isNewSession) {
        return;
      }
      if (viewMode === "archived") {
        void continueCurrentThread({ prompt: nextPayload });
        return;
      }

      setPhase("thinking");

      if (!hasActivatedSession) {
        setHasActivatedSession(true);
        setPendingText(nextPayload);
        return;
      }

      if (!isConnected) {
        setPendingText(nextPayload);
        return;
      }

      sendJson({
        type: "text_input",
        text: nextPayload.text,
        connector_ids: nextPayload.connectorIds,
        tool_ids: nextPayload.toolIds,
        uploaded_files: nextPayload.uploadedFiles,
      });
    },
    [continueCurrentThread, hasActivatedSession, isConnected, isNewSession, sendJson, viewMode],
  );

  /* ---- Actions ---- */
  const toggleMic = useCallback(async () => {
    const byok = await ensureByokReady();
    if (!byok.ok) {
      toast(byok.message, "info");
      return;
    }

    if (isNewSession) {
      void createThreadFromAction({ type: "startMic" });
      return;
    }
    if (viewMode === "archived") {
      void continueCurrentThread({ startMic: true });
      return;
    }
    // Voice unavailable — no credentials on backend
    if (voiceStatus === "unavailable") return;
    // Voice connecting — wait
    if (voiceStatus === "connecting" || voiceStatus === "reconnecting") return;

    // Voice available but not yet connected — trigger connection first
    if (voiceStatus === "available" || voiceStatus === "disconnected") {
      sendJson({ type: "start_voice" });
      setPendingMicStart(true);
      setPhase("listening");
      return;
    }

    // Voice is connected
    if (isRecording) {
      stopMic();
      setPhase("thinking");
    } else {
      if (!hasActivatedSession) {
        setHasActivatedSession(true);
        setPendingMicStart(true);
        setPhase("listening");
        return;
      }

      if (!isConnected) {
        setPendingMicStart(true);
        setPhase("listening");
        return;
      }

      startMic();
      setPhase("listening");
    }
  }, [
    createThreadFromAction,
    continueCurrentThread,
    ensureByokReady,
    hasActivatedSession,
    isConnected,
    isNewSession,
    isRecording,
    sendJson,
    startMic,
    stopMic,
    toast,
    viewMode,
    voiceStatus,
  ]);

  const toggleConnectorSelection = useCallback((connectionId: string) => {
    setSelectedConnectorIds((prev) =>
      prev.includes(connectionId)
        ? prev.filter((id) => id !== connectionId)
        : [...prev, connectionId],
    );
  }, []);

  const toggleToolSelection = useCallback((toolId: string) => {
    setSelectedToolIds((prev) =>
      prev.includes(toolId)
        ? prev.filter((id) => id !== toolId)
        : [...prev, toolId],
    );
  }, []);

  const toggleAllConnectors = useCallback((ids: string[]) => {
    setSelectedConnectorIds((prev) => {
      if (ids.every((id) => prev.includes(id))) {
        return prev.filter((id) => !ids.includes(id));
      }
      return Array.from(new Set([...prev, ...ids]));
    });
  }, []);

  const toggleAllTools = useCallback((ids: string[]) => {
    setSelectedToolIds((prev) => {
      if (ids.every((id) => prev.includes(id))) {
        return prev.filter((id) => !ids.includes(id));
      }
      return Array.from(new Set([...prev, ...ids]));
    });
  }, []);

  const handleOpenFilePicker = useCallback((kind: "image" | "file" = "file") => {
    if (isNewSession || viewMode !== "live" || !sessionData?.session_id) {
      toast("File upload is available in a live session.", "error");
      return;
    }
    const input = fileInputRef.current;
    if (!input) return;
    input.accept = kind === "image" ? "image/*" : "";
    input.value = "";
    input.click();
  }, [isNewSession, sessionData?.session_id, toast, viewMode]);

  const handleFileUpload = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(event.target.files ?? []);
      event.target.value = "";
      if (files.length === 0) {
        return;
      }
      if (isNewSession || viewMode !== "live" || !sessionData?.session_id) {
        toast("Create or resume a live session before uploading files.", "error");
        return;
      }

      setIsUploadingFile(true);
      try {
        for (const file of files) {
          const formData = new FormData();
          formData.append("file", file);
          formData.append("relative_path", `sources/uploads/${file.name}`);
          formData.append("mirror_to_drive", "true");
          const response = await authenticatedFetch(
            `/api/v1/sessions/${encodeURIComponent(sessionData.session_id)}/files/upload`,
            {
              method: "POST",
              body: formData,
            },
          );
          if (!response.ok) {
            throw new Error(await parseApiError(response));
          }
          const body = (await response.json()) as SessionUploadResponse;
          setRunArtifacts((prev) => upsertRunArtifact(prev, body.artifact));
          setUploadedFiles((prev) => [
            ...prev,
            {
              artifact_id: body.artifact.artifact_id,
              name: body.artifact.title || file.name,
              path: body.path,
              mime_type: (body.artifact.metadata?.content_type as string | undefined) ?? file.type ?? null,
              size: (body.artifact.metadata?.size as number | undefined) ?? file.size,
              drive_status: body.drive_status ?? null,
              drive_file_id: body.drive_file_id ?? null,
              drive_web_view_link: body.drive_web_view_link ?? null,
              drive_folder_path: body.drive_folder_path ?? null,
            },
          ]);
        }
      } catch (error) {
        toast(error instanceof Error ? error.message : "File upload failed.", "error");
      } finally {
        setIsUploadingFile(false);
      }
    },
    [isNewSession, sessionData?.session_id, toast, viewMode],
  );

  const handleRemoveUploadedFile = useCallback((path: string) => {
    setUploadedFiles((prev) => prev.filter((file) => file.path !== path));
  }, []);

  const handleTextSubmit = useCallback(async () => {
    const text = textInput.trim();
    if (!text) return;

    const byok = await ensureByokReady();
    if (!byok.ok) {
      toast(byok.message, "info");
      return;
    }

    const payload: PendingTurnInput = {
      text,
      connectorIds: withSchedulingConnectors(
        text,
        selectedConnectorIds,
        selectedToolIds,
        availableConnectors,
      ),
      toolIds: selectedToolIds,
      uploadedFiles,
    };
    if (isNewSession) {
      // Clear optimistically so the composer feels responsive, but put the text
      // back if the thread could not be started -- losing the prompt with no
      // feedback is worse than a brief flicker.
      setTextInput("");
      void createThreadFromPrompt(payload).then((started) => {
        if (!started) {
          setTextInput(payload.text);
        }
      });
      return;
    }
    sendTextOrQueue(payload);
    setTextInput("");
    setUploadedFiles([]);
  }, [availableConnectors, createThreadFromPrompt, ensureByokReady, isNewSession, selectedConnectorIds, selectedToolIds, sendTextOrQueue, textInput, toast, uploadedFiles]);

  useEffect(() => {
    workspaceTabRef.current = workspaceTab;
  }, [workspaceTab]);

  const requestCanvasPane = useCallback((reason: SessionCanvasOpenReason) => {
    setIsDesktopVisible(true);
    if (reason === "user" || !LIVE_WORK_TABS.has(workspaceTabRef.current)) {
      setForcedTab("canvas");
    }
  }, []);

  const handleShowDesktop = useCallback(() => {
    if (isNewSession) {
      void createThreadFromAction({ type: "openDesktop" });
      return;
    }
    if (viewMode === "archived") {
      void continueCurrentThread({ openDesktop: true });
      return;
    }
    setIsDesktopVisible(true);
    if (!hasActivatedSession) {
      setHasActivatedSession(true);
      setPendingDesktopStart(true);
      return;
    }
    if (isConnected && !streamUrl) {
      sendJson({ type: "start_desktop" });
    } else if (!streamUrl) {
      setPendingDesktopStart(true);
    }
  }, [createThreadFromAction, continueCurrentThread, hasActivatedSession, isConnected, isNewSession, sendJson, streamUrl, viewMode]);

  const handleHideDesktop = useCallback(() => {
    setIsDesktopVisible(false);
    setIsDesktopFullscreen(false);
  }, []);

  const handleToggleDesktopFullscreen = useCallback(() => {
    if (viewMode !== "live") return;

    if (!isDesktopVisible) {
      handleShowDesktop();
      setIsDesktopFullscreen(false);
      return;
    }

    setIsDesktopFullscreen((prev) => !prev);
  }, [handleShowDesktop, isDesktopVisible, viewMode]);

  const handleDemo = useCallback(
    async (text: string) => {
      const byok = await ensureByokReady();
      if (!byok.ok) {
        toast(byok.message, "info");
        return;
      }
      const payload: PendingTurnInput = {
        text,
        connectorIds: withSchedulingConnectors(text, selectedConnectorIds, selectedToolIds, availableConnectors),
        toolIds: selectedToolIds,
      };
      if (isNewSession) {
        void createThreadFromAction({ type: "demo", payload });
        return;
      }
      if (viewMode === "archived") {
        void continueCurrentThread({ demo: payload });
        return;
      }
      sendTextOrQueue(payload);
    },
    [availableConnectors, continueCurrentThread, createThreadFromAction, ensureByokReady, isNewSession, selectedConnectorIds, selectedToolIds, sendTextOrQueue, toast, viewMode],
  );

  const handlePermissionRespond = useCallback(
    (
      taskId: string,
      approved: boolean,
      approvalId?: string,
      durableTaskId?: string,
    ) => {
      setChatItems((prev) =>
        prev.map((item) =>
          item.kind === "permission" && item.task_id === taskId
            ? {
                ...item,
                resolved: true,
                decision: approved ? "approved" : "denied",
              }
            : item,
        ),
      );
      if (approvalId && durableTaskId) {
        void authenticatedFetch(
          `/api/v1/tasks/${encodeURIComponent(durableTaskId)}/approvals/${encodeURIComponent(approvalId)}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ approved }),
          },
        ).catch((error) => {
          toast(
            error instanceof Error ? error.message : "Could not submit approval.",
            "error",
          );
        });
        return;
      }
      sendJson({ type: "permission_response", task_id: taskId, approved });
    },
    [sendJson, toast],
  );

  const handleQuestionRespond = useCallback(
    (questionId: string, answer: string) => {
      setChatItems((prev) =>
        prev.map((item) =>
          item.kind === "user_question" && item.question_id === questionId
            ? { ...item, answered: true, timedOut: false }
            : item,
        ),
      );
      setAgentStatus("");
      setPhase("acting");
      sendJson({ type: "user_question_response", question_id: questionId, answer });
    },
    [sendJson],
  );

  const handleStopAgent = useCallback(() => {
    sendJson({ type: "stop_agent" });
    // Do NOT claim the run is done here: a durable run lives on a worker and only
    // its terminal event (worker_finished / run_status) proves it stopped.
    // Flipping to "done" locally used to hide a run that was still executing,
    // which then refused the next prompt with no visible reason.
    setAgentStatus("Stopping...");
  }, [sendJson]);

  useEffect(() => {
    if (isNewSession || !sessionId) {
      return;
    }

    // Adopt a freshly handed-off action into the ref. The storage key is consumed
    // immediately so a later reload cannot resubmit the same prompt, but the ref
    // keeps it alive across session-state resets until it is actually sent.
    if (armedActionRef.current?.sessionId !== sessionId) {
      try {
        const key = `nexus.pendingSessionAction:${sessionId}`;
        const raw = sessionStorage.getItem(key);
        if (!raw) {
          return;
        }
        sessionStorage.removeItem(key);
        const stored = JSON.parse(raw) as
          | PendingSessionAction
          | { type: "demo" | "prompt"; text?: string };
        const action: PendingSessionAction | null =
          stored.type === "openDesktop" || stored.type === "startMic"
            ? { type: stored.type }
            : (() => {
                const payload = normalizePendingTurnInput(
                  "payload" in stored ? stored.payload : { text: stored.text ?? "" },
                );
                return payload ? { type: stored.type, payload } : null;
              })();
        if (!action) {
          return;
        }
        armedActionRef.current = { sessionId, action };
      } catch {
        // Ignore invalid storage payloads.
        return;
      }
    }

    const armed = armedActionRef.current;
    if (!armed || armed.sessionId !== sessionId) {
      return;
    }

    // Re-applied after every reset, so each branch must be idempotent.
    setHasActivatedSession(true);
    if (armed.action.type === "openDesktop") {
      setIsDesktopVisible(true);
      setPendingDesktopStart(true);
    } else if (armed.action.type === "startMic") {
      setPendingMicStart(true);
      setPhase("listening");
    } else {
      const payload = armed.action.payload;
      setPendingText(payload);
      setPhase("thinking");
      // Show the user's message right away so the thread is never blank while
      // the socket dials. Never append twice on a re-apply.
      optimisticUserTextRef.current = payload.text;
      setChatItems((prev) =>
        prev.length > 0
          ? prev
          : [{ kind: "message", role: "user", text: payload.text, ts: Date.now() }],
      );
    }
  }, [isNewSession, sessionId, sessionResetToken]);

  useEffect(() => {
    if (
      isNewSession ||
      (!shouldAutoResume && !shouldAutoContinue) ||
      viewMode !== "archived" ||
      autoResumeTriggeredRef.current
    ) {
      return;
    }
    autoResumeTriggeredRef.current = true;
    void continueCurrentThread(shouldAutoResume ? { openDesktop: true } : undefined);
  }, [continueCurrentThread, isNewSession, shouldAutoContinue, shouldAutoResume, viewMode]);

  const handleOpenSaveTemplate = useCallback(() => {
    if (isNewSession) {
      return;
    }
    sendTextOrQueue({ text: CREATE_TEMPLATE_PROMPT });
  }, [isNewSession, sendTextOrQueue]);

  const handleTemplateDraftChange = useCallback(
    (patch: {
      template_id: string;
      status?: "draft" | "published";
      name?: string;
      description?: string;
      instructions?: string;
      input_fields?: Array<{
        key: string;
        label: string;
        placeholder: string;
        required: boolean;
      }>;
      dismissed?: boolean;
    }) => {
      setChatItems((prev) => upsertTemplateDraftItem(prev, patch, Date.now()));
    },
    [],
  );

  useEffect(() => {
    if (!agentAction) return;
    const timeout = window.setTimeout(() => setAgentAction(null), 2200);
    return () => window.clearTimeout(timeout);
  }, [agentAction]);

  /* ---- Render ---- */
  const latestAnalysis = useMemo(() => {
    // Hide vision overlay when the agent is not actively working
    if (phase === "done" || phase === "idle") {
      return null;
    }

    for (let i = chatItems.length - 1; i >= 0; i--) {
      const item = chatItems[i];
      // If we see a completion event before finding a screenshot, the task is done
      if (item.kind === "event" && item.type === "agent_complete") {
        return null;
      }
      if (item.kind === "event" && item.type === "agent_screenshot" && typeof item.analysis === "string") {
        return item.analysis;
      }
    }
    return null;
  }, [chatItems, phase]);

  const hasConversationStarted =
    chatItems.length > 0 ||
    phase !== "idle" ||
    pendingText !== null ||
    pendingMicStart ||
    viewMode === "archived";
  const hasStarted = hasConversationStarted || isDesktopVisible;
  const uploadDisabled = isNewSession || viewMode !== "live" || isUploadingFile;
  const canShowComposer = !isNewSession;

  useEffect(() => {
    setLandingChrome(!hasStarted);
    return () => setLandingChrome(false);
  }, [hasStarted, setLandingChrome]);

  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={handleFileUpload}
      />

      {/* ─── Main panel ─── */}
      <div className="flex-1 flex flex-col min-h-0 relative h-full overflow-hidden">
        {!hasStarted ? (
          <SessionLandingView
            onShowDesktop={handleShowDesktop}
            textInput={textInput}
            onChangeText={setTextInput}
            onSubmitText={handleTextSubmit}
            onOpenFilePicker={handleOpenFilePicker}
            uploadDisabled={uploadDisabled}
            uploadedFiles={uploadedFiles}
            onRemoveFile={handleRemoveUploadedFile}
            onToggleMic={toggleMic}
            isRecording={isRecording}
            voiceStatus={voiceStatus}
            phase={phase}
            isLoading={isLoading}
            isUploadingFile={isUploadingFile}
            onStopAgent={handleStopAgent}
            availableConnectors={availableConnectors}
            selectedConnectorIds={selectedConnectorIds}
            onToggleConnector={toggleConnectorSelection}
            onToggleAllConnectors={toggleAllConnectors}
            selectedToolIds={selectedToolIds}
            onToggleTool={toggleToolSelection}
            onToggleAllTools={toggleAllTools}
            connectorsLoading={connectorsLoading}
            onRefreshTools={refreshConnectors}
            pageError={pageError}
            error={error}
            landingInputRef={landingInputRef}
          />
        ) : (
          <SessionCanvasProvider
            todoItems={todoItems}
            onRequestPane={requestCanvasPane}
            apiRef={canvasApiRef}
          >
            {/* ─── Header ─── */}
            <SessionHeader
              viewMode={viewMode}
              isConnected={isConnected}
              isNewSession={isNewSession}
              isDesktopVisible={isDesktopVisible}
              isDesktopFullscreen={isDesktopFullscreen}
              contextUsage={contextUsage}
              onToggleDesktopFullscreen={handleToggleDesktopFullscreen}
              onShowDesktop={handleShowDesktop}
              onHideDesktop={handleHideDesktop}
              onOpenSaveTemplate={handleOpenSaveTemplate}
            />

            {/* ─── Main content: Desktop + Chat ─── */}
            <div className="flex-1 flex overflow-hidden min-h-0">
              {/* Left/Middle: Chat Sidebar */}
              <div
                className={`overflow-hidden flex flex-col transition-all duration-300 ease-in-out ${
                  isDesktopVisible && isDesktopFullscreen
                    ? "hidden"
                    : isDesktopVisible
                      ? workspaceTab === "canvas"
                        ? "flex-1 min-w-[320px] max-w-[440px] border-r border-zinc-200 dark:border-white/5"
                        : "flex-1 min-w-[380px] max-w-4xl border-r border-zinc-200 dark:border-white/5"
                      : "flex-1 min-w-0"
                }`}
              >
                {/* Tabs removed to modernize UI */}

                {/* Feed + sticky composer dock */}
                <div className="flex-1 min-h-0 overflow-hidden">
                  {viewMode === "archived" && chatItems.length === 0 ? (
                    <div className="flex h-full flex-col min-h-0">
                      <div className="flex-1 overflow-y-auto custom-scrollbar flex flex-col items-center justify-center p-8 text-center bg-transparent">
                        <p className="text-lg font-medium text-zinc-900 dark:text-zinc-100">
                          Previous chat
                        </p>
                        <p className="mt-2 max-w-md text-sm text-zinc-500 dark:text-zinc-500">
                          Send a message or open desktop to continue.
                        </p>
                        {(sessionInfo?.handoff_summary?.preview || sessionInfo?.summary) && (
                          <p className="mt-6 max-w-lg rounded-2xl bg-[#f4f4f5] dark:bg-[#1a1a1c] px-5 py-4 text-[15px] leading-relaxed text-zinc-700 dark:text-zinc-300">
                            {sessionInfo.handoff_summary?.preview || sessionInfo.summary}
                          </p>
                        )}
                      </div>
                      {canShowComposer ? (
                        <div className="shrink-0 px-6 pb-4 pt-1">
                          <div className="mx-auto w-full max-w-3xl relative rounded-[24px] border border-border-button-white bg-background-secondary-default p-2 shadow-sidebar">
                            <TodoList items={todoItems} />
                            <ChatComposer
                              inputRef={inputRef}
                              textInput={textInput}
                              onChangeText={setTextInput}
                              onSubmitText={handleTextSubmit}
                              onOpenFilePicker={handleOpenFilePicker}
                              uploadDisabled={uploadDisabled}
                              uploadedFiles={uploadedFiles}
                              onRemoveFile={handleRemoveUploadedFile}
                              onToggleMic={toggleMic}
                              isRecording={isRecording}
                              voiceStatus={voiceStatus}
                              phase={phase}
                              isLoading={isLoading}
                              isUploadingFile={isUploadingFile}
                              onStopAgent={handleStopAgent}
                              onShowDesktop={handleShowDesktop}
                              availableConnectors={availableConnectors}
                              selectedConnectorIds={selectedConnectorIds}
                              onToggleConnector={toggleConnectorSelection}
                              onToggleAllConnectors={toggleAllConnectors}
                              selectedToolIds={selectedToolIds}
                              onToggleTool={toggleToolSelection}
                              onToggleAllTools={toggleAllTools}
                              connectorsLoading={connectorsLoading}
                              onRefreshTools={refreshConnectors}
                            />
                          </div>
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <UnifiedChatPanel
                      items={chatItems}
                      isThinking={phase === "thinking"}
                      phase={phase}
                      statusLabel={agentStatus}
                      onPermissionRespond={handlePermissionRespond}
                      onQuestionRespond={handleQuestionRespond}
                      onTemplateDraftChange={handleTemplateDraftChange}
                      footer={
                        canShowComposer ? (
                          <div className="rounded-[24px] border border-border-button-white bg-background-secondary-default p-2 shadow-sidebar">
                            <TodoList items={todoItems} />
                            <ChatComposer
                              inputRef={inputRef}
                              textInput={textInput}
                              onChangeText={setTextInput}
                              onSubmitText={handleTextSubmit}
                              onOpenFilePicker={handleOpenFilePicker}
                              uploadDisabled={uploadDisabled}
                              uploadedFiles={uploadedFiles}
                              onRemoveFile={handleRemoveUploadedFile}
                              onToggleMic={toggleMic}
                              isRecording={isRecording}
                              voiceStatus={voiceStatus}
                              phase={phase}
                              isLoading={isLoading}
                              isUploadingFile={isUploadingFile}
                              onStopAgent={handleStopAgent}
                              onShowDesktop={handleShowDesktop}
                              availableConnectors={availableConnectors}
                              selectedConnectorIds={selectedConnectorIds}
                              onToggleConnector={toggleConnectorSelection}
                              onToggleAllConnectors={toggleAllConnectors}
                              selectedToolIds={selectedToolIds}
                              onToggleTool={toggleToolSelection}
                              onToggleAllTools={toggleAllTools}
                              connectorsLoading={connectorsLoading}
                              onRefreshTools={refreshConnectors}
                            />
                          </div>
                        ) : null
                      }
                    />
                  )}
                </div>
              </div>

              {/* Right: Desktop panel */}
              {isDesktopVisible ? (
                <div className="flex-[2] min-w-0 flex overflow-hidden transition-all duration-300 ease-in-out">
                  <div className="flex-1 flex flex-col overflow-hidden p-0 bg-zinc-50 dark:bg-[#151515]">
                    <div className="w-full h-full xl:max-w-7xl mx-auto rounded-xl overflow-hidden border border-zinc-200 dark:border-zinc-800/80 shadow-2xl relative">
                      <WorkflowDesktopContainer
                        workflowRun={workflowRun}
                        streamUrl={streamUrl}
                        artifacts={runArtifacts}
                        analysis={latestAnalysis}
                        forcedTab={forcedTab}
                        onForcedTabAck={() => setForcedTab(null)}
                        onTabChange={setWorkspaceTab}
                        phase={phase}
                        agentStatus={agentStatus}
                        agentAction={agentAction}
                        onStopAgent={handleStopAgent}
                        sessionId={sessionId}
                        isFullscreen={isDesktopFullscreen}
                        terminalSession={terminalSession}
                        editorSession={editorSession}
                      />
                    </div>
                  </div>
                </div>
              ) : null}
            </div>

            {/* ─── Footer ─── */}
            {/* <StatusBar phase={phase} isConnected={viewMode === "live" && isConnected} tokenQuota={tokenQuota} /> */}
          </SessionCanvasProvider>
            )}
            </div>
            </>
            );
            }
