"use client";

import { useParams, useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

import { DemoPicker } from "@/components/demo-picker";
import { DesktopPanel } from "@/components/desktop-panel";
import { MicButton } from "@/components/mic-button";
import { SessionNavSidebar } from "@/components/session-nav-sidebar";
import { StatusBar } from "@/components/status-bar";
import { UnifiedChatPanel } from "@/components/unified-chat-panel";
import { useLiveDesktop } from "@/components/live-desktop-provider";
import { useAuth } from "@/lib/auth-context";
import { AudioPlayer } from "@/lib/audio-playback";
import { listArchivedMessages } from "@/lib/firestore-history";
import type {
  SessionData,
  SessionInfo,
  SessionPhase,
  WsMessage,
} from "@/lib/message-types";
import { useMicrophone } from "@/lib/use-microphone";
import { useSession } from "@/lib/use-session";
import { useWebSocket } from "@/lib/use-websocket";

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

/* ------------------------------------------------------------------ */
/*  Page component                                                     */
/* ------------------------------------------------------------------ */

export default function SessionPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.id as string;
  const { user, isLoading: authLoading } = useAuth();
  const {
    createSession,
    getSession,
    refreshTicket,
    destroySession,
    isLoading,
    error,
  } = useSession();
  const isNewSession = sessionId === "new";

  const [sessionInfo, setSessionInfo] = useState<SessionInfo | null>(null);
  const [sessionData, setSessionData] = useState<SessionData | null>(null);
  const [viewMode, setViewMode] = useState<"live" | "archived">("live");
  const [pageError, setPageError] = useState<string | null>(null);
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [phase, setPhase] = useState<SessionPhase>("idle");
  const [chatItems, setChatItems] = useState<ChatItem[]>([]);
  const [textInput, setTextInput] = useState("");
  const [hasActivatedSession, setHasActivatedSession] = useState(false);
  const [isDesktopVisible, setIsDesktopVisible] = useState(false);
  const [pendingText, setPendingText] = useState<string | null>(null);
  const [pendingMicStart, setPendingMicStart] = useState(false);
  const [activeAgent, setActiveAgent] = useState<string>("nexus");
  const [agentStatus, setAgentStatus] = useState("");
  const [voiceStatus, setVoiceStatus] = useState<
    "available" | "unavailable" | "connecting" | "connected" | "reconnecting" | "disconnected"
  >("disconnected");
  const [tokenQuota, setTokenQuota] = useState<{
    limit: number;
    used: number;
    remaining: number;
  } | null>(null);

  const audioPlayer = useRef(new AudioPlayer());
  const inputRef = useRef<HTMLInputElement>(null);
  const landingInputRef = useRef<HTMLTextAreaElement>(null);
  const streamUrlRef = useRef<string | null>(null);
  const viewModeRef = useRef<"live" | "archived">("live");
  const autoActionHandledRef = useRef(false);
  const pendingActionKeyRef = useRef(`nexus.pendingSessionAction:${sessionId}`);
  const { registerDesktop, clearDesktop, minimizeDesktop } = useLiveDesktop();
  const minimizeDesktopRef = useRef(minimizeDesktop);
  const greetingName =
    user?.displayName?.trim() ||
    user?.email?.split("@")[0]?.trim() ||
    "there";

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

  const { start: startMic, stop: stopMic, isRecording } =
    useMicrophone(sendBinary);

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

      case "error":
        setPageError(msg.message);
        setAgentStatus("");
        setChatItems((prev) => [
          ...prev,
          { kind: "event", type: msg.type, code: msg.code, message: msg.message, ts },
        ]);
        break;

      case "quota_update":
        setTokenQuota({
          limit: msg.limit,
          used: msg.used,
          remaining: msg.remaining,
        });
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
      setStreamUrl(null);
      setSessionData(null);
      setSessionInfo(null);
      setVoiceStatus("connected");
      setHasActivatedSession(false);
      setIsDesktopVisible(false);
      setPendingText(null);
      setPendingMicStart(false);
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

      if (!info.is_live) {
        clearDesktop(sessionId);
        try {
          const archivedMessages = await listArchivedMessages(sessionId);
          if (!cancelled) {
            setViewMode("archived");
            setChatItems(
              archivedMessages.map((message) => ({
                kind: "message" as const,
                role: message.role,
                text: message.text,
                ts: message.created_at
                  ? new Date(message.created_at).getTime()
                  : Date.now(),
              })),
            );
            setPhase("done");
          }
        } catch (err) {
          if (!cancelled) {
            setPageError(
              err instanceof Error
                ? err.message
                : "Failed to load archived messages",
            );
          }
        }
        return;
      }

      const wsTicket = await refreshTicket(sessionId);
      if (cancelled) {
        return;
      }

      if (!wsTicket) {
        clearDesktop(sessionId);
        try {
          const archivedMessages = await listArchivedMessages(sessionId);
          if (!cancelled) {
            setViewMode("archived");
            setChatItems(
              archivedMessages.map((message) => ({
                kind: "message" as const,
                role: message.role,
                text: message.text,
                ts: message.created_at
                  ? new Date(message.created_at).getTime()
                  : Date.now(),
              })),
            );
            setPhase("done");
          }
        } catch (err) {
          if (!cancelled) {
            setPageError(
              err instanceof Error
                ? err.message
                : "Failed to load archived messages",
            );
          }
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

  const startSession = useCallback(
    async (options?: {
      prompt?: string;
      demo?: string;
      openDesktop?: boolean;
      startMic?: boolean;
    }) => {
      if (authLoading) return;
      if (!user) {
        router.push("/");
        return;
      }

      setPageError(null);
      const session = await createSession();
      if (!session) {
        setPageError("Failed to create session.");
        return;
      }

      try {
        const key = `nexus.pendingSessionAction:${session.session_id}`;
        if (options?.demo) {
          sessionStorage.setItem(
            key,
            JSON.stringify({ type: "demo", text: options.demo }),
          );
        } else if (options?.prompt) {
          sessionStorage.setItem(
            key,
            JSON.stringify({ type: "prompt", text: options.prompt }),
          );
        } else if (options?.openDesktop) {
          sessionStorage.setItem(key, JSON.stringify({ type: "openDesktop" }));
        } else if (options?.startMic) {
          sessionStorage.setItem(key, JSON.stringify({ type: "startMic" }));
        }
      } catch {
        // If storage is unavailable, fall back to plain navigation.
      }

      router.push(`/session/${session.session_id}`);
    },
    [authLoading, createSession, router, user],
  );

  const sendTextOrQueue = useCallback(
    (text: string) => {
      if (viewMode !== "live") return;
      if (isNewSession) {
        void startSession({ prompt: text });
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
    [hasActivatedSession, isConnected, isNewSession, sendJson, startSession, viewMode],
  );

  /* ---- Actions ---- */
  const toggleMic = useCallback(() => {
    if (viewMode !== "live") return;
    if (isNewSession) {
      void startSession({ startMic: true });
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
    hasActivatedSession,
    isConnected,
    isNewSession,
    isRecording,
    sendJson,
    startMic,
    startSession,
    stopMic,
    viewMode,
    voiceStatus,
  ]);

  const handleTextSubmit = useCallback(() => {
    if (viewMode !== "live") return;
    const text = textInput.trim();
    if (!text) return;
    if (isNewSession) {
      void startSession({ prompt: text });
      setTextInput("");
      return;
    }
    sendTextOrQueue(text);
    setTextInput("");
  }, [isNewSession, sendTextOrQueue, startSession, textInput, viewMode]);

  const handleShowDesktop = useCallback(() => {
    if (viewMode !== "live") return;
    if (isNewSession) {
      void startSession({ openDesktop: true });
      return;
    }
    setIsDesktopVisible(true);
    if (!hasActivatedSession) {
      setHasActivatedSession(true);
    }
  }, [hasActivatedSession, isNewSession, startSession, viewMode]);

  const handleHideDesktop = useCallback(() => {
    setIsDesktopVisible(false);
  }, []);

  const handleDemo = useCallback(
    (text: string) => {
      if (viewMode !== "live") return;
      if (isNewSession) {
        void startSession({ demo: text });
        return;
      }
      sendTextOrQueue(text);
    },
    [isNewSession, sendTextOrQueue, startSession, viewMode],
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
    if (isNewSession || viewMode !== "live") {
      return;
    }
    if (autoActionHandledRef.current) {
      return;
    }

    let timer: ReturnType<typeof setTimeout> | null = null;
    try {
      const key = pendingActionKeyRef.current;
      const raw = sessionStorage.getItem(key);
      if (!raw) {
        return;
      }
      sessionStorage.removeItem(key);

      const action = JSON.parse(raw) as
        | { type: "demo"; text: string }
        | { type: "prompt"; text: string }
        | { type: "openDesktop" }
        | { type: "startMic" };

      autoActionHandledRef.current = true;

      if (action.type === "openDesktop") {
        handleShowDesktop();
      } else if (action.type === "startMic") {
        if (!hasActivatedSession) {
          setHasActivatedSession(true);
        }
        setPendingMicStart(true);
        setPhase("listening");
      } else if (action.type === "demo") {
        timer = setTimeout(() => {
          handleDemo(action.text);
        }, 400);
      } else if (action.type === "prompt") {
        timer = setTimeout(() => {
          sendTextOrQueue(action.text);
        }, 400);
      }
    } catch {
      // Ignore invalid storage payloads.
    }

    return () => {
      if (timer) {
        clearTimeout(timer);
      }
    };
  }, [
    handleDemo,
    handleShowDesktop,
    hasActivatedSession,
    isNewSession,
    sendTextOrQueue,
    viewMode,
  ]);

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
                  className="text-xs px-3 py-1.5 rounded-lg border border-card-border dark:border-[#1c1c1e] text-muted dark:text-zinc-400 hover:bg-black/5 dark:hover:bg-zinc-800/50 hover:text-foreground dark:hover:text-white transition-all duration-200"
                >
                  Open Desktop
                </button>
              )}
              <button
                suppressHydrationWarning
                onClick={() => router.push("/settings/profile")}
                className="text-xs px-3 py-1.5 rounded-lg border border-card-border dark:border-[#1c1c1e] text-muted dark:text-zinc-400 hover:bg-black/5 dark:hover:bg-zinc-800/50 hover:text-foreground dark:hover:text-white transition-all duration-200"
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
                  Welcome to Nexus
                </h1>
                <p className="text-[15px] text-zinc-500">
                  What can I help you with?
                </p>
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
                      placeholder="Send message to Nexus..."
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
                        disabled={!textInput.trim()}
                        className={`w-8 h-8 flex items-center justify-center rounded-full transition-all duration-200 ${
                          textInput.trim() 
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
                  Nexus
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
                {viewMode === "live" && (
                  <button
                    suppressHydrationWarning
                    onClick={isDesktopVisible ? handleHideDesktop : handleShowDesktop}
                    className="text-xs px-3 py-1.5 rounded-lg border border-card-border dark:border-[#1c1c1e] text-muted dark:text-zinc-400 hover:bg-black/5 dark:hover:bg-zinc-800/50 hover:text-foreground dark:hover:text-white transition-all duration-200 flex items-center gap-1.5"
                  >
                    <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
                      {isDesktopVisible ? (
                        <path d="M3 4a1 1 0 011-1h12a1 1 0 011 1v8a1 1 0 01-1 1H4a1 1 0 01-1-1V4zm1 0v8h12V4H4zm2.25 2.75a.75.75 0 011.06 0L10 9.44l2.69-2.69a.75.75 0 111.06 1.06L11.06 10.5l2.69 2.69a.75.75 0 11-1.06 1.06L10 11.56l-2.69 2.69a.75.75 0 11-1.06-1.06l2.69-2.69-2.69-2.69a.75.75 0 010-1.06z" />
                      ) : (
                        <path d="M3 4a1 1 0 011-1h12a1 1 0 011 1v8a1 1 0 01-1 1H4a1 1 0 01-1-1V4zm1 0v8h12V4H4zm5.25 1.75a.75.75 0 011.5 0V9h3.25a.75.75 0 010 1.5H10.75v3.25a.75.75 0 01-1.5 0V10.5H6a.75.75 0 010-1.5h3.25V5.75z" />
                      )}
                    </svg>
                    {isDesktopVisible ? "Hide Desktop" : "Open Desktop"}
                  </button>
                )}

                <button
                  suppressHydrationWarning
                  onClick={() => router.push("/settings/profile")}
                  className="text-xs px-3 py-1.5 rounded-lg border border-card-border dark:border-[#1c1c1e] text-muted dark:text-zinc-400 hover:bg-black/5 dark:hover:bg-zinc-800/50 hover:text-foreground dark:hover:text-white transition-all duration-200"
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
                className={`flex flex-col bg-[#fafafa] dark:bg-[#111114] overflow-hidden transition-all duration-300 ease-in-out ${
                  isDesktopVisible
                    ? "w-105 min-w-95 border-r border-zinc-200 dark:border-white/5"
                    : "flex-1 min-w-0"
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

                {/* Feed container */}
                <div className="flex-1 overflow-hidden">
                  {viewMode === "archived" && chatItems.length === 0 ? (
                    <div className="flex h-full flex-col items-center justify-center p-8 text-center bg-transparent">
                      <p className="text-lg font-medium text-zinc-900 dark:text-zinc-100">
                        Archived session
                      </p>
                      <p className="mt-2 max-w-md text-sm text-zinc-500 dark:text-zinc-500">
                        The live desktop is no longer attached. You can review the saved transcript below.
                      </p>
                      {sessionInfo?.summary && (
                        <p className="mt-6 max-w-lg rounded-2xl bg-[#f4f4f5] dark:bg-[#1a1a1c] px-5 py-4 text-[15px] leading-relaxed text-zinc-700 dark:text-zinc-300">
                          {sessionInfo.summary}
                        </p>
                      )}
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
                    <div className="mx-auto w-full max-w-3xl relative">
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
                            placeholder="Send message to Nexus..."
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
                            disabled={!textInput.trim()}
                            className={`w-8 h-8 flex items-center justify-center rounded-full transition-colors ${
                              textInput.trim() 
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
                <div className="flex-1 min-w-0 flex overflow-hidden transition-all duration-300 ease-in-out">
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
            <StatusBar phase={phase} isConnected={viewMode === "live" && isConnected} tokenQuota={tokenQuota} />

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
          </>
        )}
      </div>
    </div>
  );
}
