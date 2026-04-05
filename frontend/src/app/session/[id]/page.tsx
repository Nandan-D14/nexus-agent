"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

import { DemoPicker } from "@/components/demo-picker";
import { DesktopPanel } from "@/components/desktop-panel";
import { ContextPacketPanel } from "@/components/context-packet-panel";
import { MicButton } from "@/components/mic-button";
import { OutputsPanel } from "@/components/outputs-panel";
import { RunLogPanel } from "@/components/run-log-panel";
import { SessionNavSidebar } from "@/components/session-nav-sidebar";
import { WorkflowTemplateEditorModal } from "@/components/workflow-template-editor-modal";
import { UnifiedChatPanel } from "@/components/unified-chat-panel";
import { useLiveDesktop } from "@/components/live-desktop-provider";
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
  WsMessage,
  WorkflowTemplateInputField,
} from "@/lib/message-types";
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
  | { type: "demo"; text: string }
  | { type: "prompt"; text: string }
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
  const [runArtifacts, setRunArtifacts] = useState<RunArtifact[]>([]);
  const [viewMode, setViewMode] = useState<"live" | "archived">("live");
  const [activeSurface, setActiveSurface] = useState<SessionSurface>("conversation");
  const [pageError, setPageError] = useState<string | null>(null);
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [phase, setPhase] = useState<SessionPhase>("idle");
  const [chatItems, setChatItems] = useState<ChatItem[]>([]);
  const [contextMeta, setContextMeta] = useState<ContextPacketMeta | null>(null);
  const [textInput, setTextInput] = useState("");
  const [hasActivatedSession, setHasActivatedSession] = useState(false);
  const [isContinuingThread, setIsContinuingThread] = useState(false);
  const [isDesktopVisible, setIsDesktopVisible] = useState(false);
  const [isDesktopFullscreen, setIsDesktopFullscreen] = useState(false);
  const [pendingText, setPendingText] = useState<string | null>(null);
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
    const el = landingInputRef.current;
    if (!el) return;
    el.style.height = "auto";
    const maxHeight = 200;
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
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
      sendJson({ type: "text_input", text: pendingText });
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
      prompt?: string;
      demo?: string;
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

      if (
        (action.type === "prompt" || action.type === "demo") &&
        !action.text.trim()
      ) {
        return;
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
    async (text: string) => {
      const prompt = text.trim();
      if (!prompt) {
        return;
      }

      await createThreadFromAction({ type: "prompt", text: prompt });
    },
    [createThreadFromAction],
  );

  const sendTextOrQueue = useCallback(
    (text: string) => {
      if (isNewSession) {
        return;
      }
      if (viewMode === "archived") {
        void continueCurrentThread({ prompt: text });
        return;
      }

      setPhase("thinking");

      if (!hasActivatedSession) {
        setHasActivatedSession(true);
        setPendingText(text);
        return;
      }

      if (!isConnected) {
        setPendingText(text);
        return;
      }

      sendJson({ type: "text_input", text });
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

  const handleTextSubmit = useCallback(() => {
    const text = textInput.trim();
    if (!text) return;
    if (isNewSession) {
      void createThreadFromPrompt(text);
      return;
    }
    sendTextOrQueue(text);
    setTextInput("");
  }, [createThreadFromPrompt, isNewSession, sendTextOrQueue, textInput]);

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
      if (isNewSession) {
        void createThreadFromAction({ type: "demo", text });
        return;
      }
      if (viewMode === "archived") {
        void continueCurrentThread({ demo: text });
        return;
      }
      sendTextOrQueue(text);
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

      const action = JSON.parse(raw) as PendingSessionAction;

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
        setHasActivatedSession(true);
        setPendingText(action.text);
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
  const hasConversationStarted =
    chatItems.length > 0 ||
    phase !== "idle" ||
    pendingText !== null ||
    pendingMicStart ||
    viewMode === "archived";
  const hasStarted = hasConversationStarted || isDesktopVisible;

  return (
    <div className="h-screen flex overflow-hidden bg-[#fafafa] dark:bg-[#111114]">
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

              {/* Floating Input Box */}
              <div className="w-full relative group max-w-2xl mx-auto mt-4 px-4">
                <div className="relative flex flex-col bg-[#f4f4f5] dark:bg-[#212126] border border-zinc-200 dark:border-[#2f2f35] rounded-3xl shadow-sm focus-within:ring-1 focus-within:ring-zinc-400 dark:focus-within:ring-zinc-600 transition-all duration-300 p-2">
                  <div className="relative min-h-[60px] flex items-center px-2">
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
                      placeholder="Send message to CoComputer..."
                      rows={1}
                      className="w-full bg-transparent border-none outline-none text-[15px] text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-500 resize-none overflow-y-auto max-h-50 focus:ring-0 leading-relaxed"
                    />
                  </div>
                  <div className="flex items-center justify-between mt-2 px-2">
                    <div className="flex items-center gap-3 text-zinc-400">
                      {/* Paperclip */}
                      <button className="hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-5 h-5">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                        </svg>
                      </button>
                      
                      {/* Model Selector */}
                      <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-full hover:bg-zinc-100 dark:hover:bg-zinc-800/50 transition-colors text-sm font-medium">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
                          <circle cx="12" cy="12" r="10" />
                          <circle cx="12" cy="12" r="2" fill="currentColor" />
                        </svg>
                        Gemini
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3.5 h-3.5">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                        </svg>
                      </button>
                    </div>

                    <div className="flex items-center gap-2 pr-1">
                      <MicButton
                        isRecording={isRecording}
                        onStart={toggleMic}
                        onStop={toggleMic}
                        disabled={voiceStatus !== "connected"}
                      />
                      <button
                        onClick={handleTextSubmit}
                        disabled={!textInput.trim() || isLoading}
                        className={`w-8 h-8 flex items-center justify-center rounded-full transition-all duration-200 ${
                          textInput.trim() && !isLoading
                            ? "bg-zinc-900 text-white dark:bg-white dark:text-black hover:scale-105" 
                            : "bg-zinc-100 text-zinc-400 dark:bg-zinc-800 dark:text-zinc-600"
                        }`}
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3} className="w-4 h-4">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M12 5l7 7-7 7" />
                        </svg>
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
            <header className="relative flex items-center justify-between px-5 py-3">
              <div className="flex items-center gap-4">
                <h1 className="text-base font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
                  CoComputer
                </h1>

                {viewMode === "live" && isConnected && (
                  <span className="flex items-center gap-1.5 text-xs text-zinc-500 dark:text-zinc-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    LIVE
                  </span>
                )}

                {viewMode === "archived" && (
                  <span className="rounded-full bg-zinc-100 dark:bg-[#212126] px-2 py-0.5 text-[11px] font-medium text-zinc-600 dark:text-zinc-400">
                    Archived
                  </span>
                )}

                {viewMode === "live" && activeAgent && activeAgent !== "nexus" && (
                  <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#f4f4f5] dark:bg-[#212126] text-[10px] uppercase tracking-widest font-bold text-zinc-600 dark:text-zinc-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-zinc-400 dark:bg-zinc-500 animate-pulse" />
                    {activeAgent.replace(/_/g, " ")}
                  </div>
                )}
              </div>

              <div className="flex items-center gap-2">
                {!isNewSession && (
                  <button
                    suppressHydrationWarning
                    onClick={handleOpenSaveTemplate}
                    className="text-xs px-3 py-1.5 rounded-lg bg-zinc-100 text-zinc-700 border border-zinc-200 dark:bg-zinc-800 dark:text-zinc-200 dark:border-zinc-700 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-all duration-200"
                  >
                    Save as Template
                  </button>
                )}
                {viewMode === "archived" && (
                  <button
                    suppressHydrationWarning
                    onClick={handleContinueArchivedThread}
                    className="text-xs px-3 py-1.5 rounded-lg bg-cyan-600 text-white border border-cyan-700 hover:bg-cyan-700 transition-all duration-200"
                  >
                    Continue Here
                  </button>
                )}
                {viewMode === "live" && (
                  <button
                    suppressHydrationWarning
                    onClick={handleToggleDesktopFullscreen}
                    className="text-xs px-3 py-1.5 rounded-lg bg-blue-600 text-white border border-blue-700 dark:bg-blue-500 dark:border-blue-400 hover:bg-blue-700 dark:hover:bg-blue-600 transition-all duration-200 flex items-center gap-1.5"
                  >
                    <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
                      {isDesktopFullscreen ? (
                        <path d="M2.75 5A2.25 2.25 0 0 1 5 2.75h2a.75.75 0 0 1 0 1.5H5A.75.75 0 0 0 4.25 5v2a.75.75 0 0 1-1.5 0V5Zm10.25-2.25A.75.75 0 0 1 13.75 2h2A2.25 2.25 0 0 1 18 4.25v2a.75.75 0 0 1-1.5 0v-2a.75.75 0 0 0-.75-.75h-2a.75.75 0 0 1-.75-.75ZM3.5 12.75a.75.75 0 0 1 .75.75v2a.75.75 0 0 0 .75.75h2a.75.75 0 0 1 0 1.5H5a2.25 2.25 0 0 1-2.25-2.25v-2a.75.75 0 0 1 .75-.75Zm13.75 0a.75.75 0 0 1 .75.75v2A2.25 2.25 0 0 1 15.75 18h-2a.75.75 0 0 1 0-1.5h2a.75.75 0 0 0 .75-.75v-2a.75.75 0 0 1 .75-.75Z" />
                      ) : isDesktopVisible ? (
                        <path d="M3.5 2.75A.75.75 0 0 1 4.25 2h3a.75.75 0 0 1 0 1.5H5.53l3.69 3.72a.75.75 0 1 1-1.06 1.06L4.5 4.6v1.65a.75.75 0 0 1-1.5 0v-3.5Zm13 0a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0V4.6l-3.69 3.68A.75.75 0 0 1 11 7.22l3.72-3.72h-1.97a.75.75 0 0 1 0-1.5h3a.75.75 0 0 1 .75.75ZM8.16 11.72a.75.75 0 0 1 1.06 1.06L5.53 16.5h1.72a.75.75 0 0 1 0 1.5h-3A.75.75 0 0 1 3.5 17.25v-3.5a.75.75 0 0 1 1.5 0v1.65l3.16-3.68Zm3.9 1.06a.75.75 0 1 1 1.06-1.06l3.16 3.68v-1.65a.75.75 0 0 1 1.5 0v3.5a.75.75 0 0 1-.75.75h-3a.75.75 0 0 1 0-1.5h1.72l-3.69-3.72Z" />
                      ) : (
                        <path d="M3 4a1 1 0 011-1h12a1 1 0 011 1v8a1 1 0 01-1 1H4a1 1 0 01-1-1V4zm1 0v8h12V4H4zm5.25 1.75a.75.75 0 011.5 0V9h3.25a.75.75 0 010 1.5H10.75v3.25a.75.75 0 01-1.5 0V10.5H6a.75.75 0 010-1.5h3.25V5.75z" />
                      )}
                    </svg>
                    {isDesktopFullscreen
                      ? "Show Chat"
                      : isDesktopVisible
                        ? "Fullscreen Desktop"
                        : "Open Desktop"}
                  </button>
                )}

                {viewMode === "live" && isDesktopVisible && !isDesktopFullscreen && (
                  <button
                    suppressHydrationWarning
                    onClick={handleHideDesktop}
                    className="text-xs px-3 py-1.5 rounded-lg bg-zinc-100 text-zinc-700 border border-zinc-200 dark:bg-zinc-800 dark:text-zinc-200 dark:border-zinc-700 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-all duration-200"
                  >
                    Hide Desktop
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
                  {viewMode === "live" ? "End Session" : "Dashboard"}
                </button>
              </div>
            </header>

            {/* ─── Main content: Desktop + Chat ─── */}
            <div className="flex-1 flex overflow-hidden">
              {/* Left/Middle: Chat Sidebar */}
              <div
                className={`bg-[#fafafa] dark:bg-[#111114] overflow-hidden transition-all duration-300 ease-in-out ${
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

                <div className="shrink-0 border-b border-zinc-200/80 px-4 py-3 dark:border-white/5">
                  <div className="mx-auto flex w-full max-w-4xl items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-2">
                      {([
                        { id: "conversation", label: "Conversation" },
                        { id: "run_log", label: "Run Log" },
                        { id: "outputs", label: "Outputs" },
                        { id: "context", label: "Context" },
                      ] as const).map((surface) => (
                        <button
                          key={surface.id}
                          onClick={() => setActiveSurface(surface.id)}
                          className={`rounded-full px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.16em] transition-colors ${
                            activeSurface === surface.id
                              ? "bg-zinc-900 text-white dark:bg-white dark:text-black"
                              : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
                          }`}
                        >
                          {surface.label}
                        </button>
                      ))}
                    </div>
                    <div className="text-xs text-zinc-500">
                      {runInfo?.status ? `Run ${runInfo.status}` : "Run queued"}
                    </div>
                  </div>
                </div>

                {/* Feed container */}
                <div className="flex-1 overflow-hidden">
                  {activeSurface === "conversation" ? (
                    viewMode === "archived" && chatItems.length === 0 ? (
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
                    )
                  ) : activeSurface === "run_log" ? (
                    <RunLogPanel
                      run={runInfo}
                      steps={runSteps}
                      emptyState={
                        viewMode === "archived"
                          ? "This archived session does not have a stored run log yet."
                          : "Waiting for the first persisted run step."
                      }
                    />
                  ) : activeSurface === "context" ? (
                    <ContextPacketPanel
                      packet={(sessionInfo?.context_packet as ContextPacket | null) ?? null}
                      meta={contextMeta}
                      emptyState={
                        viewMode === "archived"
                          ? "This archived session does not have compact resume memory stored yet."
                          : "Compact context will appear here once the session builds or injects it."
                      }
                    />
                  ) : (
                    <OutputsPanel
                      artifacts={runArtifacts}
                      emptyState={
                        viewMode === "archived"
                          ? "This archived session does not have stored outputs yet."
                          : "Outputs from this run will appear here."
                      }
                    />
                  )}
                </div>

                {/* Input area */}
                {viewMode === "live" ? (
                  <div className="px-4 pb-6 pt-2 shrink-0">
                    <div className="mx-auto w-full max-w-4xl relative">
                      <div className="flex items-center gap-2 bg-[#f4f4f5] dark:bg-[#212126] border border-zinc-200 dark:border-[#2f2f35] rounded-full p-2 shadow-sm transition-all focus-within:ring-1 focus-within:ring-zinc-400 dark:focus-within:ring-zinc-600">
                        {/* Action buttons left */}
                        <div className="flex items-center gap-1 shrink-0">
                          <button className="w-8 h-8 flex items-center justify-center rounded-full text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-300 hover:bg-zinc-200/50 dark:hover:bg-zinc-700/50 transition-colors">
                            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
                              <line x1="12" y1="5" x2="12" y2="19"></line>
                              <line x1="5" y1="12" x2="19" y2="12"></line>
                            </svg>
                          </button>
                          <button className="w-8 h-8 flex items-center justify-center rounded-full text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-300 hover:bg-zinc-200/50 dark:hover:bg-zinc-700/50 transition-colors">
                            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
                              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path>
                              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path>
                            </svg>
                          </button>
                        </div>
                        
                        {/* Text input */}
                        <div className="flex-1 relative min-h-10 flex items-center">
                          <input
                            suppressHydrationWarning
                            ref={inputRef}
                            type="text"
                            value={textInput}
                            onChange={(e) => setTextInput(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && handleTextSubmit()}
                            placeholder="Send message to CoComputer..."
                            className="w-full bg-transparent border-none px-2 py-2.5 text-[15px] text-foreground dark:text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:ring-0"
                          />
                        </div>
                        
                        {/* Action buttons right */}
                        <div className="flex items-center gap-1 shrink-0">
                          <MicButton
                            isRecording={isRecording}
                            onStart={toggleMic}
                            onStop={toggleMic}
                            disabled={voiceStatus !== "connected"}
                          />
                          <button
                            onClick={handleTextSubmit}
                            disabled={!textInput.trim() || isLoading}
                            className={`w-8 h-8 flex items-center justify-center rounded-full transition-colors ${
                              textInput.trim() && !isLoading
                                ? 'bg-zinc-800 dark:bg-zinc-200 text-white dark:text-zinc-900 hover:bg-zinc-700 dark:hover:bg-white' 
                                : 'bg-zinc-200 dark:bg-zinc-800 text-zinc-400 dark:text-zinc-600 cursor-not-allowed'
                            }`}
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
                              <line x1="12" y1="19" x2="12" y2="5"></line>
                              <polyline points="5 12 12 5 19 12"></polyline>
                            </svg>
                          </button>
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
                      <DesktopPanel streamUrl={streamUrl} />
                      
                      {/* ── Overlay: blocks user interaction while agent is working ── */}
                      {(phase === "thinking" || phase === "acting") && (
                        <>
                          <div className="absolute inset-0 z-10 cursor-not-allowed" />
                          <div className="absolute top-4 right-4 z-20 flex items-center gap-3 px-4 py-2.5 rounded-xl bg-white/85 dark:bg-black/85 border border-black/10 dark:border-white/10 backdrop-blur-sm shadow-2xl">
                            <span className="text-xs font-medium text-foreground dark:text-zinc-300 flex items-center gap-2">
                              <span className={`w-2 h-2 rounded-full shrink-0 animate-pulse ${
                                phase === "thinking" ? "bg-cyan-400" : "bg-amber-400"
                              }`} />
                              {agentStatus || (phase === "thinking" ? "Thinking..." : "Acting...")}
                            </span>
                            <div className="w-px h-4 bg-black/10 dark:bg-white/10 mx-1" />
                            <button
                              onClick={handleStopAgent}
                              className="text-xs font-bold text-red-500 hover:text-red-400 uppercase tracking-widest transition-colors"
                            >
                              Stop
                            </button>
                          </div>
                        </>
                      )}
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
