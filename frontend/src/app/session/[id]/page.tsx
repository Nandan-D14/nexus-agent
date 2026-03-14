"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { DemoPicker } from "@/components/demo-picker";
import { DesktopPanel } from "@/components/desktop-panel";
import { DesktopSidebar } from "@/components/desktop-sidebar";
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
  const searchParams = useSearchParams();
  const router = useRouter();
  const sessionId = params.id as string;
  const { user, isLoading: authLoading } = useAuth();
  const { getSession, refreshTicket, destroySession, isLoading, error } =
    useSession();

  const [sessionInfo, setSessionInfo] = useState<SessionInfo | null>(null);
  const [sessionData, setSessionData] = useState<SessionData | null>(null);
  const [viewMode, setViewMode] = useState<"live" | "archived">("live");
  const [pageError, setPageError] = useState<string | null>(null);
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [phase, setPhase] = useState<SessionPhase>("idle");
  const [chatItems, setChatItems] = useState<ChatItem[]>([]);
  const [textInput, setTextInput] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [activeAgent, setActiveAgent] = useState<string>("nexus");
  const [agentStatus, setAgentStatus] = useState("");
  const [voiceStatus, setVoiceStatus] = useState<
    "connected" | "reconnecting" | "disconnected"
  >("connected");

  const audioPlayer = useRef(new AudioPlayer());
  const inputRef = useRef<HTMLInputElement>(null);
  const {
    activeDesktop,
    isMinimized,
    registerDesktop,
    minimizeDesktop,
    restoreDesktop,
    clearDesktop,
  } = useLiveDesktop();

  const isCurrentSessionMinimized =
    activeDesktop?.sessionId === sessionId && isMinimized;
  const desktopVisible = viewMode === "live" && !isCurrentSessionMinimized;

  const wsUrl =
    typeof window !== "undefined"
      ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${process.env.NEXT_PUBLIC_AGENT_WS_URL?.replace(/^wss?:\/\//, "") || "localhost:8000"}/ws/${sessionId}?ticket=${sessionData?.ws_ticket || ""}`
      : null;

  const { sendBinary, sendJson, lastMessage, isConnected, onBinaryMessageRef } =
    useWebSocket(viewMode === "live" && sessionData?.ws_ticket ? wsUrl : null);

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
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

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

      case "pong":
        break;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!lastMessage) return;
    handleLastMessage(lastMessage);
  }, [lastMessage, handleLastMessage]);

  useEffect(() => {
    if (viewMode !== "live" || !streamUrl) {
      return;
    }

    registerDesktop({ sessionId, streamUrl });
  }, [registerDesktop, sessionId, streamUrl, viewMode]);

  useEffect(() => {
    const player = audioPlayer.current;

    return () => {
      player.stop();
      stopMic();
    };
  }, [stopMic]);

  useEffect(() => {
    if (voiceStatus !== "connected" && isRecording) {
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
          stream_url: info.stream_url || "",
          ws_ticket: wsTicket,
          status: info.status,
          created_at: info.created_at,
        });
        setStreamUrl(info.stream_url);
        registerDesktop({
          sessionId: info.session_id,
          streamUrl: info.stream_url || "",
        });
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
    refreshTicket,
    registerDesktop,
    router,
    sessionId,
    user,
  ]);

  /* ---- Actions ---- */
  const toggleMic = useCallback(() => {
    if (viewMode !== "live") return;
    if (voiceStatus !== "connected") return;
    if (isRecording) {
      stopMic();
      setPhase("thinking");
    } else {
      startMic();
      setPhase("listening");
    }
  }, [isRecording, startMic, stopMic, viewMode, voiceStatus]);

  const handleTextSubmit = useCallback(() => {
    if (viewMode !== "live") return;
    const text = textInput.trim();
    if (!text) return;
    sendJson({ type: "text_input", text });
    setTextInput("");
    setPhase("thinking");
  }, [sendJson, textInput, viewMode]);

  const handleDemo = useCallback(
    (text: string) => {
      if (viewMode !== "live") return;
      sendJson({ type: "text_input", text });
      setPhase("thinking");
    },
    [sendJson, viewMode],
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
    const demo = searchParams.get("demo");
    if (demo && isConnected && viewMode === "live") {
      const timer = setTimeout(() => handleDemo(demo), 1500);
      return () => clearTimeout(timer);
    }
  }, [handleDemo, isConnected, searchParams, viewMode]);

  const handleEnd = async () => {
    audioPlayer.current.stop();
    stopMic();
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
  return (
    <div className="h-screen flex overflow-hidden bg-background dark:bg-[#09090b]">
      {/* ─── Left nav sidebar ─── */}
      <SessionNavSidebar />

      {/* ─── Main panel ─── */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
      {/* ─── Header ─── */}
      <header className="relative flex items-center justify-between px-5 py-2.5 border-b border-card-border dark:border-[#1c1c1e] bg-card dark:bg-[#09090b]">
        {/* Gradient accent line under header */}
        <div className="absolute bottom-0 left-0 right-0 h-px bg-linear-to-r from-transparent via-cyan-500/30 to-transparent" />

        <div className="flex items-center gap-4">
          <h1 className="text-lg font-bold tracking-tight">
            <span className="text-[#22d3ee]">NEXUS</span>
          </h1>

          {viewMode === "live" && isConnected && (
            <span className="flex items-center gap-1.5 text-xs text-emerald-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              LIVE
            </span>
          )}

          {viewMode === "archived" && (
            <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[11px] uppercase tracking-wider text-amber-300">
              Archived
            </span>
          )}

          {/* Active agent badge */}
          {viewMode === "live" && activeAgent && activeAgent !== "nexus" && (
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 text-[10px] uppercase tracking-widest font-bold text-zinc-600 dark:text-zinc-400">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-500 animate-pulse" />
              {activeAgent.replace(/_/g, " ")}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Hide/Show Desktop toggle */}
          {viewMode === "live" && (
            <button
              suppressHydrationWarning
              onClick={() => {
                if (isCurrentSessionMinimized) {
                  restoreDesktop();
                  return;
                }

                minimizeDesktop({
                  sessionId,
                  streamUrl: streamUrl ?? sessionInfo?.stream_url ?? "",
                });
              }}
              className="text-xs px-3 py-1.5 rounded-lg border border-card-border dark:border-[#1c1c1e] text-muted dark:text-zinc-400 hover:bg-black/5 dark:hover:bg-zinc-800/50 hover:text-foreground dark:hover:text-white transition-all duration-200 flex items-center gap-1.5"
              title={
                isCurrentSessionMinimized
                  ? "Return the desktop to the main view"
                  : "Minimize the desktop into a floating player"
              }
            >
              <svg
                viewBox="0 0 20 20"
                fill="currentColor"
                className="w-3.5 h-3.5"
              >
                {isCurrentSessionMinimized ? (
                  <path d="M3 4a1 1 0 011-1h12a1 1 0 011 1v8a1 1 0 01-1 1H4a1 1 0 01-1-1V4zm1 0v8h12V4H4zm4.25 12a.75.75 0 010-1.5h3.5a.75.75 0 010 1.5h-3.5z" />
                ) : (
                  <path d="M3 4a1 1 0 011-1h12a1 1 0 011 1v8a1 1 0 01-1 1H4a1 1 0 01-1-1V4zm1 0v8h12V4H4zm-1 11a1 1 0 011-1h12a1 1 0 010 2H4a1 1 0 01-1-1z" />
                )}
              </svg>
              {isCurrentSessionMinimized
                ? "Restore Desktop"
                : "Minimize Desktop"}
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
        {/* Left: Desktop panel (collapsible) */}
        <div
          className={`flex overflow-hidden transition-all duration-300 ease-in-out ${
            desktopVisible
              ? "flex-1 min-w-0"
              : "w-0 min-w-0 p-0 opacity-0"
          }`}
        >
          {viewMode === "live" ? (
            <>
              <DesktopSidebar
                open={sidebarOpen}
                onToggle={() => setSidebarOpen((v) => !v)}
                phase={phase}
                activeAgent={activeAgent}
                isConnected={isConnected}
                onAnalyzeScreen={() => sendJson({ type: "analyze_screen" })}
              />
              <div className="flex-1 overflow-hidden p-2 relative">
                <DesktopPanel streamUrl={streamUrl} />

                {/* ── Overlay: blocks user interaction while agent is working ── */}
                {(phase === "thinking" || phase === "acting") && (
                  <>
                    {/* Transparent click-blocker over the whole desktop */}
                    <div className="absolute inset-0 z-10 cursor-not-allowed" />

                    {/* Bottom action bar */}
                    <div className="absolute bottom-2 left-2 right-2 z-20 flex items-center gap-3 px-4 py-2.5 rounded-xl bg-white/85 dark:bg-black/85 border border-black/10 dark:border-white/10 backdrop-blur-sm shadow-2xl">
                      {/* Stop button */}
                      <button
                        onClick={handleStopAgent}
                        title="Stop"
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/15 border border-red-500/30 text-red-400 hover:bg-red-500/25 transition-colors text-xs font-bold uppercase tracking-wider"
                      >
                        <svg viewBox="0 0 16 16" fill="currentColor" className="w-3 h-3">
                          <rect x="3" y="3" width="10" height="10" rx="1.5" />
                        </svg>
                        Stop
                      </button>

                      {/* Divider */}
                      <div className="w-px h-5 bg-black/10 dark:bg-white/10" />

                      {/* Live status */}
                      <div className="flex items-center gap-2 flex-1 min-w-0">
                        <span className={`w-2 h-2 rounded-full shrink-0 animate-pulse ${
                          phase === "thinking" ? "bg-cyan-400" : "bg-amber-400"
                        }`} />
                        <span className="text-xs text-foreground dark:text-zinc-300 truncate">
                          {agentStatus || (phase === "thinking" ? "Thinking..." : "Acting...")}
                        </span>
                      </div>

                      {/* Active agent badge */}
                      {activeAgent && activeAgent !== "nexus" && (
                        <span className="text-[9px] text-zinc-500 font-bold uppercase tracking-widest shrink-0">
                          {activeAgent.replace(/_/g, " ")}
                        </span>
                      )}
                    </div>
                  </>
                )}
              </div>
            </>
          ) : null}
        </div>

        {/* Right: Unified Chat Panel */}
        <div
          className={`flex flex-col border-l border-card-border dark:border-[#1c1c1e] bg-card dark:bg-[#0a0a0c] overflow-hidden transition-all duration-300 ease-in-out ${
            desktopVisible
              ? "w-105 min-w-95"
              : "flex-1"
          }`}
        >
          {/* Chat header */}
          <div className="px-4 py-2.5 border-b border-card-border dark:border-[#1c1c1e] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-black text-muted dark:text-zinc-400 uppercase tracking-[0.15em]">
                Chat
              </span>
              {phase === "thinking" && (
                <span className="text-[9px] text-cyan-500 font-bold uppercase tracking-widest animate-pulse">
                  Thinking...
                </span>
              )}
              {phase === "acting" && (
                <span className="text-[9px] text-amber-500 font-bold uppercase tracking-widest animate-pulse">
                  Acting...
                </span>
              )}
            </div>

            {/* Stop button — visible while agent is running */}
            {viewMode === "live" && (phase === "thinking" || phase === "acting") && (
              <button
                suppressHydrationWarning
                onClick={handleStopAgent}
                title="Stop agent"
                className="flex items-center gap-1.5 px-2 py-1 rounded-md border border-red-500/30 bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors text-[10px] font-bold uppercase tracking-widest"
              >
                <span className="w-2 h-2 rounded-sm bg-red-400 shrink-0" />
                Stop
              </button>
            )}
          </div>

          {/* Feed container */}
          <div className="flex-1 overflow-hidden">
            {viewMode === "archived" && chatItems.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center p-8 text-center">
                <p className="text-lg font-semibold text-foreground dark:text-zinc-100">
                  Archived session
                </p>
                <p className="mt-2 max-w-md text-sm text-muted dark:text-zinc-500">
                  The live desktop is no longer attached. You can review the
                  saved transcript below.
                </p>
                {sessionInfo?.summary && (
                  <p className="mt-4 max-w-lg rounded-xl border border-card-border dark:border-[#1c1c1e] bg-background dark:bg-[#09090b] px-4 py-3 text-sm text-foreground dark:text-zinc-300">
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

          {/* Demo picker */}
          {viewMode === "live" &&
            chatItems.length === 0 &&
            isConnected && (
              <div className="px-4 pb-2">
                <DemoPicker onSelect={handleDemo} disabled={!isConnected} />
              </div>
            )}

          {/* Input area */}
          {viewMode === "live" ? (
            <div className="px-4 py-3 border-t border-card-border dark:border-[#1c1c1e] bg-card dark:bg-[#09090b]">
              <div className="flex items-center gap-2">
                <div className="flex-1 relative">
                  <input
                    suppressHydrationWarning
                    ref={inputRef}
                    type="text"
                    value={textInput}
                    onChange={(e) => setTextInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleTextSubmit()}
                    placeholder="Type a command... ( / to focus)"
                    className="w-full bg-background dark:bg-[#111114] border border-card-border dark:border-[#1c1c1e] rounded-full px-4 py-2.5 text-sm text-foreground dark:text-white placeholder:text-muted dark:placeholder:text-zinc-600 focus:outline-none focus:border-cyan-500/40 focus:shadow-[0_0_12px_rgba(34,211,238,0.08)] transition-all duration-200"
                  />
                  {textInput.trim() && (
                    <button
                      onClick={handleTextSubmit}
                      className="absolute right-2 top-1/2 -translate-y-1/2 w-7 h-7 flex items-center justify-center rounded-full bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 transition-colors"
                    >
                      <svg
                        viewBox="0 0 20 20"
                        fill="currentColor"
                        className="w-3.5 h-3.5"
                      >
                        <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" />
                      </svg>
                    </button>
                  )}
                </div>
                <MicButton
                  isRecording={isRecording}
                  onStart={toggleMic}
                  onStop={toggleMic}
                  disabled={!isConnected || voiceStatus !== "connected"}
                />
              </div>
            </div>
          ) : (
            <div className="border-t border-card-border dark:border-[#1c1c1e] px-4 py-3 text-sm text-muted dark:text-zinc-500">
              Archived sessions are read-only. Start a new session from the home
              page to launch a fresh live desktop.
            </div>
          )}
        </div>
      </div>

      {/* ─── Footer ─── */}
      <StatusBar phase={phase} isConnected={viewMode === "live" && isConnected} />

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
      </div>{/* end main panel */}
    </div>
  );
}
