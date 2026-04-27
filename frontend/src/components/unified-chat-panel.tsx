"use client";

import { useMemo, useRef, useEffect, useState, type ReactNode } from "react";
import { ChatMarkdown } from "@/components/chat-markdown";
import { PermissionCard } from "@/components/permission-card";
import { motion, AnimatePresence } from "framer-motion";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
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

type Props = {
  items: ChatItem[];
  isThinking: boolean;
  onPermissionRespond: (taskId: string, approved: boolean) => void;
};

type Turn = {
  id: string;
  userMessage?: Extract<ChatItem, { kind: "message" }>;
  events: Extract<ChatItem, { kind: "event" }>[];
  agentMessages: Extract<ChatItem, { kind: "message" }>[];
  permissions: Extract<ChatItem, { kind: "permission" }>[];
  delegations: Extract<ChatItem, { kind: "delegation" }>[];
};

/* ------------------------------------------------------------------ */
/*  Minimal Icons (2026 Style)                                         */
/* ------------------------------------------------------------------ */
function IconSparkles({ className }: { className?: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className={className}><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>
}
function IconTerminal({ className }: { className?: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className={className}><polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/></svg>
}
function IconEye({ className }: { className?: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className={className}><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
}

/* ------------------------------------------------------------------ */
/*  Main exported component                                            */
/* ------------------------------------------------------------------ */

export function UnifiedChatPanel({
  items,
  isThinking,
  onPermissionRespond,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, [items, isThinking]);

  const turns = useMemo(() => {
    const grouped: Turn[] = [];
    let currentTurn: Turn = { id: "initial", events: [], agentMessages: [], permissions: [], delegations: [] };

    for (const item of items) {
      if (item.kind === "message" && item.role === "user") {
        if (currentTurn.userMessage || currentTurn.events.length > 0 || currentTurn.agentMessages.length > 0 || currentTurn.permissions.length > 0) {
          grouped.push(currentTurn);
        }
        currentTurn = { id: `turn-${item.ts}`, userMessage: item, events: [], agentMessages: [], permissions: [], delegations: [] };
      } else if (item.kind === "message" && item.role === "agent") {
        currentTurn.agentMessages.push(item);
      } else if (item.kind === "event") {
        currentTurn.events.push(item);
      } else if (item.kind === "permission") {
        currentTurn.permissions.push(item);
      } else if (item.kind === "delegation") {
        currentTurn.delegations.push(item);
      }
    }
    grouped.push(currentTurn);
    return grouped.filter(t => t.userMessage || t.events.length > 0 || t.agentMessages.length > 0 || t.permissions.length > 0);
  }, [items]);

  return (
    <div
      ref={scrollRef}
      className="overflow-y-auto h-full custom-scrollbar flex flex-col px-4 py-8 relative bg-transparent"
    >
      <div className="mx-auto max-w-3xl w-full flex flex-col gap-12 pb-32">
        <AnimatePresence initial={false}>
          {turns.map((turn, i) => {
            const isLastTurn = i === turns.length - 1;
            const isWorking = isLastTurn && isThinking;

            return (
              <motion.div 
                key={turn.id} 
                layout
                initial={{ opacity: 0, y: 20, filter: "blur(4px)" }}
                animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                className="flex flex-col gap-6"
              >
                {turn.userMessage && (
                  <UserMessageCard text={turn.userMessage.text} />
                )}
                
                {turn.events.length > 0 && (
                  <AgentActionStream events={turn.events} isWorking={isWorking} />
                )}

                {turn.agentMessages.map((msg, idx) => (
                  <AgentMessageCard key={idx} text={msg.text} />
                ))}

                {turn.permissions.map((perm, idx) => (
                  <motion.div layout key={idx} className="py-1">
                    <PermissionCard
                      taskId={perm.task_id}
                      description={perm.description}
                      estimatedSeconds={perm.estimated_seconds}
                      agent={perm.agent}
                      onRespond={onPermissionRespond}
                    />
                  </motion.div>
                ))}

                {turn.delegations.map((del, idx) => (
                  <DelegationBadge key={idx} from={del.from} to={del.to} />
                ))}
              </motion.div>
            );
          })}
        </AnimatePresence>

        {/* Floating Thinking Indicator */}
        <AnimatePresence>
          {isThinking && turns.length > 0 && turns[turns.length-1].events.length === 0 && turns[turns.length-1].agentMessages.length === 0 && (
            <motion.div 
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              className="flex items-center gap-3 text-cyan-400 py-2"
            >
              <div className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-cyan-500"></span>
              </div>
              <span className="text-[15px] font-medium tracking-wide">Synthesizing intent...</span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  User Message (Sleek modern bubble)                                 */
/* ------------------------------------------------------------------ */

function UserMessageCard({ text }: { text: string }) {
  return (
    <div className="flex w-full justify-end py-2 pl-12">
      <div className="max-w-[80%] rounded-2xl rounded-tr-md bg-zinc-100/80 dark:bg-[#212126] border border-zinc-200/50 dark:border-[#2f2f35] px-5 py-3.5 text-[15px] leading-relaxed text-zinc-900 dark:text-zinc-100 shadow-sm backdrop-blur-sm">
        {text}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Agent Message (Borderless, crisp markdown)                         */
/* ------------------------------------------------------------------ */

function AgentMessageCard({ text }: { text: string }) {
  return (
    <motion.div layout className="flex flex-col items-start py-2 pr-12">
      <div className="w-full text-[16px] leading-relaxed text-zinc-700 dark:text-zinc-300 font-normal">
        <ChatMarkdown content={text} />
      </div>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Agent Action Stream (The 2026 "Chain of Thought")                  */
/* ------------------------------------------------------------------ */

function AgentActionStream({ events, isWorking }: { events: Extract<ChatItem, { kind: "event" }>[], isWorking: boolean }) {
  const [expanded, setExpanded] = useState(false);
  
  // Find the most recent meaningful action to show as the "status"
  const currentAction = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i--) {
      const e = events[i];
      if (e.type === "agent_tool_call") return `Using ${e["tool"]}`;
      if (e.type === "agent_screenshot") return `Analyzing screen`;
      if (e.type === "agent_thinking" && typeof e["content"] === "string") return e["content"];
    }
    return "Processing...";
  }, [events]);

  const toolCount = events.filter(e => e.type === "agent_tool_call").length;
  const timeSecs = events.length > 1 ? ((events[events.length - 1].ts - events[0].ts) / 1000).toFixed(1) : 0;

  if (!isWorking && !expanded) {
    return (
      <motion.button 
        layout
        onClick={() => setExpanded(true)}
        className="group w-fit flex items-center gap-2.5 px-3 py-1.5 rounded-full bg-zinc-100/50 dark:bg-zinc-900/50 border border-zinc-200/50 dark:border-zinc-800/50 hover:bg-zinc-200/50 dark:hover:bg-zinc-800/80 transition-all cursor-pointer overflow-hidden backdrop-blur-sm"
      >
        <IconSparkles className="w-3.5 h-3.5 text-zinc-400 dark:text-zinc-500 group-hover:text-cyan-500 transition-colors" />
        <span className="text-[12px] font-medium text-zinc-500 dark:text-zinc-400 group-hover:text-zinc-700 dark:group-hover:text-zinc-200 transition-colors">
          Analyzed intent and ran {toolCount} tool{toolCount !== 1 ? 's' : ''} in {timeSecs}s
        </span>
      </motion.button>
    );
  }

  return (
    <motion.div layout className="flex flex-col gap-3 w-full max-w-full">
      {/* The Active/Status Bar */}
      <div 
        className="flex items-center gap-3 text-cyan-500 cursor-pointer w-fit"
        onClick={() => !isWorking && setExpanded(false)}
      >
        {isWorking ? (
           <div className="relative flex h-2 w-2 ml-1">
             <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
             <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500"></span>
           </div>
        ) : (
           <IconSparkles className="w-4 h-4 text-zinc-500 hover:text-cyan-500 transition-colors" />
        )}
        <span className={`text-[14px] font-medium tracking-wide ${isWorking ? "text-cyan-500 animate-pulse" : "text-zinc-500"}`}>
          {isWorking ? currentAction : "Execution Log"}
        </span>
      </div>

      {/* The Glassmorphic Log Stream */}
      <AnimatePresence>
        {(isWorking || expanded) && (
          <motion.div 
            initial={{ opacity: 0, height: 0, filter: "blur(4px)" }}
            animate={{ opacity: 1, height: "auto", filter: "blur(0px)" }}
            exit={{ opacity: 0, height: 0, filter: "blur(4px)" }}
            className="flex flex-col gap-1.5 pl-6 border-l border-zinc-200 dark:border-zinc-800/80"
          >
            {events.map((item, index) => (
              <GlassRow key={`${item.type}-${item.ts}-${index}`} item={item} />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

/* ------------------------------------------------------------------ */
/*  Glass Row (Individual items in the stream)                         */
/* ------------------------------------------------------------------ */

function GlassRow({ item }: { item: Extract<ChatItem, { kind: "event" }> }) {
  if (item.type === "agent_thinking") {
    return (
      <div className="text-[13px] text-zinc-400 dark:text-zinc-500 py-1">
        {String(item["content"] || "Thinking...")}
      </div>
    );
  }

  if (item.type === "agent_tool_call") {
    return (
      <div className="flex flex-col gap-1 py-1.5">
        <div className="flex items-center gap-2 text-[13px] font-medium text-zinc-700 dark:text-zinc-300">
          <IconTerminal className="w-3.5 h-3.5 text-zinc-400" />
          <span>{String(item["tool"])}</span>
        </div>
        {item["args"] && (
          <div className="pl-5 text-[12px] font-mono text-zinc-500 dark:text-zinc-500 break-all">
            {JSON.stringify(item["args"])}
          </div>
        )}
      </div>
    );
  }

  if (item.type === "agent_tool_result") {
    return (
      <div className="pl-5 py-1 w-full">
        <div className="w-full max-h-32 overflow-y-auto custom-scrollbar bg-zinc-100/50 dark:bg-[#0A0A0A] border border-zinc-200/50 dark:border-zinc-800/50 rounded-lg p-2.5 text-[11px] font-mono text-zinc-600 dark:text-zinc-400 whitespace-pre-wrap break-words backdrop-blur-sm">
          {String(item["output"] || "Success")}
        </div>
      </div>
    );
  }

  if (item.type === "agent_screenshot") {
    return (
      <div className="flex flex-col gap-2 py-1.5">
        <div className="flex items-center gap-2 text-[13px] font-medium text-zinc-700 dark:text-zinc-300">
          <IconEye className="w-3.5 h-3.5 text-amber-500" />
          <span>Vision Analysis</span>
        </div>
        <div className="pl-5 space-y-2">
          {typeof item["analysis"] === "string" && item["analysis"] && (
            <p className="text-[12px] text-zinc-500 dark:text-zinc-400 leading-relaxed">{item["analysis"]}</p>
          )}
          {typeof item["image_b64"] === "string" && item["image_b64"] && (
             <img src={`data:image/png;base64,${item["image_b64"]}`} className="max-h-32 rounded-lg border border-zinc-200/50 dark:border-zinc-800/50 object-contain shadow-sm" alt="Screenshot" />
          )}
        </div>
      </div>
    );
  }

  if (item.type === "error") {
     return (
      <div className="py-1.5 text-[13px] text-red-500 flex items-center gap-2">
        <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
        {String(item["message"] || "Failed")}
      </div>
     );
  }

  // Hide internal plumbing and system events
  if (
    item.type === "agent_complete" || 
    item.type.startsWith("bg_task") ||
    item.type === "context_packet" ||
    item.type === "sandbox_status" ||
    item.type === "voice_status" ||
    item.type === "budget_warning" ||
    item.type === "resume_recovery" ||
    item.type === "pong" ||
    item.type === "quota_update"
  ) {
    return null; // Keep it clean, don't show plumbing
  }

  // Only show known events, silently drop the rest to maintain a pristine UI
  return null;
}

/* ------------------------------------------------------------------ */
/*  Delegation (Clean text)                                            */
/* ------------------------------------------------------------------ */
function DelegationBadge({ from, to }: { from: string; to: string }) {
  return (
    <div className="flex justify-center py-4">
      <span className="text-[12px] font-medium text-zinc-400 dark:text-zinc-500 italic">
        {from} handed off to {to}
      </span>
    </div>
  );
}
