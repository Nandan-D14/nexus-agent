"use client";

import { useRef, useEffect } from "react";

type Message = {
  role: "user" | "agent";
  text: string;
};

type Props = {
  messages: Message[];
  emptyState?: string;
};

export function ConversationPanel({
  messages,
  emptyState = "Start speaking to interact with NEXUS",
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex items-center justify-center h-full px-6">
        <div className="text-center">
          {/* Waveform icon */}
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            className="w-10 h-10 mx-auto mb-3 text-zinc-600"
            aria-hidden="true"
            focusable="false"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 1v22M8 5v14M4 9v6M16 5v14M20 9v6"
            />
          </svg>
          <p className="text-zinc-500 text-sm">{emptyState}</p>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={scrollRef}
      className="flex flex-col gap-3 p-4 overflow-y-auto h-full scrollbar-thin scrollbar-track-transparent scrollbar-thumb-zinc-700"
    >
      {messages.map((msg, i) => (
        <div
          key={i}
          className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
        >
          <div
            className={`max-w-[80%] px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed ${
              msg.role === "user"
                ? "bg-[#22d3ee]/15 text-[#22d3ee] border border-[#22d3ee]/20 rounded-br-md"
                : "bg-[#27272a] text-zinc-200 rounded-bl-md"
            }`}
          >
            <span className="block text-[10px] font-semibold uppercase tracking-wider opacity-50 mb-1">
              {msg.role === "user" ? "You" : "NEXUS"}
            </span>
            {msg.text}
          </div>
        </div>
      ))}
    </div>
  );
}
