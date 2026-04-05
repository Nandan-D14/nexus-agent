"use client";

import { useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChatMarkdown } from "@/components/chat-markdown";

type Message = {
  role: "user" | "agent";
  text: string;
};

type Props = {
  messages: Message[];
  isThinking?: boolean;
};

export function ConversationPanel({ messages, isThinking = false }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, [messages, isThinking]);

  if (messages.length === 0) {
    return (
      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="flex items-center justify-center h-full px-8"
      >
        <div className="text-center space-y-4">
          <div className="relative inline-flex items-center justify-center">
            <div className="absolute inset-0 bg-cyan-500/20 rounded-full blur-xl animate-pulse" />
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.5}
              className="relative w-12 h-12 text-zinc-700"
              aria-hidden="true"
              focusable="false"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 1v22M8 5v14M4 9v6M16 5v14M20 9v6"
              />
            </svg>
          </div>
          <div className="space-y-1">
            <p className="text-zinc-400 text-xs font-bold uppercase tracking-widest">
              Awaiting Input
            </p>
            <p className="text-zinc-600 text-[10px] max-w-[180px] mx-auto leading-relaxed uppercase tracking-wider">
              Initialize communication via voice or text command.
            </p>
          </div>
        </div>
      </motion.div>
    );
  }

  return (
    <div
      ref={scrollRef}
      className="flex flex-col gap-6 p-6 overflow-y-auto h-full custom-scrollbar"
    >
      <AnimatePresence mode="popLayout">
        {messages.map((msg, i) => (
          <motion.div
            key={`${i}-${msg.text.slice(0, 10)}`}
            initial={{ opacity: 0, y: 10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
            className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}
          >
            <div className="flex items-center gap-2 mb-2 px-1">
              <span className={`text-[9px] font-black uppercase tracking-[0.2em] ${msg.role === "user" ? "text-cyan-500" : "text-emerald-500"}`}>
                {msg.role === "user" ? "Protocol: User" : "Source: COCOMPUTER"}
              </span>
              <div className={`w-1 h-1 rounded-full ${msg.role === "user" ? "bg-cyan-500/40" : "bg-emerald-500/40"}`} />
            </div>
            
            <div
              className={`max-w-full px-4 py-3 rounded-2xl text-sm leading-relaxed transition-all duration-300 ${
                msg.role === "user"
                  ? "bg-cyan-500/5 text-cyan-50 border border-cyan-500/20 rounded-tr-none shadow-lg shadow-cyan-500/5"
                  : "bg-zinc-900 text-zinc-200 border border-zinc-800 rounded-tl-none"
              }`}
            >
              <ChatMarkdown content={msg.text} />
            </div>
          </motion.div>
        ))}

        {/* Thinking indicator */}
        {isThinking && (
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="flex flex-col items-start"
          >
            <div className="flex items-center gap-2 mb-2 px-1">
              <span className="text-[9px] font-black text-emerald-500 uppercase tracking-[0.2em]">
                Source: COCOMPUTER
              </span>
              <div className="w-1 h-1 rounded-full bg-emerald-500/40" />
            </div>
            
            <div className="px-4 py-3 rounded-2xl rounded-tl-none bg-zinc-900 border border-zinc-800 flex items-center gap-3">
              <div className="flex items-center gap-1">
                <motion.div animate={{ scale: [1, 1.2, 1] }} transition={{ duration: 1, repeat: Infinity, delay: 0 }} className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                <motion.div animate={{ scale: [1, 1.2, 1] }} transition={{ duration: 1, repeat: Infinity, delay: 0.2 }} className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                <motion.div animate={{ scale: [1, 1.2, 1] }} transition={{ duration: 1, repeat: Infinity, delay: 0.4 }} className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              </div>
              <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                Neural Processing...
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
