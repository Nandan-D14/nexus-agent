"use client";

import { useParams, useSearchParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState, useCallback } from "react";

import { useSession } from "@/lib/use-session";
import { useWebSocket } from "@/lib/use-websocket";
import { useMicrophone } from "@/lib/use-microphone";
import { AudioPlayer } from "@/lib/audio-playback";
import type { WsMessage, SessionPhase } from "@/lib/message-types";

import { DesktopPanel } from "@/components/desktop-panel";
import { ConversationPanel } from "@/components/conversation-panel";
import { ActivityFeed } from "@/components/activity-feed";
import { MicButton } from "@/components/mic-button";
import { StatusBar } from "@/components/status-bar";
import { DemoPicker } from "@/components/demo-picker";

type Message = { role: "user" | "agent"; text: string };
type ActivityEvent = { type: string; timestamp: number; [key: string]: unknown };

export default function SessionPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const sessionId = params.id as string;

  // Session data
  const { session, destroySession } = useSession();
  const [streamUrl, setStreamUrl] = useState<string | null>(
    session?.stream_url ?? null
  );
  const [phase, setPhase] = useState<SessionPhase>("idle");

  // Chat state
  const [messages, setMessages] = useState<Message[]>([]);
  const [events, setEvents] = useState<ActivityEvent[]>([]);

  // Text input
  const [textInput, setTextInput] = useState("");

  // Derived: agent is busy (thinking or acting)
  const isBusy = phase === "thinking" || phase === "acting";

  // Audio player
  const audioPlayer = useRef(new AudioPlayer());

  // WebSocket
  const wsUrl =
    typeof window !== "undefined"
      ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${process.env.NEXT_PUBLIC_AGENT_WS_URL?.replace(/^wss?:\/\//, "") || "localhost:8000"}/ws/${sessionId}?ticket=${session?.ws_ticket || ""}`
      : null;

  const { sendBinary, sendJson, lastMessage, isConnected, onBinaryMessageRef } =
    useWebSocket(session?.ws_ticket ? wsUrl : null);

  // Microphone
  const { start: startMic, stop: stopMic, isRecording } = useMicrophone(sendBinary);

  // Audio playback for incoming binary frames
  useEffect(() => {
    onBinaryMessageRef.current = (data: ArrayBuffer) => {
      audioPlayer.current.play(data);
    };
  }, [onBinaryMessageRef]);

  // Process incoming WS messages
  useEffect(() => {
    if (!lastMessage) return;
    const msg = lastMessage;

    const addEvent = (m: WsMessage) => {
      queueMicrotask(() => setEvents((prev) => [...prev, { ...m, timestamp: Date.now() }]));
    };

    switch (msg.type) {
      case "sandbox_status":
        addEvent(msg);
        break;
      case "vnc_url":
        queueMicrotask(() => setStreamUrl(msg.url));
        break;
      case "transcript":
        queueMicrotask(() => {
          setMessages((prev) => [...prev, { role: msg.role, text: msg.text }]);
          if (msg.role === "agent") setPhase("done");
        });
        break;
      case "agent_thinking":
        queueMicrotask(() => setPhase("thinking"));
        addEvent(msg);
        break;
      case "agent_tool_call":
        queueMicrotask(() => setPhase("acting"));
        addEvent(msg);
        break;
      case "agent_tool_result":
        addEvent(msg);
        break;
      case "agent_screenshot":
        addEvent(msg);
        break;
      case "agent_complete":
        queueMicrotask(() => setPhase("done"));
        addEvent(msg);
        break;
      case "error":
        addEvent(msg);
        break;
    }
  }, [lastMessage]);

  // Handle mic toggle
  const toggleMic = useCallback(() => {
    if (isRecording) {
      stopMic();
      setPhase("thinking");
    } else {
      startMic();
      setPhase("listening");
    }
  }, [isRecording, startMic, stopMic]);

  // Handle text submit
  const handleTextSubmit = useCallback(() => {
    const text = textInput.trim();
    if (!text) return;
    sendJson({ type: "text_input", text });
    setTextInput("");
    setPhase("thinking");
  }, [textInput, sendJson]);

  // Handle demo selection
  const handleDemo = useCallback(
    (text: string) => {
      sendJson({ type: "text_input", text });
      setPhase("thinking");
    },
    [sendJson]
  );

  // Auto-send demo command from URL params
  useEffect(() => {
    const demo = searchParams.get("demo");
    if (demo && isConnected) {
      const timer = setTimeout(() => handleDemo(demo), 1500);
      return () => clearTimeout(timer);
    }
  }, [isConnected, searchParams, handleDemo]);

  // Handle end session
  const handleEnd = async () => {
    audioPlayer.current.stop();
    stopMic();
    await destroySession();
    router.push("/");
  };

  return (
    <div className="relative h-screen flex flex-col overflow-hidden bg-[#09090b] text-[#fafafa]">
      {/* Background Decor */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-cyan-500/5 rounded-full blur-[100px]" />
        <div className="absolute bottom-0 left-0 w-[500px] h-[500px] bg-emerald-500/5 rounded-full blur-[100px]" />
      </div>

      {/* Top bar */}
      <header className="relative z-20 flex items-center justify-between px-6 py-3 border-b border-zinc-800 glass">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-black tracking-tighter italic">
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-emerald-400">
                NEXUS
              </span>
            </h1>
            <div className="h-4 w-[1px] bg-zinc-800" />
            <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-[0.2em]">
              Agent Workspace
            </span>
          </div>

          {isConnected && (
            <div className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider">
                Connection Stable
              </span>
            </div>
          )}
        </div>

        <button
          onClick={handleEnd}
          className="group flex items-center gap-2 px-4 py-1.5 rounded-xl border border-red-500/30 text-red-400 hover:bg-red-500 hover:text-white transition-all duration-300 text-xs font-bold uppercase tracking-wider active:scale-95 shadow-lg shadow-red-500/5"
        >
          Termination
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" className="w-3.5 h-3.5 group-hover:rotate-90 transition-transform">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </header>

      {/* Main 3-panel layout */}
      <div className="relative z-10 flex-1 flex overflow-hidden">
        {/* Left: Activity Feed */}
        <aside className="w-80 border-r border-zinc-800 flex flex-col overflow-hidden bg-zinc-950/40">
          <div className="px-4 py-3 border-b border-zinc-800/50 flex items-center justify-between">
            <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-[0.2em]">
              Activity Log
            </span>
            <div className="w-1.5 h-1.5 rounded-full bg-zinc-700" />
          </div>
          <div className="flex-1 overflow-y-auto custom-scrollbar">
            <ActivityFeed events={events} />
          </div>
        </aside>

        {/* Center: Desktop + Input */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Desktop viewer */}
          <div className="flex-1 p-4 overflow-hidden">
            <div className="h-full rounded-2xl border border-zinc-800 bg-black overflow-hidden shadow-2xl shadow-black/50 transition-all">
              <DesktopPanel streamUrl={streamUrl} />
            </div>
          </div>

          {/* Controls Area */}
          <div className="px-4 pb-4 space-y-4">
            {/* Demo picker (show when idle and no messages sent yet) */}
            {messages.length === 0 && events.length === 0 && isConnected && (
              <div className="animate-fade-in">
                <div className="flex items-center gap-4 mb-3">
                  <div className="h-[1px] flex-1 bg-zinc-800/50" />
                  <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-[0.2em]">Quick Deployment</span>
                  <div className="h-[1px] flex-1 bg-zinc-800/50" />
                </div>
                <DemoPicker onSelect={handleDemo} disabled={!isConnected} />
              </div>
            )}

            {/* Input bar */}
            <div className="p-2 rounded-2xl bg-zinc-900/50 border border-zinc-800 flex items-center gap-3 glass shadow-lg">
              <input
                type="text"
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleTextSubmit()}
                placeholder={isBusy ? "NEXUS is processing..." : "Initialize mission command..."}
                disabled={!isConnected || isBusy}
                className="flex-1 bg-transparent px-4 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none disabled:opacity-40 disabled:cursor-not-allowed font-medium"
              />
              
              <div className="h-6 w-[1px] bg-zinc-800" />
              
              <button
                type="button"
                onClick={handleTextSubmit}
                disabled={!isConnected || isBusy || !textInput.trim()}
                className="px-5 py-2 rounded-xl bg-cyan-500 text-black text-xs font-black uppercase tracking-wider hover:bg-cyan-400 transition-all disabled:opacity-20 disabled:cursor-not-allowed active:scale-95 shadow-lg shadow-cyan-500/10"
              >
                Send
              </button>
              
              <MicButton
                isRecording={isRecording}
                onStart={toggleMic}
                onStop={toggleMic}
                disabled={!isConnected || isBusy}
              />
            </div>
          </div>
        </main>

        {/* Right: Conversation */}
        <aside className="w-80 border-l border-zinc-800 flex flex-col overflow-hidden bg-zinc-950/40">
          <div className="px-4 py-3 border-b border-zinc-800/50 flex items-center justify-between">
            <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-[0.2em]">
              Intelligence
            </span>
            <div className="flex gap-1">
              <div className="w-1 h-1 rounded-full bg-cyan-500/40" />
              <div className="w-1 h-1 rounded-full bg-cyan-500/40" />
              <div className="w-1 h-1 rounded-full bg-cyan-500/40" />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto custom-scrollbar">
            <ConversationPanel messages={messages} isThinking={isBusy} />
          </div>
        </aside>
      </div>

      {/* Status bar */}
      <footer className="relative z-20">
        <StatusBar phase={phase} isConnected={isConnected} />
      </footer>
    </div>
  );
}
