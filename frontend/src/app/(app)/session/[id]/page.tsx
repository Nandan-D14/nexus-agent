/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  type ChangeEvent,
  useCallback,
  useEffect,
  useLayoutEffect,
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

import { SessionNavSidebar } from "@/components/session-nav-sidebar";
import { WorkflowTemplateEditorModal } from "@/components/workflow-template-editor-modal";
import { UnifiedChatPanel } from "@/components/unified-chat-panel";
import { TodoList } from "@/components/todo-list";
import { useLiveDesktop } from "@/components/live-desktop-provider";
import { WorkflowDesktopContainer } from "@/components/workflow-desktop-container";
import type { WorkflowRun } from "@/components/agent-workflow-panel";
import type { StepType } from "@/components/workflow-step";
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
  WorkflowTemplateInputField,
} from "@/lib/message-types";
import { authenticatedFetch, parseApiError } from "@/lib/api-client";
import { useMicrophone } from "@/lib/use-microphone";
import { useSession } from "@/lib/use-session";
import { useWorkflowTemplates } from "@/lib/use-workflow-templates";
import { useWebSocket } from "@/lib/use-websocket";
import { useToast } from "@/components/toast-provider";
import { useSettings } from "@/lib/settings-context";
import {
  classifyAgentTool,
  displayAgentToolName,
  surfaceForAgentTool,
} from "@/lib/agent-tool-classification";

import {
  type ChatItem,
  type PendingSessionAction,
  type PendingTurnInput,
  type SessionConnector,
  type SessionUploadResponse,
  type TemplateFormValue,
  SYSTEM_CONNECTOR,
  EMPTY_TEMPLATE,
  providerLogo,
  toolAction,
  displayStepTitle,
  upsertRunArtifact,
  normalizePendingTurnInput,
  upsertRunStep,
  upsertArtifact,
  mapStoredMessagesToChatItems,
  buildSessionTemplateDraft,
} from "@/lib/session-utils";

import { SessionHeader } from "@/components/session";
import { SessionLandingView } from "@/components/session/session-landing-view";
import { ChatComposer } from "@/components/session/chat-composer";

import type { AgentVisualAction } from "@/components/desktop-panel";

/* ------------------------------------------------------------------ */
/*  Page component                                                     */
/* ------------------------------------------------------------------ */

