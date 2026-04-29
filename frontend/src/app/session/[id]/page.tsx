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

import { Check, ChevronDown, Link2, Paperclip, X, Plus, Monitor, Mic, ArrowUp, Signal, Globe, User, Settings, Search } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

import { DemoPicker } from "@/components/demo-picker";
import { DesktopPanel } from "@/components/desktop-panel";
import { ContextPacketPanel } from "@/components/context-packet-panel";
import { MicButton } from "@/components/mic-button";
import { OutputsPanel } from "@/components/outputs-panel";
import { RunLogPanel } from "@/components/run-log-panel";
import { SessionNavSidebar } from "@/components/session-nav-sidebar";
import { WorkflowTemplateEditorModal } from "@/components/workflow-template-editor-modal";
import { UnifiedChatPanel } from "@/components/unified-chat-panel";
import { TodoList } from "@/components/todo-list";
import { useLiveDesktop } from "@/components/live-desktop-provider";
import { WorkflowDesktopContainer } from "@/components/workflow-desktop-container";
import type { WorkflowRun } from "@/components/agent-workflow-panel";
import { useAuth } from "@/lib/auth-context";
import { AudioPlayer } from "@/lib/audio-playback";
import type {
  ArchivedMessage,
  ContextPacket,
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

/* ------------------------------------------------------------------ */
/*  Unified chat item type                                             */
/* ------------------------------------------------------------------ */

type ChatItem =
  | { kind: "message"; role: "user" | "agent"; text: string; ts: number }
  | { kind: "event"; type: string; ts: number; [key: string]: unknown }
  | {
      kind: "permission";
      task_id: string;
      description: string;
      estimated_seconds: number;
      agent: string;
      ts: number;
    }
  | { kind: "delegation"; from: string; to: string; ts: number };

type PendingSessionAction =
  | { type: "demo"; payload: PendingTurnInput }
  | { type: "prompt"; payload: PendingTurnInput }
  | { type: "openDesktop" }
  | { type: "startMic" };

type SessionSurface = "conversation" | "run_log" | "outputs" | "context";

type ContextPacketMeta = {
  stage: string;
  action: string;
  estimated_tokens?: number;
  reasoning_model: string;
  vision_model: string;
};

type PendingTurnInput = {
  text: string;
  connectorIds?: string[];
  uploadedFiles?: UploadedInputFile[];
};

type SessionConnector = {
  connection_id: string;
  connector_type: string;
  provider: string;
  name: string;
  enabled: boolean;
  status: string;
};

type SessionUploadResponse = {
  path: string;
  artifact: RunArtifact;
  drive_status?: string | null;
  drive_file_id?: string | null;
  drive_web_view_link?: string | null;
  drive_folder_path?: string | null;
};

const SYSTEM_CONNECTOR: SessionConnector = {
  connection_id: "system",
  connector_type: "system",
  provider: "system",
  name: "Cloud Desktop Tools",
  enabled: true,
  status: "connected",
};

function upsertRunArtifact(prev: RunArtifact[], nextArtifact: RunArtifact): RunArtifact[] {
  const existingIndex = prev.findIndex((artifact) => artifact.artifact_id === nextArtifact.artifact_id);
  if (existingIndex === -1) {
    return [nextArtifact, ...prev];
  }
  const updated = [...prev];
  updated[existingIndex] = nextArtifact;
  return updated;
}

function normalizePendingTurnInput(value: unknown): PendingTurnInput | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const record = value as Record<string, unknown>;
  const text = typeof record.text === "string" ? record.text.trim() : "";
  if (!text) {
    return null;
  }
  const connectorIds = Array.isArray(record.connectorIds)
    ? record.connectorIds.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];
  const uploadedFiles = Array.isArray(record.uploadedFiles)
    ? record.uploadedFiles.filter((item): item is UploadedInputFile => Boolean(item && typeof item === "object"))
    : [];
  return { text, connectorIds, uploadedFiles };
}

function connectorButtonLabel(connectors: SessionConnector[], selectedIds: string[]): string {
  if (selectedIds.length === 0) return "Connectors";
  if (selectedIds.length === 1) {
    return connectors.find((connector) => connector.connection_id === selectedIds[0])?.name ?? "1 connector";
  }
  return `${selectedIds.length} connectors`;
}

function upsertRunStep(prev: RunStep[], nextStep: RunStep): RunStep[] {
  const existingIndex = prev.findIndex((step) => step.step_id === nextStep.step_id);
  if (existingIndex === -1) {
    return [...prev, nextStep].sort((left, right) => left.step_index - right.step_index);
  }
  const updated = [...prev];
  updated[existingIndex] = nextStep;
  return updated.sort((left, right) => left.step_index - right.step_index);
}

