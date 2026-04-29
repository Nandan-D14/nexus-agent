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
function IconCpu({ className }: { className?: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}><rect width="16" height="16" x="4" y="4" rx="2"/><rect width="6" height="6" x="9" y="9" rx="1"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/></svg>
}
function IconCheckCircle({ className }: { className?: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
}
function IconChevronUp({ className }: { className?: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}><path d="m18 15-6-6-6 6"/></svg>
}
function IconGlobe({ className }: { className?: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>
}
function IconCompass({ className }: { className?: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}><circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/></svg>
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
      className="overflow-y-auto h-full custom-scrollbar flex flex-col px-6 py-8 relative bg-transparent"
    >
      <div className="mx-auto max-w-3xl w-full flex flex-col gap-12 pb-48">
        <AnimatePresence initial={false}>
          {turns.map((turn, i) => {
            const isLastTurn = i === turns.length - 1;
            const isWorking = isLastTurn && isThinking;

            return (
              <motion.div 
                key={turn.id} 
                layout
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex flex-col gap-8"
              >
                {turn.userMessage && (
                  <UserMessageCard text={turn.userMessage.text} />
                )}
                
                {(turn.events.length > 0 || turn.agentMessages.length > 0 || turn.permissions.length > 0) && (
                  <div className="w-full flex flex-col gap-6">
                    {/* Agent Identity Header */}
                    <div className="flex items-center gap-2.5 px-0.5">
                      <div className="w-6 h-6 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center">
                        <IconCpu className="w-4 h-4 text-indigo-400" />
                      </div>
                      <span className="font-bold text-[15px] tracking-tight text-zinc-100">CoComputer</span>
                      <span className="text-[9px] text-indigo-400/80 border border-indigo-500/20 rounded px-1.5 py-0.5 ml-1 bg-indigo-500/5 font-bold uppercase tracking-wider">Lite</span>
                    </div>

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
                  </div>
                )}

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
              className="flex items-center gap-3 text-indigo-400 py-2"
            >
              <div className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-indigo-500"></span>
              </div>
              <span className="text-[14px] font-medium tracking-wide">Synthesizing intent...</span>
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
    <div className="flex w-full justify-end py-1">
      <div className="max-w-[85%] rounded-2xl bg-[#27272a] px-5 py-4 text-[15px] leading-relaxed text-zinc-100 shadow-sm border border-zinc-700/30">
        {text}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Agent Message (Crisp markdown)                                     */
/* ------------------------------------------------------------------ */

function AgentMessageCard({ text }: { text: string }) {
  return (
    <motion.div layout className="flex flex-col items-start px-0.5">
      <div className="w-full text-[15px] leading-relaxed text-zinc-200 font-normal">
        <ChatMarkdown content={text} />
      </div>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Agent Action Stream (The 2026 "Chain of Thought")                  */
/* ------------------------------------------------------------------ */

function AgentActionStream({ events, isWorking }: { events: Extract<ChatItem, { kind: "event" }>[], isWorking: boolean }) {
  const [expanded, setExpanded] = useState(true);
  
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

  return (
    <motion.div layout className="flex flex-col w-full max-w-full mt-2 text-[14px]">
      {/* Header */}
      <div 
        className="flex items-center gap-2 cursor-pointer transition-colors pt-2 pb-3"
        onClick={() => setExpanded(!expanded)}
      >
        <IconCheckCircle className={`w-4 h-4 ${isWorking ? "text-cyan-500 animate-pulse" : "text-zinc-500"}`} />
        <span className="font-semibold text-zinc-200">{isWorking ? currentAction : "Execution Log"}</span>
        <IconChevronUp className={`w-4 h-4 text-zinc-500 ml-1 transition-transform ${expanded ? "" : "rotate-180"}`} />
      </div>

      {/* The Workflow style log stream */}
      <AnimatePresence>
        {expanded && (
          <motion.div 
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="pl-2.5 pb-2"
          >
            <div className="border-l border-zinc-800/80 pl-5 space-y-4 relative pb-2 min-h-[20px]">
              {events.map((item, index) => (
                <WorkflowStyleRow key={`${item.type}-${item.ts}-${index}`} item={item} />
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

/* ------------------------------------------------------------------ */
/*  Workflow Style Row                                                 */
/* ------------------------------------------------------------------ */

function WorkflowStyleRow({ item }: { item: Extract<ChatItem, { kind: "event" }> }) {
  if (item.type === "agent_thinking") {
    return (
      <div className="flex flex-col gap-2 relative">
        <div className="absolute -left-[28px] top-1 bg-[#1a1a1c] p-0.5">
          <IconCompass className="w-[14px] h-[14px] text-zinc-500" />
        </div>
        <p className="text-zinc-300 text-[14px] mt-1 pr-4 leading-relaxed">
          {String(item["content"] || "Thinking...")}
        </p>
      </div>
    );
  }

  if (item.type === "agent_tool_call") {
    return (
      <div className="flex flex-col gap-2 relative">
        <div className="absolute -left-[28px] top-1 bg-[#1a1a1c] p-0.5">
          <IconTerminal className="w-[14px] h-[14px] text-zinc-500" />
        </div>
        <div className="bg-[#242426] border border-zinc-800/80 rounded-full px-3 py-1 text-[13px] text-zinc-400 flex items-center gap-2 inline-flex w-fit">
          <IconGlobe className="w-3.5 h-3.5" /> 
          <span>Using {String(item["tool"])}</span>
        </div>
        {item["args"] && (
          <div className="pl-1 text-[12px] font-mono text-zinc-500 dark:text-zinc-500 break-all bg-black/20 rounded p-2 mt-1">
            {JSON.stringify(item["args"])}
          </div>
        )}
      </div>
    );
  }

  if (item.type === "agent_tool_result") {
    return (
      <div className="pl-1 py-1 w-full relative">
        <div className="w-full max-h-32 overflow-y-auto custom-scrollbar bg-zinc-900/50 border border-zinc-800/50 rounded-lg p-2.5 text-[11px] font-mono text-zinc-500 whitespace-pre-wrap break-words">
          {String(item["output"] || "Success")}
        </div>
      </div>
    );
  }

  if (item.type === "agent_screenshot") {
    return (
      <div className="flex flex-col gap-2 relative">
        <div className="absolute -left-[28px] top-1 bg-[#1a1a1c] p-0.5">
          <IconEye className="w-[14px] h-[14px] text-zinc-500" />
        </div>
        <div className="bg-[#242426] border border-zinc-800/80 rounded-full px-3 py-1 text-[13px] text-zinc-400 flex items-center gap-2 inline-flex w-fit">
          <IconEye className="w-3.5 h-3.5" /> 
          <span>Vision Analysis</span>
        </div>
        <div className="pl-1 space-y-2 mt-1">
          {typeof item["analysis"] === "string" && item["analysis"] && (
            <p className="text-[14px] text-zinc-300 leading-relaxed pr-4">{item["analysis"]}</p>
          )}
          {typeof item["image_b64"] === "string" && item["image_b64"] && (
             <div className="relative w-[160px] h-[100px] rounded overflow-hidden border border-zinc-700/80 brightness-75 hover:brightness-100 transition">
               <img src={`data:image/png;base64,${item["image_b64"]}`} className="object-cover w-full h-full" alt="Screenshot" />
             </div>
          )}
        </div>
      </div>
    );
  }

  if (item.type === "error") {
     return (
      <div className="py-1.5 text-[13px] text-red-500 flex items-center gap-2 relative">
        <div className="absolute -left-[28px] top-1 bg-[#1a1a1c] p-0.5">
          <X className="w-[14px] h-[14px] text-red-500" />
        </div>
        <span className="font-medium">{String(item["message"] || "Failed")}</span>
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
    return null; 
  }

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