export default function SessionPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const sessionId = params.id as string;
  const { user, isLoading: authLoading } = useAuth();
  const { setIsSettingsOpen, requiresByokSetup } = useSettings();
  const {
    createSession,
    continueSession,
    getSession,
    getSessionMessages,
    getSessionArtifacts,
    getSessionRun,
    getSessionRunSteps,
    refreshTicket,
    destroySession,
    isLoading,
    error,
  } = useSession();
  const { saveSessionAsTemplate } = useWorkflowTemplates();
  const { toast } = useToast();
  const isNewSession = sessionId === "new";
  const shouldAutoResume = searchParams.get("resume") === "1";
  const shouldAutoContinue = searchParams.get("continue") === "1";

  const [sessionInfo, setSessionInfo] = useState<SessionInfo | null>(null);
  const [sessionData, setSessionData] = useState<SessionData | null>(null);
  const [runInfo, setRunInfo] = useState<RunInfo | null>(null);
  const [runSteps, setRunSteps] = useState<RunStep[]>([]);
  const [workflowRun, setWorkflowRun] = useState<WorkflowRun | null>(null);
  const [forcedTab, setForcedTab] = useState<"workflow" | "desktop" | null>(null);
  const [runArtifacts, setRunArtifacts] = useState<RunArtifact[]>([]);
  const [viewMode, setViewMode] = useState<"live" | "archived">("live");
  const [pageError, setPageError] = useState<string | null>(null);
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [phase, setPhase] = useState<SessionPhase>("idle");
  const [chatItems, setChatItems] = useState<ChatItem[]>([]);
  const [textInput, setTextInput] = useState("");
  const [availableConnectors, setAvailableConnectors] = useState<SessionConnector[]>([SYSTEM_CONNECTOR]);
  const [selectedConnectorIds, setSelectedConnectorIds] = useState<string[]>([]);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedInputFile[]>([]);
  const [todoItems, setTodoItems] = useState<Array<{ title: string; status: "pending" | "in_progress" | "done"; note?: string }>>([]);
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
  const [isTemplateDialogOpen, setIsTemplateDialogOpen] = useState(false);
  const [templateDraft, setTemplateDraft] = useState<TemplateFormValue>(EMPTY_TEMPLATE);
  const [isSavingTemplate, setIsSavingTemplate] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState<
    "available" | "unavailable" | "connecting" | "connected" | "reconnecting" | "disconnected"
  >("disconnected");
  const audioPlayer = useRef(new AudioPlayer());
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const landingInputRef = useRef<HTMLTextAreaElement>(null);
  const streamUrlRef = useRef<string | null>(null);
  const viewModeRef = useRef<"live" | "archived">("live");
  const autoActionHandledRef = useRef(false);
  const pendingActionKeyRef = useRef(`nexus.pendingSessionAction:${sessionId}`);
  const autoResumeTriggeredRef = useRef(false);
  const { registerDesktop, clearDesktop, minimizeDesktop } = useLiveDesktop();
  const minimizeDesktopRef = useRef(minimizeDesktop);
  const wsUrl =
    typeof window !== "undefined"
      ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${process.env.NEXT_PUBLIC_AGENT_WS_URL?.replace(/^wss?:\/\//, "") || "localhost:8000"}/ws/${sessionId}?ticket=${sessionData?.ws_ticket || ""}`
      : null;

  const shouldConnectWs =
    !isNewSession &&
    viewMode === "live" &&
    Boolean(sessionData?.ws_ticket) &&
    hasActivatedSession;
  const durableTaskId =
    sessionData?.task_id && sessionData.task_id.startsWith("task_")
      ? sessionData.task_id
      : null;

  // Keep refs in sync for unmount cleanup
  streamUrlRef.current = streamUrl;
  viewModeRef.current = viewMode;
  minimizeDesktopRef.current = minimizeDesktop;

  const { sendBinary, sendJson, isConnected, onBinaryMessageRef, onJsonMessageRef } =
    useWebSocket(shouldConnectWs ? wsUrl : null, durableTaskId);

  const handleSpeechStart = useCallback(() => {
    // Zero-latency barge-in: stop agent audio the moment the user starts speaking
    audioPlayer.current.stop();
  }, []);

  const { start: startMic, stop: stopMic, isRecording } =
    useMicrophone(sendBinary, handleSpeechStart);

  useEffect(() => {
    if (authLoading || !user) {
      setAvailableConnectors([SYSTEM_CONNECTOR]);
      return;
    }

    let cancelled = false;

    async function loadAvailableConnectors() {
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
        if (!cancelled) {
          setAvailableConnectors(nextConnectors);
          setSelectedConnectorIds((prev) =>
            prev.filter((id) => nextConnectors.some((connector) => connector.connection_id === id)),
          );
        }
      } catch (error) {
        console.warn("[session] Failed to load connectors", error);
        if (!cancelled) {
          setAvailableConnectors([SYSTEM_CONNECTOR]);
          setSelectedConnectorIds((prev) => prev.filter((id) => id === SYSTEM_CONNECTOR.connection_id));
        }
      }
    }

    void loadAvailableConnectors();

    return () => {
      cancelled = true;
    };
  }, [authLoading, user]);

  /* ---- Audio playback ---- */
  useEffect(() => {
    onBinaryMessageRef.current = (data: ArrayBuffer) => {
      audioPlayer.current.play(data);
    };
  }, [onBinaryMessageRef]);

  /* ---- Keyboard shortcut: "/" to focus input ---- */
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (
        e.key === "/" &&
        !["INPUT", "TEXTAREA"].includes(
          (document.activeElement?.tagName ?? ""),
        )
      ) {
        e.preventDefault();
        inputRef.current?.focus();
        landingInputRef.current?.focus();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  useLayoutEffect(() => {
    const maxHeight = 200;
    const el1 = landingInputRef.current;
    if (el1) {
      el1.style.height = "auto";
      el1.style.height = `${Math.min(el1.scrollHeight, maxHeight)}px`;
    }
    const el2 = inputRef.current;
    if (el2) {
      el2.style.height = "auto";
      el2.style.height = `${Math.min(el2.scrollHeight, maxHeight)}px`;
    }
  }, [textInput]);

  useEffect(() => {
    autoActionHandledRef.current = false;
    autoResumeTriggeredRef.current = false;
    pendingActionKeyRef.current = `nexus.pendingSessionAction:${sessionId}`;
  }, [sessionId]);

  /* ---- WS message handler ---- */
  const handleLastMessage = useCallback((msg: WsMessage) => {
    const ts = Date.now();

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

      case "artifact_created":
        setRunArtifacts((prev) => upsertArtifact(prev, msg.artifact));
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

      case "transcript":
        setChatItems((prev) => [
          ...prev,
          { kind: "message", role: msg.role, text: msg.text, ts },
        ]);
        if (msg.role === "agent") {
          setPhase("done");
          setAgentAction(null);
        }
        break;

      case "agent_thinking":
        setPhase("thinking");
        setAgentStatus("Thinking...");
        setChatItems((prev) => [
          ...prev,
          { kind: "event", type: msg.type, content: msg.content, ts },
        ]);
        break;

      case "agent_tool_call":
        setPhase("acting");
        setAgentStatus(`Running ${displayAgentToolName(msg.tool)}...`);
        setAgentAction(toolAction(msg.tool, msg.args));
        setForcedTab(surfaceForAgentTool(msg.tool));
        setChatItems((prev) => [
          ...prev,
          { kind: "event", type: msg.type, tool: msg.tool, args: msg.args, ts },
        ]);
        break;

      case "agent_tool_result":
        setChatItems((prev) => [
          ...prev,
          { kind: "event", type: msg.type, tool: msg.tool, output: msg.output, ts },
        ]);
        break;

      case "agent_screenshot":
        setAgentAction({ kind: "observe", label: "Observing screen", ts });
        setForcedTab("desktop");
        setChatItems((prev) => [
          ...prev,
          {
            kind: "event",
            type: msg.type,
            image_b64: msg.image_b64,
            analysis: msg.analysis,
            ts,
          },
        ]);
        break;

      case "agent_complete":
        setPhase("done");
        setAgentStatus("");
        setAgentAction(null);
        setChatItems((prev) => [
          ...prev,
          { kind: "event", type: msg.type, summary: msg.summary, ts },
        ]);
        break;

      case "agent_delegation":
        setActiveAgent(msg.to);
        setChatItems((prev) => [
          ...prev,
          { kind: "delegation", from: msg.from, to: msg.to, ts },
        ]);
        break;

      case "permission_request":
        setChatItems((prev) => [
          ...prev,
          {
            kind: "permission",
            task_id: msg.task_id,
            approval_id: msg.approval_id,
            durable_task_id: msg.durable_task_id,
            description: msg.description,
            estimated_seconds: msg.estimated_seconds,
            agent: msg.agent,
            ts,
          },
        ]);
        break;

      case "bg_task_progress":
        setChatItems((prev) => [
          ...prev,
          {
            kind: "event",
            type: msg.type,
            task_id: msg.task_id,
            progress: msg.progress,
            message: msg.message,
            ts,
          },
        ]);
        break;

      case "bg_task_complete":
        setChatItems((prev) => [
          ...prev,
          {
            kind: "event",
            type: msg.type,
            task_id: msg.task_id,
            success: msg.success,
            result: msg.result,
            ts,
          },
        ]);
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
        setChatItems((prev) => [
          ...prev,
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
        ]);
        break;

      case "resume_recovery":
        setChatItems((prev) => [
          ...prev,
          {
            kind: "event",
            type: msg.type,
            state: msg.state,
            message: msg.message,
            reused_context_digest: msg.reused_context_digest,
            ts,
          },
        ]);
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
        setChatItems((prev) => [
          ...prev,
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
        ]);
        break;

      case "todo_list_updated":
        setTodoItems(msg.items);
        break;

      case "error":
        setPageError(msg.detail || msg.message);
        setPhase("done");
        setAgentStatus("");
        setAgentAction(null);
        setChatItems((prev) => [
          ...prev,
          {
            kind: "event",
            type: msg.type,
            code: msg.code,
            message: msg.message,
            detail: msg.detail,
            ts,
          },
        ]);
        break;

      case "quota_update":
        break;

      case "pong":
        break;

      case "ui_action":
        if (msg.action === "switch_tab") {
          setForcedTab(msg.target);
        }
        break;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---- Wire up JSON message handler via ref (avoids React batching loss) ---- */
  useEffect(() => {
    onJsonMessageRef.current = handleLastMessage;
  }, [handleLastMessage, onJsonMessageRef]);

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
      // Minimize to PiP when navigating away from an active live session
      const url = streamUrlRef.current;
      const mode = viewModeRef.current;
      if (url && mode === "live") {
        minimizeDesktopRef.current({ sessionId, streamUrl: url });
      }
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
      setWorkflowRun(null);
      return;
    }

    const runStatusMap: Record<string, "pending" | "running" | "completed" | "failed"> = {
      "pending": "pending",
      "running": "running",
      "completed": "completed",
      "failed": "failed",
      "success": "completed",
      "error": "failed",
    };
    const stepStatusMap: Record<string, "pending" | "in_progress" | "completed" | "failed"> = {
      "pending": "pending",
      "running": "in_progress",
      "in_progress": "in_progress",
      "completed": "completed",
      "failed": "failed",
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
        stepType === "completion"
      ) {
        return stepType;
      }
      return "observation";
    };

    setWorkflowRun({
      run_id: runInfo.run_id,
      title: runInfo.title || "Agent Workflow",
      status: runStatusMap[runInfo.status] || "running",
      steps: runSteps.map((step) => {
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
      }),
    });
  }, [runInfo, runSteps]);

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
      setIsTemplateDialogOpen(false);
      setTemplateDraft(EMPTY_TEMPLATE);
      setIsSavingTemplate(false);
      setViewMode("live");

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
      const [messages, run, steps, artifacts] = await Promise.all([
        getSessionMessages(sessionId),
        getSessionRun(sessionId),
        getSessionRunSteps(sessionId),
        getSessionArtifacts(sessionId),
      ]);
      if (cancelled) return;
      setChatItems(mapStoredMessagesToChatItems(messages));
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
          stream_url: info.stream_url,
          ws_ticket: wsTicket,
          status: info.status,
          created_at: info.created_at,
          current_run_id: info.current_run_id,
          run_status: info.run_status,
          artifact_count: info.artifact_count,
        });
        setStreamUrl(info.stream_url);

        // If the session is already active with a stream URL,
        // auto-activate so the desktop renders immediately on reconnect
        if (info.stream_url && (info.status === "active" || info.status === "ready")) {
          setHasActivatedSession(true);
          setIsDesktopVisible(true);
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
    refreshTicket,
    router,
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
        uploaded_files: pendingText.uploadedFiles,
      });
      setPendingText(null);
    }

    if (pendingMicStart && voiceStatus === "connected") {
      startMic();
      setPendingMicStart(false);
      setPhase("listening");
    }

    if (pendingDesktopStart) {
      sendJson({ type: "start_desktop" });
      setPendingDesktopStart(false);
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
    async (action: PendingSessionAction) => {
      if (isLoading) {
        return;
      }

      if (action.type === "prompt" || action.type === "demo") {
        const payload = normalizePendingTurnInput(action.payload);
        if (!payload) {
          return;
        }
        action = { ...action, payload };
      }

      setPageError(null);
      const session = await createSession({ mode: "fresh" });
      if (!session) {
        setPageError("Failed to create a new thread.");
        return;
      }

      if (action.type === "prompt" || action.type === "demo") {
        setTextInput("");
      }

      try {
        sessionStorage.setItem(
          `nexus.pendingSessionAction:${session.session_id}`,
          JSON.stringify(action),
        );
      } catch {
        // Ignore storage failures and continue to the created session.
      }

      router.replace(`/session/${session.session_id}`);
    },
    [createSession, isLoading, router],
  );

  const createThreadFromPrompt = useCallback(
    async (payload: PendingTurnInput) => {
      const nextPayload = normalizePendingTurnInput(payload);
      if (!nextPayload) {
        return;
      }

      await createThreadFromAction({ type: "prompt", payload: nextPayload });
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
        uploaded_files: nextPayload.uploadedFiles,
      });
    },
    [continueCurrentThread, hasActivatedSession, isConnected, isNewSession, sendJson, viewMode],
  );

  /* ---- Actions ---- */
  const toggleMic = useCallback(() => {
    if (requiresByokSetup) {
      setIsSettingsOpen(true);
      toast("Please set up your API keys to continue.", "info");
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
    hasActivatedSession,
    isConnected,
    isNewSession,
    isRecording,
    sendJson,
    startMic,
    stopMic,
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

  const handleOpenFilePicker = useCallback(() => {
    if (isNewSession || viewMode !== "live" || !sessionData?.session_id) {
      toast("File upload is available in a live session.", "error");
      return;
    }
    fileInputRef.current?.click();
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

  const handleTextSubmit = useCallback(() => {
    const text = textInput.trim();
    if (!text) return;

    if (requiresByokSetup) {
      setIsSettingsOpen(true);
      toast("Please set up your API keys to continue.", "info");
      return;
    }

    const payload: PendingTurnInput = {
      text,
      connectorIds: selectedConnectorIds,
      uploadedFiles,
    };
    if (isNewSession) {
      void createThreadFromPrompt(payload);
      setTextInput("");
      return;
    }
    sendTextOrQueue(payload);
    setTextInput("");
    setUploadedFiles([]);
  }, [createThreadFromPrompt, isNewSession, requiresByokSetup, selectedConnectorIds, sendTextOrQueue, setIsSettingsOpen, textInput, toast, uploadedFiles]);

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
    (text: string) => {
      if (requiresByokSetup) {
        setIsSettingsOpen(true);
        toast("Please set up your API keys to continue.", "info");
        return;
      }
      const payload: PendingTurnInput = { text };
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
    [continueCurrentThread, createThreadFromAction, isNewSession, requiresByokSetup, sendTextOrQueue, setIsSettingsOpen, toast, viewMode],
  );

  const handlePermissionRespond = useCallback(
    (
      taskId: string,
      approved: boolean,
      approvalId?: string,
      durableTaskId?: string,
    ) => {
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

  const handleStopAgent = useCallback(() => {
    sendJson({ type: "stop_agent" });
    setPhase("done");
    setAgentStatus("");
  }, [sendJson]);

  useEffect(() => {
    if (isNewSession || viewMode !== "live" || !sessionData?.session_id) {
      return;
    }
    if (autoActionHandledRef.current) {
      return;
    }

    try {
      const key = pendingActionKeyRef.current;
      const raw = sessionStorage.getItem(key);
      if (!raw) {
        return;
      }
      sessionStorage.removeItem(key);

      const action = JSON.parse(raw) as PendingSessionAction | { type: "demo" | "prompt"; text?: string };

      autoActionHandledRef.current = true;

      if (action.type === "openDesktop") {
        setHasActivatedSession(true);
        setIsDesktopVisible(true);
        setPendingDesktopStart(true);
      } else if (action.type === "startMic") {
        setHasActivatedSession(true);
        setPendingMicStart(true);
        setPhase("listening");
      } else if (action.type === "demo" || action.type === "prompt") {
        const payload = normalizePendingTurnInput(
          "payload" in action ? action.payload : { text: action.text ?? "" },
        );
        if (!payload) {
          return;
        }
        setHasActivatedSession(true);
        setPendingText(payload);
        setPhase("thinking");
      }
    } catch {
      // Ignore invalid storage payloads.
    }
  }, [isNewSession, sessionData?.session_id, viewMode]);

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

  const handleEnd = async () => {
    audioPlayer.current.stop();
    stopMic();
    if (isNewSession) {
      router.push("/dashboard");
      return;
    }
    if (viewMode === "live") {
      try {
        await destroySession(sessionId);
        clearDesktop(sessionId);
      } catch (err) {
        console.error("[handleEnd] Failed to destroy session:", err);
      }
    }
    router.push("/dashboard");
  };

  const handleOpenSaveTemplate = useCallback(() => {
    if (isNewSession) {
      return;
    }
    setTemplateDraft(
      buildSessionTemplateDraft(sessionInfo, runInfo, runSteps, runArtifacts),
    );
    setIsTemplateDialogOpen(true);
  }, [isNewSession, runArtifacts, runInfo, runSteps, sessionInfo]);

  const handleSaveTemplate = useCallback(
    async (draft: TemplateFormValue) => {
      if (isNewSession) {
        return;
      }
      setIsSavingTemplate(true);
      try {
        const template = await saveSessionAsTemplate(sessionId, {
          name: draft.name,
          description: draft.description,
          instructions: draft.instructions,
          inputFields: draft.inputFields,
        });
        if (!template) {
          toast("Failed to save this session as a template.", "error");
          return;
        }
        toast(`Saved "${template.name}" as a workflow template.`, "success");
        setIsTemplateDialogOpen(false);
      } finally {
        setIsSavingTemplate(false);
      }
    },
    [isNewSession, saveSessionAsTemplate, sessionId, toast],
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
            viewMode={viewMode}
            onShowDesktop={handleShowDesktop}
            onOpenSettings={() => setIsSettingsOpen(true)}
            onEndSession={handleEnd}
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
            onToggleAllConnectors={(ids) => {
              if (ids.every((id) => selectedConnectorIds.includes(id))) {
                setSelectedConnectorIds((prev) =>
                  prev.filter((id) => !ids.includes(id))
                );
              } else {
                setSelectedConnectorIds((prev) =>
                  Array.from(new Set([...prev, ...ids]))
                );
              }
            }}
            pageError={pageError}
            error={error}
            landingInputRef={landingInputRef}
          />
        ) : (
          <>
            {/* ─── Header ─── */}
            <SessionHeader
              viewMode={viewMode}
              isConnected={isConnected}
              isNewSession={isNewSession}
              isDesktopVisible={isDesktopVisible}
              isDesktopFullscreen={isDesktopFullscreen}
              onToggleDesktopFullscreen={handleToggleDesktopFullscreen}
              onShowDesktop={handleShowDesktop}
              onHideDesktop={handleHideDesktop}
              onOpenSaveTemplate={handleOpenSaveTemplate}
              onOpenSettings={() => setIsSettingsOpen(true)}
              onEndSession={handleEnd}
            />

            {/* ─── Main content: Desktop + Chat ─── */}
            <div className="flex-1 flex overflow-hidden min-h-0">
              {/* Left/Middle: Chat Sidebar */}
              <div
                className={`overflow-hidden flex flex-col transition-all duration-300 ease-in-out ${
                  isDesktopVisible && isDesktopFullscreen
                    ? "hidden"
                    : isDesktopVisible
                      ? "flex-1 min-w-[380px] max-w-4xl border-r border-zinc-200 dark:border-white/5"
                      : "flex-1 min-w-0"
                }`}
              >
                {/* Tabs removed to modernize UI */}

                {/* Feed container */}
                <div className="flex-1 overflow-y-auto min-h-0 custom-scrollbar">
                  {viewMode === "archived" && chatItems.length === 0 ? (
                    <div className="flex h-full flex-col items-center justify-center p-8 text-center bg-transparent">
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
                  ) : (
                    <UnifiedChatPanel
                      items={chatItems}
                      isThinking={phase === "thinking"}
                      phase={phase}
                      onPermissionRespond={handlePermissionRespond}
                    />
                  )}
                </div>

                {/* Input area */}
                {canShowComposer ? (
                  <div className="px-4 pb-6 pt-2 shrink-0">
                    <div className="mx-auto w-full max-w-3xl relative">
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
                        onToggleAllConnectors={(ids) => {
                          if (ids.every((id) => selectedConnectorIds.includes(id))) {
                            setSelectedConnectorIds((prev) =>
                              prev.filter((id) => !ids.includes(id))
                            );
                          } else {
                            setSelectedConnectorIds((prev) =>
                              Array.from(new Set([...prev, ...ids]))
                            );
                          }
                        }}
                      />
                    </div>
                  </div>
                ) : null}
              </div>

              {/* Right: Desktop panel */}
              {viewMode === "live" && isDesktopVisible ? (
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
                        phase={phase}
                        agentStatus={agentStatus}
                        agentAction={agentAction}
                        onStopAgent={handleStopAgent}
                      />
                    </div>
                  </div>
                </div>
              ) : null}
            </div>

            {/* ─── Footer ─── */}
            {/* <StatusBar phase={phase} isConnected={viewMode === "live" && isConnected} tokenQuota={tokenQuota} /> */}

            {(pageError || error) && (
              <div className="border-t border-red-500/20 bg-red-950/20 px-4 py-2 text-sm text-red-300">
                {pageError || error}
              </div>
            )}
            {isLoading && (
              <div className="border-t border-card-border dark:border-[#1c1c1e] bg-card dark:bg-[#09090b] px-4 py-2 text-sm text-muted dark:text-zinc-500">
                Loading session...
              </div>
            )}
            <WorkflowTemplateEditorModal
              open={isTemplateDialogOpen}
              title="Save as Template"
              subtitle="Capture this session as a reusable workflow template."
              submitLabel="Save Template"
              initialValue={templateDraft}
              isSubmitting={isSavingTemplate}
              onClose={() => setIsTemplateDialogOpen(false)}
              onSubmit={handleSaveTemplate}
            />
            </>
            )}
            </div>
            </>
            );
            }

