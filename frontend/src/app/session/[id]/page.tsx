"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { ActivityFeed } from "@/components/activity-feed";
import { ConversationPanel } from "@/components/conversation-panel";
import { DemoPicker } from "@/components/demo-picker";
import { DesktopPanel } from "@/components/desktop-panel";
import { MicButton } from "@/components/mic-button";
import { StatusBar } from "@/components/status-bar";
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

type Message = { role: "user" | "agent"; text: string };
type ActivityEvent = { type: string; timestamp: number; [key: string]: unknown };

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
  const [messages, setMessages] = useState<Message[]>([]);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [textInput, setTextInput] = useState("");

  const audioPlayer = useRef(new AudioPlayer());

  const wsUrl =
    typeof window !== "undefined"
      ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${process.env.NEXT_PUBLIC_AGENT_WS_URL?.replace(/^wss?:\/\//, "") || "localhost:8000"}/ws/${sessionId}?ticket=${sessionData?.ws_ticket || ""}`
      : null;

  const { sendBinary, sendJson, lastMessage, isConnected, onBinaryMessageRef } =
    useWebSocket(viewMode === "live" && sessionData?.ws_ticket ? wsUrl : null);

  const { start: startMic, stop: stopMic, isRecording } =
    useMicrophone(sendBinary);

  useEffect(() => {
    onBinaryMessageRef.current = (data: ArrayBuffer) => {
      audioPlayer.current.play(data);
    };
  }, [onBinaryMessageRef]);

  const handleLastMessage = useCallback((msg: WsMessage) => {
    const addEvent = (message: WsMessage) => {
      setEvents((prev) => [...prev, { ...message, timestamp: Date.now() }]);
    };

    switch (msg.type) {
      case "sandbox_status":
        addEvent(msg);
        break;
      case "vnc_url":
        setStreamUrl(msg.url);
        break;
      case "transcript":
        setMessages((prev) => [...prev, { role: msg.role, text: msg.text }]);
        if (msg.role === "agent") setPhase("done");
        break;
      case "agent_thinking":
        setPhase("thinking");
        addEvent(msg);
        break;
      case "agent_tool_call":
        setPhase("acting");
        addEvent(msg);
        break;
      case "agent_tool_result":
        addEvent(msg);
        break;
      case "agent_screenshot":
        addEvent(msg);
        break;
      case "agent_complete":
        setPhase("done");
        addEvent(msg);
        break;
      case "error":
        setPageError(msg.message);
        addEvent(msg);
        break;
      case "pong":
        break;
    }
  // State setters from useState are stable references — no deps needed.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!lastMessage) return;
    handleLastMessage(lastMessage);
  }, [lastMessage, handleLastMessage]);

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
      setEvents([]);
      setMessages([]);
      setStreamUrl(null);
      setSessionData(null);
      setSessionInfo(null);

      const info = await getSession(sessionId);
      if (cancelled) return;
      if (!info) {
        setPageError("Session not found");
        return;
      }

      setSessionInfo(info);

      if (!info.is_live) {
        try {
          const archivedMessages = await listArchivedMessages(sessionId);
          if (!cancelled) {
            setViewMode("archived");
            setMessages(
              archivedMessages.map((message) => ({
                role: message.role,
                text: message.text,
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
      if (!wsTicket || cancelled) {
        try {
          const archivedMessages = await listArchivedMessages(sessionId);
          if (!cancelled) {
            setViewMode("archived");
            setMessages(
              archivedMessages.map((message) => ({
                role: message.role,
                text: message.text,
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
      }
    }

    void loadSessionState();

    return () => {
      cancelled = true;
    };
  }, [authLoading, getSession, refreshTicket, router, sessionId, user]);

  const toggleMic = useCallback(() => {
    if (viewMode !== "live") return;
    if (isRecording) {
      stopMic();
      setPhase("thinking");
    } else {
      startMic();
      setPhase("listening");
    }
  }, [isRecording, startMic, stopMic, viewMode]);

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
      } catch (err) {
        console.error("[handleEnd] Failed to destroy session:", err);
      }
    }
    router.push("/");
  };

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <header className="flex items-center justify-between px-4 py-2 border-b border-[#27272a] bg-[#18181b]">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold tracking-tight">
            <span className="text-[#22d3ee]">NEXUS</span>
          </h1>
          {viewMode === "live" && isConnected && (
            <span className="flex items-center gap-1.5 text-xs text-emerald-400">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              LIVE
            </span>
          )}
          {viewMode === "archived" && (
            <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[11px] uppercase tracking-wider text-amber-300">
              Archived
            </span>
          )}
        </div>
        <button
          onClick={handleEnd}
          className="text-xs px-3 py-1.5 rounded-lg border border-red-500/30 text-red-400 hover:bg-red-500/10 transition"
        >
          {viewMode === "live" ? "End Session" : "Back Home"}
        </button>
      </header>

      <div className="flex-1 flex overflow-hidden">
        <div className="w-72 border-r border-[#27272a] flex flex-col overflow-hidden">
          <div className="px-3 py-2 border-b border-[#27272a] text-xs font-medium text-zinc-400 uppercase tracking-wider">
            Activity
          </div>
          <div className="flex-1 overflow-y-auto">
            <ActivityFeed
              events={events}
              emptyState={
                viewMode === "archived"
                  ? "This session is archived. Live activity is unavailable."
                  : "Waiting for agent activity..."
              }
            />
          </div>
        </div>

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex-1 p-2 overflow-hidden">
            {viewMode === "live" ? (
              <DesktopPanel streamUrl={streamUrl} />
            ) : (
              <div className="flex h-full flex-col items-center justify-center rounded-lg border border-[#27272a] bg-[#18181b] p-8 text-center">
                <p className="text-lg font-semibold text-zinc-100">
                  Archived session
                </p>
                <p className="mt-2 max-w-md text-sm text-zinc-500">
                  The live desktop is no longer attached. You can still review
                  the saved transcript stored in Firestore.
                </p>
                {sessionInfo?.summary && (
                  <p className="mt-4 max-w-lg rounded-xl border border-[#27272a] bg-[#111113] px-4 py-3 text-sm text-zinc-300">
                    {sessionInfo.summary}
                  </p>
                )}
              </div>
            )}
          </div>

          {viewMode === "live" && events.length === 0 && isConnected && (
            <div className="px-4 pb-2">
              <DemoPicker onSelect={handleDemo} disabled={!isConnected} />
            </div>
          )}

          {viewMode === "live" ? (
            <div className="px-4 py-2 border-t border-[#27272a] flex items-center gap-2">
              <input
                type="text"
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleTextSubmit()}
                placeholder="Type a command..."
                className="flex-1 bg-[#18181b] border border-[#27272a] rounded-lg px-3 py-2 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-[#22d3ee]/50"
              />
              <MicButton
                isRecording={isRecording}
                onStart={toggleMic}
                onStop={toggleMic}
                disabled={!isConnected}
              />
            </div>
          ) : (
            <div className="border-t border-[#27272a] px-4 py-3 text-sm text-zinc-500">
              Archived sessions are read-only. Start a new session from the home
              page to launch a fresh live desktop.
            </div>
          )}
        </div>

        <div className="w-80 border-l border-[#27272a] flex flex-col overflow-hidden">
          <div className="px-3 py-2 border-b border-[#27272a] text-xs font-medium text-zinc-400 uppercase tracking-wider">
            Conversation
          </div>
          <div className="flex-1 overflow-y-auto">
            <ConversationPanel
              messages={messages}
              emptyState={
                viewMode === "archived"
                  ? "No saved transcript was found for this session."
                  : "Start speaking to interact with NEXUS"
              }
            />
          </div>
        </div>
      </div>

      <StatusBar phase={phase} isConnected={viewMode === "live" && isConnected} />
      {(pageError || error) && (
        <div className="border-t border-red-500/20 bg-red-950/20 px-4 py-2 text-sm text-red-300">
          {pageError || error}
        </div>
      )}
      {isLoading && (
        <div className="border-t border-[#27272a] bg-[#111113] px-4 py-2 text-sm text-zinc-500">
          Loading session...
        </div>
      )}
    </div>
  );
}