function upsertArtifact(prev: RunArtifact[], artifact: RunArtifact): RunArtifact[] {
  const existingIndex = prev.findIndex((item) => item.artifact_id === artifact.artifact_id);
  if (existingIndex === -1) {
    return [artifact, ...prev];
  }
  const updated = [...prev];
  updated[existingIndex] = artifact;
  return updated;
}

function mapStoredMessagesToChatItems(messages: ArchivedMessage[]): ChatItem[] {
  return messages.map((message) => ({
    kind: "message" as const,
    role: message.role,
    text: message.text,
    ts: message.created_at ? new Date(message.created_at).getTime() : Date.now(),
  }));
}

type TemplateFormValue = {
  name: string;
  description: string;
  instructions: string;
  inputFields: WorkflowTemplateInputField[];
};

const EMPTY_TEMPLATE: TemplateFormValue = {
  name: "",
  description: "",
  instructions: "",
  inputFields: [],
};

function buildSessionTemplateDraft(
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

/* ------------------------------------------------------------------ */
/*  Page component                                                     */
/* ------------------------------------------------------------------ */

export default function SessionPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const sessionId = params.id as string;
  const { user, isLoading: authLoading } = useAuth();
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
  const [activeSurface, setActiveSurface] = useState<SessionSurface>("conversation");
  const [pageError, setPageError] = useState<string | null>(null);
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [phase, setPhase] = useState<SessionPhase>("idle");
  const [chatItems, setChatItems] = useState<ChatItem[]>([]);
  const [contextMeta, setContextMeta] = useState<ContextPacketMeta | null>(null);
  const [textInput, setTextInput] = useState("");
  const [availableConnectors, setAvailableConnectors] = useState<SessionConnector[]>([SYSTEM_CONNECTOR]);
  const [selectedConnectorIds, setSelectedConnectorIds] = useState<string[]>([]);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedInputFile[]>([]);
  const [todoItems, setTodoItems] = useState<Array<{ title: string; status: "pending" | "in_progress" | "done"; note?: string }>>([]);
  const [isConnectorMenuOpen, setIsConnectorMenuOpen] = useState(false);
  const [connectorSearch, setConnectorSearch] = useState("");
  const [isUploadingFile, setIsUploadingFile] = useState(false);
  const [hasActivatedSession, setHasActivatedSession] = useState(false);
  const [isContinuingThread, setIsContinuingThread] = useState(false);
  const [isDesktopVisible, setIsDesktopVisible] = useState(false);
  const [isDesktopFullscreen, setIsDesktopFullscreen] = useState(false);
  const [pendingText, setPendingText] = useState<PendingTurnInput | null>(null);
  const [pendingMicStart, setPendingMicStart] = useState(false);
  const [activeAgent, setActiveAgent] = useState<string>("nexus");
  const [agentStatus, setAgentStatus] = useState("");
  const [isTemplateDialogOpen, setIsTemplateDialogOpen] = useState(false);
  const [templateDraft, setTemplateDraft] = useState<TemplateFormValue>(EMPTY_TEMPLATE);
  const [isSavingTemplate, setIsSavingTemplate] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState<
    "available" | "unavailable" | "connecting" | "connected" | "reconnecting" | "disconnected"
  >("disconnected");
  const audioPlayer = useRef(new AudioPlayer());
  const inputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const connectorMenuRef = useRef<HTMLDivElement>(null);
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

  // Keep refs in sync for unmount cleanup
  streamUrlRef.current = streamUrl;
  viewModeRef.current = viewMode;
  minimizeDesktopRef.current = minimizeDesktop;

  const { sendBinary, sendJson, isConnected, onBinaryMessageRef, onJsonMessageRef } =
    useWebSocket(shouldConnectWs ? wsUrl : null);

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

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!connectorMenuRef.current?.contains(event.target as Node)) {
        setIsConnectorMenuOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, []);

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
        if (msg.role === "agent") setPhase("done");
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
        setAgentStatus(`Running ${msg.tool}...`);
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
        setContextMeta({
          stage: msg.stage,
          action: msg.action,
          estimated_tokens: msg.estimated_tokens,
          reasoning_model: msg.reasoning_model,
          vision_model: msg.vision_model,
        });
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
        setAgentStatus("");
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

    const statusMap: Record<string, "pending" | "running" | "completed" | "failed"> = {
      "pending": "pending",
      "running": "running",
      "completed": "completed",
      "failed": "failed",
      "success": "completed",
      "error": "failed",
    };

    setWorkflowRun({
      run_id: runInfo.run_id,
      title: runInfo.title || "Agent Workflow",
      status: statusMap[runInfo.status] || "running",
      steps: runSteps.map((step) => ({
        step_id: step.step_id,
        type: step.type as "thinking" | "tool_call" | "tool_result" | "observation" | "screenshot" | "error" | "completion",
        status: statusMap[step.status] || "pending",
        title: step.title || `${step.type} step`,
        detail: step.detail || "",
        created_at: step.created_at,
        command: step.command,
        args: step.args,
        output: step.output,
        error: step.error,
        image_b64: step.image_b64,
      })),
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
      setActiveSurface("conversation");
      setRunInfo(null);
      setRunSteps([]);
      setRunArtifacts([]);
      setContextMeta(null);
      setStreamUrl(null);
      setSessionData(null);
      setSessionInfo(null);
      setVoiceStatus("connected");
      setHasActivatedSession(false);
      setIsDesktopVisible(false);
      setPendingText(null);
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
  }, [isConnected, pendingMicStart, pendingText, sendJson, startMic, viewMode, voiceStatus]);

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
        setActiveSurface("conversation");
        setIsDesktopFullscreen(false);
        setHasActivatedSession(true);
        if (options?.openDesktop || shouldAutoResume) {
          setIsDesktopVisible(true);
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
  }, [createThreadFromPrompt, isNewSession, selectedConnectorIds, sendTextOrQueue, textInput, uploadedFiles]);

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
    }
  }, [createThreadFromAction, continueCurrentThread, hasActivatedSession, isNewSession, viewMode]);

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
    [continueCurrentThread, createThreadFromAction, isNewSession, sendTextOrQueue, viewMode],
  );

  const handlePermissionRespond = useCallback(
    (taskId: string, approved: boolean) => {
      sendJson({ type: "permission_response", task_id: taskId, approved });
    },
    [sendJson],
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
      setActiveSurface("conversation");

      if (action.type === "openDesktop") {
        setHasActivatedSession(true);
        setIsDesktopVisible(true);
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
    setActiveSurface("conversation");
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

  const handleContinueArchivedThread = useCallback(() => {
    if (isNewSession) {
      return;
    }
    setActiveSurface("conversation");
    void continueCurrentThread();
  }, [continueCurrentThread, isNewSession]);

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
  const selectedConnectorLabel = connectorButtonLabel(availableConnectors, selectedConnectorIds);
  const uploadDisabled = isNewSession || viewMode !== "live" || isUploadingFile;

  return (
    <div className="h-screen flex overflow-hidden bg-[#fafafa] dark:bg-[#1a1a1c]">
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={handleFileUpload}
      />
      {/* ─── Left nav sidebar ─── */}
      <SessionNavSidebar />

      {/* ─── Main panel ─── */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0 relative">
        {!hasStarted ? (
          <div className="flex-1 flex flex-col items-center justify-center relative p-6">
            <div className="absolute top-4 right-4 flex gap-2">
              {viewMode === "live" && (
                <button
                  suppressHydrationWarning
                  onClick={handleShowDesktop}
                  className="text-xs px-3 py-1.5 rounded-lg bg-blue-600 text-white border border-blue-700 dark:bg-blue-500 dark:border-blue-400 hover:bg-blue-700 dark:hover:bg-blue-600 transition-all duration-200"
                >
                  Open Desktop
                </button>
              )}
              <button
                suppressHydrationWarning
                onClick={() => router.push("/settings/api")}
                className="text-xs px-3 py-1.5 rounded-lg bg-blue-50 text-blue-700 border border-blue-200 dark:bg-blue-500/10 dark:border-blue-400 hover:bg-blue-100 dark:hover:bg-blue-600/20 transition-all duration-200"
              >
                Settings
              </button>
              <button
                suppressHydrationWarning
                onClick={handleEnd}
                className="text-xs px-3 py-1.5 rounded-lg border border-red-500/20 text-red-400 hover:bg-red-500/10 hover:border-red-500/30 transition-all duration-200"
              >
                Dashboard
              </button>
            </div>

            <div className="max-w-3xl w-full flex flex-col items-center gap-8 mb-20 mt-10">
              <div className="text-center space-y-4">
                <h1 className="text-3xl font-medium tracking-tight text-zinc-900 dark:text-zinc-100">
                  Welcome to CoComputer
                </h1>
                <p className="text-[15px] text-zinc-500">What can I help you with?</p>
              </div>

              {/* Redesigned Landing Input Box */}
              <div className="w-full max-w-2xl mx-auto mt-4 px-4">
                <div className="relative flex flex-col bg-transparent border border-zinc-700/50 rounded-2xl p-1 shadow-2xl transition-all focus-within:border-zinc-500/50">
                  <div className="relative min-h-[60px] flex items-start px-4 py-3">
                    <textarea
                      suppressHydrationWarning
                      ref={landingInputRef}
                      value={textInput}
                      onChange={(e) => setTextInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          handleTextSubmit();
                        }
                      }}
                      placeholder="Send message to CoComputer"
                      rows={1}
                      className="w-full bg-transparent border-none outline-none text-[15px] text-zinc-200 placeholder-zinc-500 resize-none overflow-y-auto max-h-50 focus:ring-0 leading-relaxed placeholder:font-medium"
                    />
                  </div>
                  {uploadedFiles.length > 0 ? (
                    <div className="flex flex-wrap gap-2 px-3 pb-1 mb-2">
                      {uploadedFiles.map((file) => (
                        <span
                          key={file.path}
                          className="inline-flex items-center gap-2 rounded-full border border-zinc-700 bg-zinc-800 px-3 py-1 text-xs text-zinc-200"
                        >
                          <Paperclip className="h-3.5 w-3.5" />
                          <span className="max-w-44 truncate">{file.name}</span>
                          <button
                            type="button"
                            onClick={() => handleRemoveUploadedFile(file.path)}
                            className="text-zinc-400 transition-colors hover:text-zinc-200"
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                        </span>
                      ))}
                    </div>
                  ) : null}
                  
                  <div className="flex items-center justify-between mt-1 px-2 pb-2">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={handleOpenFilePicker}
                        disabled={uploadDisabled}
                        className="p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-full transition-colors flex items-center justify-center border border-zinc-700/50 disabled:opacity-40"
                        title="Attach"
                      >
                        <Plus className="w-4 h-4" />
                      </button>
                      
                      <div ref={connectorMenuRef} className="relative">
                        <button
                          type="button"
                          onClick={() => setIsConnectorMenuOpen((open) => !open)}
                          className="p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded transition-colors flex items-center gap-1.5"
                          title="Links"
                        >
                          <Link2 className="w-4 h-4" />
                          {selectedConnectorIds.length > 0 && (
                            <span className="text-[10px] bg-indigo-500 text-white rounded-full w-4 h-4 flex items-center justify-center font-bold">
                              {selectedConnectorIds.length}
                            </span>
                          )}
                        </button>
                        <AnimatePresence>
                          {isConnectorMenuOpen && (
                            <motion.div 
                              initial={{ opacity: 0, scale: 0.95, y: 10 }}
                              animate={{ opacity: 1, scale: 1, y: 0 }}
                              exit={{ opacity: 0, scale: 0.95, y: 10 }}
                              className="absolute left-0 bottom-full mb-3 w-80 rounded-2xl border border-zinc-800 bg-[#161618] p-1.5 shadow-2xl z-50 overflow-hidden"
                            >
                              {/* Search & Actions Header */}
                              <div className="p-2 flex flex-col gap-2 border-b border-zinc-800/50 mb-1">
                                <div className="relative flex items-center">
                                  <Search className="absolute left-2.5 w-3.5 h-3.5 text-zinc-500" />
                                  <input 
                                    autoFocus
                                    type="text"
                                    value={connectorSearch}
                                    onChange={(e) => setConnectorSearch(e.target.value)}
                                    placeholder="Search tools..."
                                    className="w-full bg-zinc-900/50 border border-zinc-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-indigo-500/50 transition-all"
                                  />
                                </div>
                                <div className="flex items-center justify-between px-1">
                                  <span className="text-[10px] uppercase tracking-widest font-bold text-zinc-500">Connectors</span>
                                  <button 
                                    onClick={() => {
                                      const allIds = availableConnectors.map(c => c.connection_id);
                                      const filteredIds = availableConnectors
                                        .filter(c => c.name.toLowerCase().includes(connectorSearch.toLowerCase()))
                                        .map(c => c.connection_id);
                                      
                                      if (filteredIds.every(id => selectedConnectorIds.includes(id))) {
                                        setSelectedConnectorIds(prev => prev.filter(id => !filteredIds.includes(id)));
                                      } else {
                                        setSelectedConnectorIds(prev => Array.from(new Set([...prev, ...filteredIds])));
                                      }
                                    }}
                                    className="text-[10px] font-bold text-indigo-400 hover:text-indigo-300 transition-colors"
                                  >
                                    Toggle All
                                  </button>
                                </div>
                              </div>

                              {/* Scrollable List */}
                              <div className="max-h-64 overflow-y-auto custom-scrollbar space-y-0.5 px-0.5">
                                {availableConnectors
                                  .filter(c => c.name.toLowerCase().includes(connectorSearch.toLowerCase()))
                                  .map((connector) => {
                                    const checked = selectedConnectorIds.includes(connector.connection_id);
                                    return (
                                      <button
                                        key={connector.connection_id}
                                        type="button"
                                        onClick={() => toggleConnectorSelection(connector.connection_id)}
                                        className={`flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left transition-all ${
                                          checked ? "bg-indigo-500/5" : "hover:bg-zinc-800/60"
                                        }`}
                                      >
                                        <div className="flex items-center gap-3">
                                          <div className={`w-8 h-8 rounded-lg flex items-center justify-center border ${checked ? "border-indigo-500/30 bg-indigo-500/10" : "border-zinc-800 bg-zinc-900/50"}`}>
                                            <Globe className={`w-4 h-4 ${checked ? "text-indigo-400" : "text-zinc-500"}`} />
                                          </div>
                                          <div className="flex flex-col">
                                            <div className={`text-[13px] font-medium leading-tight ${checked ? "text-zinc-100" : "text-zinc-300"}`}>
                                              {connector.name}
                                            </div>
                                            <div className="text-[10px] uppercase tracking-wider text-zinc-500 mt-0.5 font-semibold">
                                              {connector.provider}
                                            </div>
                                          </div>
                                        </div>
                                        <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all ${
                                          checked ? "border-indigo-500 bg-indigo-500 text-white" : "border-zinc-700 bg-transparent text-transparent"
                                        }`}>
                                          <Check className="w-3 h-3 stroke-[3]" />
                                        </div>
                                      </button>
                                    );
                                  })}
                                
                                {availableConnectors.filter(c => c.name.toLowerCase().includes(connectorSearch.toLowerCase())).length === 0 && (
                                  <div className="py-8 text-center text-xs text-zinc-600 font-medium">
                                    No tools found for "{connectorSearch}"
                                  </div>
                                )}
                              </div>
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </div>

                      <button
                        type="button"
                        onClick={handleShowDesktop}
                        className="p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded transition-colors"
                        title="Workspace Context"
                      >
                        <Monitor className="w-4 h-4" />
                      </button>
                    </div>

                    <div className="flex items-center gap-2">
                       <button
                        onClick={toggleMic}
                        disabled={voiceStatus !== "connected"}
                        className={`p-1.5 rounded transition-colors ${
                          isRecording ? "text-red-400 bg-red-500/10" : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
                        } disabled:opacity-40`}
                        title="Voice Input"
                      >
                        <Mic className="w-4 h-4" />
                      </button>
                      <button
                        onClick={handleTextSubmit}
                        disabled={!textInput.trim() || isLoading || isUploadingFile}
                        className={`p-1.5 rounded-full transition-colors border border-zinc-700/50 ${
                          textInput.trim() && !isLoading && !isUploadingFile
                            ? "bg-[#3a3a3c] text-zinc-200 hover:bg-zinc-600" 
                            : "bg-zinc-800 text-zinc-500 cursor-not-allowed opacity-50"
                        }`}
                        title="Send"
                      >
                        <ArrowUp className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Demo picker */}
              {viewMode === "live" && (
                <div className="w-full max-w-4xl mx-auto mt-4 relative">
                  <DemoPicker onSelect={handleDemo} disabled={false} />
                </div>
              )}
            </div>
            
            {(pageError || error) && (
              <div className="absolute bottom-4 border border-red-500/20 bg-red-950/20 px-4 py-2 text-sm text-red-300 rounded-lg">
                {pageError || error}
              </div>
            )}
            {isLoading && (
              <div className="absolute bottom-4 border border-card-border dark:border-[#1c1c1e] bg-card dark:bg-[#09090b] px-4 py-2 text-sm text-muted dark:text-zinc-500 rounded-lg">
                Loading session...
              </div>
            )}
          </div>
        ) : (
          <>
            {/* ─── Header ─── */}
            <header className="h-14 shrink-0 flex items-center justify-between px-6 border-b border-zinc-800/30">
              <div className="flex items-center gap-4">
                <button className="flex items-center gap-2 text-[14px] font-medium text-zinc-200 hover:text-zinc-100 transition-colors">
                  CoComputer <span className="text-[10px] uppercase font-bold text-zinc-400 border border-zinc-700/80 rounded px-1.5 py-0.5 bg-zinc-800/30">Beta</span> <ChevronDown className="w-4 h-4 text-zinc-500 ml-1" />
                </button>

                {viewMode === "live" && isConnected && (
                  <div className="flex items-center gap-2 text-emerald-400 text-[13px] font-medium">
                    <Signal className="w-4 h-4" /> Connected
                  </div>
                )}

                {viewMode === "archived" && (
                  <span className="rounded-full bg-zinc-100 dark:bg-[#212126] px-2 py-0.5 text-[11px] font-medium text-zinc-600 dark:text-zinc-400">
                    Archived
                  </span>
                )}
              </div>

              <div className="flex items-center gap-4 text-[13px] font-medium">
                {viewMode === "live" && (
                  <button
                    suppressHydrationWarning
                    onClick={handleToggleDesktopFullscreen}
                    className="flex items-center gap-2 text-zinc-400 hover:text-zinc-200 transition-colors"
                  >
                    <Monitor className="w-4 h-4" />
                    {isDesktopFullscreen
                      ? "Exit Fullscreen"
                      : isDesktopVisible
                        ? "Fullscreen"
                        : "Open Desktop"}
                  </button>
                )}

                {viewMode === "live" && isDesktopVisible && !isDesktopFullscreen && (
                  <button
                    suppressHydrationWarning
                    onClick={handleHideDesktop}
                    className="text-zinc-400 hover:text-zinc-200 transition-colors"
                  >
                    Hide
                  </button>
                )}

                {!isNewSession && (
                  <button
                    suppressHydrationWarning
                    onClick={handleOpenSaveTemplate}
                    className="text-zinc-400 hover:text-zinc-200 transition-colors ml-1"
                  >
                    Save Template
                  </button>
                )}
                {viewMode === "archived" && (
                  <button
                    suppressHydrationWarning
                    onClick={handleContinueArchivedThread}
                    className="text-emerald-400 hover:text-emerald-300 transition-colors"
                  >
                    Continue
                  </button>
                )}
                
                <button className="text-zinc-400 hover:text-zinc-300 ml-2" onClick={() => router.push("/settings/api")}>
                  <Settings className="w-4 h-4" />
                </button>
                <button className="text-zinc-400 hover:text-zinc-300">
                  <User className="w-4 h-4" />
                </button>

                <button
                  suppressHydrationWarning
                  onClick={handleEnd}
                  className="text-red-400 hover:text-red-300 transition-colors ml-2"
                >
                  {viewMode === "live" ? "End" : "Exit"}
                </button>
              </div>
            </header>

            {/* ─── Main content: Desktop + Chat ─── */}
            <div className="flex-1 flex overflow-hidden">
              {/* Left/Middle: Chat Sidebar */}
              <div
                className={`bg-[#fafafa] dark:bg-[#1a1a1c] overflow-hidden transition-all duration-300 ease-in-out ${
                  isDesktopVisible && isDesktopFullscreen
                    ? "hidden"
                    : isDesktopVisible
                      ? "flex flex-col flex-1 min-w-[380px] max-w-4xl border-r border-zinc-200 dark:border-white/5"
                      : "flex flex-col flex-1 min-w-0"
                }`}
              >
                {/* Minimal top status area for Desktop mode */}
                {viewMode === "live" && (phase === "thinking" || phase === "acting") && (
                  <div className="absolute top-4 left-4 z-20 flex items-center justify-between pointer-events-none">
                    <button
                      suppressHydrationWarning
                      onClick={handleStopAgent}
                      title="Stop agent"
                      className="pointer-events-auto flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-red-500/30 bg-red-500/10 backdrop-blur text-red-500 hover:bg-red-500/20 transition-colors text-[11px] font-bold uppercase tracking-widest shadow-sm"
                    >
                      <span className="w-2 h-2 rounded-sm bg-red-500 shrink-0" />
                      Stop {phase}
                    </button>
                  </div>
                )}

                {/* Tabs removed to modernize UI */}

                {/* Feed container */}
                <div className="flex-1 overflow-hidden">
                  {viewMode === "archived" && chatItems.length === 0 ? (
                    <div className="flex h-full flex-col items-center justify-center p-8 text-center bg-transparent">
                      <p className="text-lg font-medium text-zinc-900 dark:text-zinc-100">
                        Archived session
                      </p>
                      <p className="mt-2 max-w-md text-sm text-zinc-500 dark:text-zinc-500">
                        The live desktop is no longer attached. Reuse the saved handoff or review the transcript below.
                      </p>
                      {(sessionInfo?.handoff_summary?.preview || sessionInfo?.summary) && (
                        <p className="mt-6 max-w-lg rounded-2xl bg-[#f4f4f5] dark:bg-[#1a1a1c] px-5 py-4 text-[15px] leading-relaxed text-zinc-700 dark:text-zinc-300">
                          {sessionInfo.handoff_summary?.preview || sessionInfo.summary}
                        </p>
                      )}
                      <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
                        <button
                          onClick={handleContinueArchivedThread}
                          className="rounded-full bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-700"
                        >
                          Continue Here
                        </button>
                      </div>
                    </div>
                  ) : (
                    <UnifiedChatPanel
                      items={chatItems}
                      isThinking={phase === "thinking"}
                      onPermissionRespond={handlePermissionRespond}
                    />
                  )}
                </div>

                {/* Input area */}
                {viewMode === "live" ? (
                  <div className="px-4 pb-6 pt-2 shrink-0">
                    <div className="mx-auto w-full max-w-2xl relative">
                      <TodoList items={todoItems} />
                      {uploadedFiles.length > 0 ? (
                        <div className="mb-3 flex flex-wrap gap-2">
                          {uploadedFiles.map((file) => (
                            <span
                              key={file.path}
                              className="inline-flex items-center gap-2 rounded-full border border-zinc-200 bg-white px-3 py-1 text-xs text-zinc-700 shadow-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
                            >
                              <Paperclip className="h-3.5 w-3.5" />
                              <span className="max-w-52 truncate">{file.name}</span>
                              <button
                                type="button"
                                onClick={() => handleRemoveUploadedFile(file.path)}
                                className="text-zinc-400 transition-colors hover:text-zinc-700 dark:hover:text-zinc-200"
                              >
                                <X className="h-3.5 w-3.5" />
                              </button>
                            </span>
                          ))}
                        </div>
                      ) : null}
                      <div className="relative flex flex-col bg-transparent border border-zinc-700/50 rounded-2xl p-1 shadow-2xl transition-all focus-within:border-zinc-500/50">
                        {/* Text input (Top) */}
                        <div className="relative flex w-full items-start px-4 py-3">
                          <textarea
                            suppressHydrationWarning
                            ref={inputRef}
                            value={textInput}
                            onChange={(e) => setTextInput(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" && !e.shiftKey) {
                                e.preventDefault();
                                handleTextSubmit();
                              }
                            }}
                            placeholder="Send message to CoComputer"
                            rows={1}
                            className="w-full bg-transparent border-none p-0 text-[15px] text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-0 resize-none overflow-y-auto max-h-40 leading-relaxed placeholder:font-medium"
                          />
                        </div>

                        {/* Action buttons (Bottom) */}
                        <div className="flex items-center justify-between mt-1 px-2 pb-2">
                          {/* Action buttons left */}
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={handleOpenFilePicker}
                              disabled={uploadDisabled}
                              title="Attach"
                              className="p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-full transition-colors flex items-center justify-center border border-zinc-700/50 disabled:opacity-40 disabled:cursor-not-allowed"
                            >
                              <Plus className="w-4 h-4" />
                            </button>
                            
                            <div ref={connectorMenuRef} className="relative">
                              <button
                                type="button"
                                onClick={() => setIsConnectorMenuOpen((open) => !open)}
                                className="p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded transition-colors flex items-center gap-1.5"
                                title="Links"
                              >
                                <Link2 className="w-4 h-4" />
                                {selectedConnectorIds.length > 0 && (
                                  <span className="text-[10px] bg-indigo-500 text-white rounded-full w-4 h-4 flex items-center justify-center font-bold">
                                    {selectedConnectorIds.length}
                                  </span>
                                )}
                              </button>
                              <AnimatePresence>
                                {isConnectorMenuOpen && (
                                  <motion.div 
                                    initial={{ opacity: 0, scale: 0.95, y: 10 }}
                                    animate={{ opacity: 1, scale: 1, y: 0 }}
                                    exit={{ opacity: 0, scale: 0.95, y: 10 }}
                                    className="absolute left-0 bottom-full mb-3 w-80 rounded-2xl border border-zinc-800 bg-[#161618] p-1.5 shadow-2xl z-50 overflow-hidden"
                                  >
                                    {/* Search & Actions Header */}
                                    <div className="p-2 flex flex-col gap-2 border-b border-zinc-800/50 mb-1">
                                      <div className="relative flex items-center">
                                        <Search className="absolute left-2.5 w-3.5 h-3.5 text-zinc-500" />
                                        <input 
                                          autoFocus
                                          type="text"
                                          value={connectorSearch}
                                          onChange={(e) => setConnectorSearch(e.target.value)}
                                          placeholder="Search tools..."
                                          className="w-full bg-zinc-900/50 border border-zinc-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-indigo-500/50 transition-all"
                                        />
                                      </div>
                                      <div className="flex items-center justify-between px-1">
                                        <span className="text-[10px] uppercase tracking-widest font-bold text-zinc-500">Connectors</span>
                                        <button 
                                          onClick={() => {
                                            const filteredIds = availableConnectors
                                              .filter(c => c.name.toLowerCase().includes(connectorSearch.toLowerCase()))
                                              .map(c => c.connection_id);
                                            
                                            if (filteredIds.every(id => selectedConnectorIds.includes(id))) {
                                              setSelectedConnectorIds(prev => prev.filter(id => !filteredIds.includes(id)));
                                            } else {
                                              setSelectedConnectorIds(prev => Array.from(new Set([...prev, ...filteredIds])));
                                            }
                                          }}
                                          className="text-[10px] font-bold text-indigo-400 hover:text-indigo-300 transition-colors"
                                        >
                                          Toggle All
                                        </button>
                                      </div>
                                    </div>

                                    {/* Scrollable List */}
                                    <div className="max-h-64 overflow-y-auto custom-scrollbar space-y-0.5 px-0.5">
                                      {availableConnectors
                                        .filter(c => c.name.toLowerCase().includes(connectorSearch.toLowerCase()))
                                        .map((connector) => {
                                          const checked = selectedConnectorIds.includes(connector.connection_id);
                                          return (
                                            <button
                                              key={connector.connection_id}
                                              type="button"
                                              onClick={() => toggleConnectorSelection(connector.connection_id)}
                                              className={`flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left transition-all ${
                                                checked ? "bg-indigo-500/5" : "hover:bg-zinc-800/60"
                                              }`}
                                            >
                                              <div className="flex items-center gap-3">
                                                <div className={`w-8 h-8 rounded-lg flex items-center justify-center border ${checked ? "border-indigo-500/30 bg-indigo-500/10" : "border-zinc-800 bg-zinc-900/50"}`}>
                                                  <Globe className={`w-4 h-4 ${checked ? "text-indigo-400" : "text-zinc-500"}`} />
                                                </div>
                                                <div className="flex flex-col">
                                                  <div className={`text-[13px] font-medium leading-tight ${checked ? "text-zinc-100" : "text-zinc-300"}`}>
                                                    {connector.name}
                                                  </div>
                                                  <div className="text-[10px] uppercase tracking-wider text-zinc-500 mt-0.5 font-semibold">
                                                    {connector.provider}
                                                  </div>
                                                </div>
                                              </div>
                                              <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all ${
                                                checked ? "border-indigo-500 bg-indigo-500 text-white" : "border-zinc-700 bg-transparent text-transparent"
                                              }`}>
                                                <Check className="w-3 h-3 stroke-[3]" />
                                              </div>
                                            </button>
                                          );
                                        })}
                                      
                                      {availableConnectors.filter(c => c.name.toLowerCase().includes(connectorSearch.toLowerCase())).length === 0 && (
                                        <div className="py-8 text-center text-xs text-zinc-600 font-medium">
                                          No tools found for "{connectorSearch}"
                                        </div>
                                      )}
                                    </div>
                                  </motion.div>
                                )}
                              </AnimatePresence>
                            </div>

                            <button
                              type="button"
                              onClick={handleShowDesktop}
                              title="Workspace Context"
                              className="p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded transition-colors"
                            >
                              <Monitor className="w-4 h-4" />
                            </button>
                          </div>
                          
                          {/* Action buttons right */}
                          <div className="flex items-center gap-2">
                            <button
                              onClick={toggleMic}
                              disabled={voiceStatus !== "connected"}
                              title="Voice Input"
                              className={`p-1.5 rounded transition-colors ${
                                isRecording ? "text-red-400 bg-red-500/10" : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
                              } disabled:opacity-40`}
                            >
                              <Mic className="w-4 h-4" />
                            </button>
                            <button
                              onClick={handleTextSubmit}
                              disabled={!textInput.trim() || isLoading || isUploadingFile}
                              title="Send"
                              className={`p-1.5 rounded-full transition-colors border border-zinc-700/50 ${
                                textInput.trim() && !isLoading && !isUploadingFile
                                  ? 'bg-[#3a3a3c] text-zinc-200 hover:bg-zinc-600' 
                                  : 'bg-zinc-800 text-zinc-500 cursor-not-allowed opacity-50'
                              }`}
                            >
                              <ArrowUp className="w-4 h-4" />
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="px-4 pb-6 pt-2 shrink-0 text-sm text-muted dark:text-zinc-500">
                    <p className="mx-auto w-full max-w-3xl text-center">Archived sessions are read-only.</p>
                  </div>
                )}
              </div>

              {/* Right: Desktop panel */}
              {viewMode === "live" && isDesktopVisible ? (
                <div className="flex-[2] min-w-0 flex overflow-hidden transition-all duration-300 ease-in-out">
                  <div className="flex-1 flex flex-col overflow-hidden p-3 bg-zinc-50 dark:bg-[#151515]">
                    <div className="w-full h-full xl:max-w-7xl mx-auto rounded-xl overflow-hidden border border-zinc-200 dark:border-zinc-800/80 shadow-2xl relative">
                      <WorkflowDesktopContainer
                        workflowRun={workflowRun}
                        streamUrl={streamUrl}
                        analysis={latestAnalysis}
                        forcedTab={forcedTab}
                        onForcedTabAck={() => setForcedTab(null)}
                        phase={phase}
                        agentStatus={agentStatus}
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
    </div>
  );
}
