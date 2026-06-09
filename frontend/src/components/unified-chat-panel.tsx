/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useMemo, useRef, useEffect, useState, memo } from "react";
import { ChatMarkdown } from "@/components/chat-markdown";
import { StreamingText } from "@/components/streaming-text";
import { PermissionCard } from "@/components/permission-card";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  Cpu,
  CheckCircle2,
  ChevronUp,
  ChevronDown,
  Eye,
  Terminal,
  Code2,
  Globe,
  Mail,
  Calendar,
  ListTodo,
  Plug,
  FileText,
  Loader2,
  Check,
  Brain,
} from "lucide-react";
import {
  classifyAgentTool,
  displayAgentToolName,
  type AgentToolProvider,
} from "@/lib/agent-tool-classification";
import {
  groupTurnEvents,
  type TaskGroup,
  type GroupedEvent,
} from "@/lib/turn-event-grouper";

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
      approval_id?: string;
      durable_task_id?: string;
      ts: number;
    }
  | { kind: "delegation"; from: string; to: string; ts: number };

type Props = {
  items: ChatItem[];
  isThinking: boolean;
  phase?: "idle" | "listening" | "thinking" | "acting" | "done";
  onPermissionRespond: (
    taskId: string,
    approved: boolean,
    approvalId?: string,
    durableTaskId?: string,
  ) => void;
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
/*  Tool Icon Helper                                                   */
/* ------------------------------------------------------------------ */

function getToolIcon(provider: AgentToolProvider, className: string) {
  switch (provider) {
    case "terminal": return <Terminal className={className} />;
    case "browser": return <Globe className={className} />;
    case "desktop": return <Eye className={className} />;
    case "file": return <FileText className={className} />;
    case "gmail": return <Mail className={className} />;
    case "calendar": return <Calendar className={className} />;
    case "tasks": return <ListTodo className={className} />;
    case "mcp": return <Plug className={className} />;
    case "workflow": return <ListTodo className={className} />;
    default: return <Code2 className={className} />;
  }
}

/* ------------------------------------------------------------------ */
/*  Compact Args Display                                               */
/* ------------------------------------------------------------------ */

function CompactArgs({ args }: { args: Record<string, unknown> }) {
  const [expanded, setExpanded] = useState(false);
  const entries = Object.entries(args);

  if (entries.length === 0) return null;

  const chips = entries.slice(0, 2).map(([key, value]) => {
    const display = typeof value === "string"
      ? value.length > 40 ? value.slice(0, 40) + "..." : value
      : JSON.stringify(value).length > 40
        ? JSON.stringify(value).slice(0, 40) + "..."
        : JSON.stringify(value);
    return (
      <span key={key} className="inline-flex items-center gap-1 bg-muted rounded-md px-1.5 py-0.5 text-[11px]">
        <span className="text-muted-foreground">{key}:</span>
        <span className="text-foreground font-medium">{display}</span>
      </span>
    );
  });

  return (
    <div className="pl-1 mt-1">
      <div className="flex items-center gap-1.5 flex-wrap">
        {chips}
        {entries.length > 2 && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-[10px] text-muted-foreground hover:text-foreground transition-colors font-medium"
          >
            +{entries.length - 2} more
          </button>
        )}
      </div>
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <pre className="text-[11px] font-mono text-muted-foreground bg-muted rounded-md p-2 mt-1.5 overflow-x-auto whitespace-pre-wrap break-all">
              {JSON.stringify(args, null, 2)}
            </pre>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main exported component                                            */
/* ------------------------------------------------------------------ */

export const UnifiedChatPanel = memo(function UnifiedChatPanel({
  items,
  isThinking,
  phase = "idle",
  onPermissionRespond,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [userScrolledUp, setUserScrolledUp] = useState(false);
  const isNearBottomRef = useRef(true);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const handleScroll = () => {
      const nearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 80;
      isNearBottomRef.current = nearBottom;
      setUserScrolledUp(!nearBottom);
    };

    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => el.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && isNearBottomRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [items, isThinking]);

  const scrollToBottom = () => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
      setUserScrolledUp(false);
      isNearBottomRef.current = true;
    }
  };

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

  const totalAgentMessages = turns.reduce((sum, t) => sum + t.agentMessages.length, 0);
  const lastTurnIdx = turns.length - 1;

  const phaseLabel = phase === "thinking" ? "Reasoning through it..."
    : phase === "acting" ? "Taking action..."
    : phase === "listening" ? "Listening..."
    : "Synthesizing intent...";

  return (
    <div className="relative h-full">
      <div
        ref={scrollRef}
        className="overflow-y-auto h-full custom-scrollbar flex flex-col px-6 py-8 bg-transparent"
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
                      <div className="flex items-center gap-2.5 px-0.5">
                        <div className="w-6 h-6 rounded-md bg-zinc-200 dark:bg-zinc-800 flex items-center justify-center">
                          <Cpu className="w-4 h-4 text-zinc-700 dark:text-zinc-300" />
                        </div>
                        <span className="font-semibold text-sm tracking-tight text-foreground">CoComputer</span>
                      </div>

                      {turn.events.length > 0 && (
                        <ExecutionLog events={turn.events} isWorking={isWorking} />
                      )}

                      {turn.agentMessages.map((msg, idx) => {
                        const isLastMsg = isLastTurn && idx === turn.agentMessages.length - 1;
                        const shouldStream = isLastMsg && !isThinking && totalAgentMessages <= 3;
                        return (
                          <AgentMessageCard
                            key={idx}
                            text={msg.text}
                            stream={shouldStream}
                          />
                        );
                      })}

                      {turn.permissions.map((perm, idx) => (
                        <motion.div layout key={idx} className="py-1">
                          <PermissionCard
                            taskId={perm.task_id}
                            approvalId={perm.approval_id}
                            durableTaskId={perm.durable_task_id}
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

          {/* Phase-Aware Thinking Indicator */}
          <AnimatePresence>
            {isThinking && turns.length > 0 && turns[lastTurnIdx].events.length === 0 && turns[lastTurnIdx].agentMessages.length === 0 && (
              <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                className="flex items-center gap-3 text-indigo-400 py-2"
              >
                {phase === "thinking" ? (
                  <Brain className="w-4 h-4 animate-pulse" />
                ) : (
                  <div className="relative flex h-3 w-3">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-indigo-500"></span>
                  </div>
                )}
                <motion.span
                  key={phase}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  className="text-[14px] font-medium tracking-wide"
                >
                  {phaseLabel}
                </motion.span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Scroll to bottom button */}
      <AnimatePresence>
        {userScrolledUp && (
          <motion.button
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            onClick={scrollToBottom}
            className="absolute bottom-6 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-background border border-border/60 shadow-lg text-[12px] font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            <ChevronDown className="w-3.5 h-3.5" />
            Scroll to bottom
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  );
});

/* ------------------------------------------------------------------ */
/*  User Message (Sleek modern bubble)                                 */
/* ------------------------------------------------------------------ */

function UserMessageCard({ text }: { text: string }) {
  return (
    <div className="flex w-full justify-end py-1">
      <div className="max-w-[85%] rounded-2xl bg-zinc-100 dark:bg-zinc-800 px-5 py-3.5 text-[15px] leading-relaxed text-zinc-900 dark:text-zinc-100 border border-zinc-200 dark:border-zinc-700/50">
        {text}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Agent Message (Crisp markdown)                                     */
/* ------------------------------------------------------------------ */

function AgentMessageCard({ text, stream = false }: { text: string; stream?: boolean }) {
  return (
    <motion.div layout className="flex flex-col items-start px-0.5">
      <div className="w-full text-[15px] leading-relaxed text-foreground font-normal">
        {stream ? (
          <StreamingText text={text} isStreaming={stream} />
        ) : (
          <ChatMarkdown content={text} />
        )}
      </div>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Execution Log (Per-task collapsible groups)                         */
/* ------------------------------------------------------------------ */

function ExecutionLog({
  events,
  isWorking,
}: {
  events: Extract<ChatItem, { kind: "event" }>[];
  isWorking: boolean;
}) {
  const taskGroups = useMemo(() => groupTurnEvents(events), [events]);

  return (
    <div className="flex flex-col gap-3 w-full max-w-full mt-2">
      {taskGroups.map((task, index) => {
        const isLast = index === taskGroups.length - 1;
        return (
          <TaskCard
            key={task.id}
            task={task}
            isActive={isLast && isWorking}
          />
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Task Card (Individual collapsible task)                            */
/* ------------------------------------------------------------------ */

function TaskCard({
  task,
  isActive,
}: {
  task: TaskGroup;
  isActive: boolean;
}) {
  const [expanded, setExpanded] = useState(true);
  const prevActiveRef = useRef(isActive);

  useEffect(() => {
    if (prevActiveRef.current && !isActive) {
      const timer = setTimeout(() => setExpanded(false), 1500);
      prevActiveRef.current = isActive;
      return () => clearTimeout(timer);
    }
    prevActiveRef.current = isActive;
  }, [isActive]);

  const toolSteps = task.steps.filter((s) => s.kind === "tool_invocation");
  const completedTools = toolSteps.filter(
    (s) => s.kind === "tool_invocation" && s.status === "completed",
  ).length;
  const totalTools = toolSteps.length;
  const isDone = !isActive && task.status === "completed";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.23, 1, 0.32, 1] }}
      className="w-full"
    >
      {/* Task Header */}
      <div
        className="flex items-center gap-2.5 cursor-pointer transition-colors py-2 px-1 rounded-lg hover:bg-muted/50"
        onClick={() => setExpanded(!expanded)}
      >
        {/* Status icon */}
        {isActive ? (
          <Loader2 className="w-4 h-4 text-cyan-500 animate-spin shrink-0" />
        ) : isDone ? (
          <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
        ) : (
          <CheckCircle2 className="w-4 h-4 text-zinc-500 shrink-0" />
        )}

        {/* Title */}
        <span className="text-[14px] font-medium text-foreground flex-1 min-w-0 truncate">
          {task.title}
        </span>

        {/* Step count badge */}
        {totalTools > 0 && (
          <span className="text-[10px] font-semibold text-muted-foreground bg-muted rounded-md px-1.5 py-0.5 shrink-0">
            {completedTools}/{totalTools}
          </span>
        )}

        {/* Collapse chevron */}
        <ChevronUp
          className={`w-4 h-4 text-zinc-500 shrink-0 transition-transform ${expanded ? "" : "rotate-180"}`}
        />
      </div>

      {/* Task Body */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.1 }}
          >
            <div className="border-l border-border/60 pl-5 ml-2 space-y-3 py-2 min-h-[20px]">
              {task.steps.map((step, index) => (
                <StepRow key={`${step.kind}-${index}`} item={step} />
              ))}
            </div>

            {/* Task summary */}
            {isDone && task.summary && (
              <div className="ml-2 mt-1 mb-1 pl-4 text-[13px] text-muted-foreground leading-relaxed italic border-l-2 border-emerald-500/30">
                {task.summary.length > 150
                  ? task.summary.slice(0, 150) + "..."
                  : task.summary}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Step Row (dispatcher for steps within a task)                      */
/* ------------------------------------------------------------------ */

function StepRow({ item }: { item: GroupedEvent }) {
  if (item.kind === "tool_invocation") {
    return <ToolInvocationCard invocation={item} />;
  }

  if (item.kind === "screenshot") {
    return <ScreenshotCard item={item} />;
  }

  if (item.kind === "error") {
    return (
      <div className="py-1.5 text-[13px] text-red-500 flex items-center gap-2 relative">
        <div className="absolute -left-[28px] top-1 bg-background p-0.5">
          <X className="w-[14px] h-[14px] text-red-500" />
        </div>
        <span className="font-medium">{item.message}</span>
      </div>
    );
  }

  return null;
}

/* ------------------------------------------------------------------ */
/*  Tool Invocation Card (paired call + result)                       */
/* ------------------------------------------------------------------ */

function ToolInvocationCard({
  invocation,
}: {
  invocation: Extract<GroupedEvent, { kind: "tool_invocation" }>;
}) {
  const [resultExpanded, setResultExpanded] = useState(false);
  const provider = classifyAgentTool(invocation.tool);
  const label = displayAgentToolName(invocation.tool);
  const isRunning = invocation.status === "running";
  const hasArgs = Object.keys(invocation.args).length > 0;
  const output = invocation.result?.output;
  const isLongOutput = output && output.length > 300;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.3, ease: [0.23, 1, 0.32, 1] }}
      className="flex flex-col gap-2 relative"
    >
      {/* Timeline node */}
      <div className="absolute -left-[28px] top-1 bg-background p-0.5">
        {isRunning ? (
          <Loader2 className="w-[14px] h-[14px] text-cyan-500 animate-spin" />
        ) : (
          <motion.div
            initial={{ scale: 0, rotate: -90 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{ type: "spring", stiffness: 400, damping: 15 }}
          >
            <Check className="w-[14px] h-[14px] text-emerald-500" />
          </motion.div>
        )}
      </div>

      {/* Tool pill */}
      <div
        className={`border rounded-lg px-3 py-1.5 text-[13px] flex items-center gap-2 inline-flex w-fit transition-colors ${
          isRunning
            ? "bg-muted border-cyan-500/30 text-foreground"
            : "bg-muted border-border/60 text-muted-foreground"
        }`}
      >
        {getToolIcon(provider, "w-3.5 h-3.5")}
        <span className="font-medium">{label}</span>
        {isRunning && (
          <Loader2 className="w-3 h-3 text-cyan-500 animate-spin ml-1" />
        )}
      </div>

      {/* Args (compact) */}
      {hasArgs && <CompactArgs args={invocation.args} />}

      {/* Result */}
      <AnimatePresence>
        {invocation.result && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            transition={{ duration: 0.3 }}
            className="pl-1 w-full"
          >
            <div
              className={`w-full overflow-y-auto custom-scrollbar bg-muted/50 border border-border/40 rounded-lg p-2.5 text-[11px] font-mono text-muted-foreground whitespace-pre-wrap break-words relative ${
                !resultExpanded && isLongOutput ? "max-h-24" : ""
              }`}
            >
              {output}
              {!resultExpanded && isLongOutput && (
                <div className="absolute bottom-0 left-0 right-0 h-10 bg-gradient-to-t from-muted/80 to-transparent pointer-events-none" />
              )}
            </div>
            {isLongOutput && (
              <button
                onClick={() => setResultExpanded(!resultExpanded)}
                className="text-[10px] text-muted-foreground hover:text-foreground mt-1 transition-colors font-medium"
              >
                {resultExpanded ? "Show less" : "Show more"}
              </button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Screenshot Card                                                    */
/* ------------------------------------------------------------------ */

function ScreenshotCard({
  item,
}: {
  item: Extract<GroupedEvent, { kind: "screenshot" }>;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="flex flex-col gap-2 relative"
    >
      <div className="absolute -left-[28px] top-1 bg-background p-0.5">
        <Eye className="w-[14px] h-[14px] text-zinc-500" />
      </div>
      <div className="bg-muted border border-border/60 rounded-full px-3 py-1 text-[13px] text-muted-foreground flex items-center gap-2 inline-flex w-fit">
        <Eye className="w-3.5 h-3.5" />
        <span>Vision Analysis</span>
      </div>
      <div className="pl-1 space-y-2 mt-1">
        {item.analysis && (
          <p className="text-[14px] text-foreground leading-relaxed pr-4">
            {item.analysis}
          </p>
        )}
        {item.image_b64 && (
          <div className="relative w-[160px] h-[100px] rounded overflow-hidden border border-zinc-700/80 brightness-75 hover:brightness-100 transition">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`data:image/png;base64,${item.image_b64}`}
              className="object-cover w-full h-full"
              alt="Screenshot"
            />
          </div>
        )}
      </div>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Delegation (Clean text)                                            */
/* ------------------------------------------------------------------ */
function DelegationBadge({ from, to }: { from: string; to: string }) {
  return (
    <div className="flex justify-center py-4">
      <span className="text-[12px] font-medium text-muted-foreground italic">
        {from} handed off to {to}
      </span>
    </div>
  );
}
