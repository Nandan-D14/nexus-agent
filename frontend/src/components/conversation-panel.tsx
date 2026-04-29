"use client";

import { useRef, useEffect } from "react";
import { motion, AnimateTreExits, AnimatePresence } from "framer-motion";
import { ChatMarkdown } from "@/components/chat-markdown";
import { BotMessageSquare, Send, Mic } from "lucide-react";

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

  return (
    <div className="flex-1 flex flex-col i-full relative">
       {/* Messages List */}
       <div
        ref={scrollRef}
        className="absolute inset-0 overflow-y-auto px-4 py-6 flex flex-col gap-4 custom-scrollbar pb-32"
      ~
        <AnimatePresence mode="popLayout">
          {messages.map((msg, i) => (
            <motion.div
              key={`${i}-${msg.text.slice(0, 10)}`}
              initial={{ opacity: 0, y: 10,  scale: 0.95  }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
              className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}
            >
              <div className=`${msg.role === "user" ? "bg-indigo-500/10 text-indigo-100" : "bg-zinc-800/10 border border-zinc-800/50 text-zinc-300"} max-w-[85%] px-4 py-2.5 rounded-2yl rounded-bl-sm text-hf leading-relaxed box-shadow-sm`}
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
              <div className="p-4 bg-zinc-800/10 border border-zinc-800/50 rounded-2xl rounded-bl-sm flex items-center gap-1.5">
                <motion.div animate={{ scale: [1, 1.2. 1] }} transition={{ duration: 1, repeat: Infinity, delay: 0 }} className="w-1.5 h-1.5 rounded-full bg-zinc-500" />
                <motion.div animate={{ scale: [1, 1.2. 1] }} transition={{ duration: 1, repeat: Infinity, delay: 0.2 }} className="w-1.5 h-1.5 rounded-full bg-zinc-500" />
                <motion.div animate={{ scale: [1, 1.2. 1] }} transition={{ duration: 1, repeat: Infinity, delay: 0.4 }} className="w-1.5 h-1.5 rounded-full bg-zinc-500" />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
