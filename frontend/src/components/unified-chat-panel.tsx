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
  ChevronDown,
  ChevronRight,
  Eye,
  Terminal as TerminalIcon,
  Code2,
  Globe,
  Mail,
  Calendar,
  ListTodo,
  Plug,
  FileText,
  Loader2,
  BrainCircuit,
  MessageSquare,
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
    case "terminal": return <TerminalIcon className={className} />;
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
/*  Inline summary extraction                                          */
/* ------------------------------------------------------------------ */

function getFileBasename(path: string): string {
  const parts = path.split(/[\\/]/);
  return parts[parts.length - 1];
}

function getInlineSummary(
  tool: string,
  args: Record<string, unknown>,
): string | null {
  if (!args) return null;

  if (tool === "ask_permission" || tool.endsWith("ask_permission")) {
    const action = typeof args.Action === "string" ? args.Action : "";
    const target = typeof args.Target === "string" ? args.Target : "";
    if (action && target) return `${action}: ${getFileBasename(target)}`;
  }

  if (typeof args.title === "string" && args.title) return args.title;

  if (typeof args.TargetFile === "string" && args.TargetFile) return args.TargetFile;
  if (typeof args.AbsolutePath === "string" && args.AbsolutePath) return args.AbsolutePath;
  if (typeof args.path === "string" && args.path) return args.path;
  if (typeof args.file === "string" && args.file) return args.file;

  if (typeof args.CommandLine === "string" && args.CommandLine) return args.CommandLine;
  if (typeof args.command === "string" && args.command) return args.command;

  if (typeof args.query === "string" && args.query) return `"${args.query}"`;
  if (typeof args.Prompt === "string" && args.Prompt) return `"${args.Prompt}"`;
  if (typeof args.question === "string" && args.question) return args.question;
  if (typeof args.Reason === "string" && args.Reason) return args.Reason;

  if (typeof args.DirectoryPath === "string" && args.DirectoryPath) return args.DirectoryPath;

  return null;
}

/* ------------------------------------------------------------------ */
/*  Timeline item type for interleaving                                */
/* ------------------------------------------------------------------ */

type TimelineItem =
  | { kind: "taskGroup"; data: TaskGroup; ts: number }
  | { kind: "agentMessage"; text: string; ts: number }
  | { kind: "permission"; data: Extract<ChatItem, { kind: "permission" }>; ts: number }
  | { kind: "delegation"; from: string; to: string; ts: number };

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

  const phaseLabel = phase === "thinking" ? "Reasoning through it..."
    : phase === "acting" ? "Working through..."
    : phase === "listening" ? "Listening..."
    : "Generating...";

  return (
    <div className="relative h-full bg-white dark:bg-[#0d0d0d] transition-colors">
      <div
        ref={scrollRef}
        className="overflow-y-auto h-full custom-scrollbar flex flex-col px-6 py-8"
      >
        <div className="mx-auto max-w-3xl w-full flex flex-col gap-10 pb-48">
          <AnimatePresence initial={false}>
            {turns.map((turn, i) => {
              const isLastTurn = i === turns.length - 1;
              const isWorking = isLastTurn && isThinking;
              return (
                <TurnBlock
                  key={turn.id}
                  turn={turn}
                  isWorking={isWorking}
                  isLastTurn={isLastTurn}
                  totalAgentMessages={totalAgentMessages}
                  onPermissionRespond={onPermissionRespond}
                />
              );
            })}
          </AnimatePresence>

          {/* Phase-Aware Status Indicator */}
          <AnimatePresence>
            {isThinking && turns.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="flex items-center gap-3 py-2 mt-2"
              >
                <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center shadow-md shadow-blue-600/20">
                  <MessageSquare className="w-3.5 h-3.5 text-white" />
                </div>
                <motion.span
                  key={phase}
                  initial={{ opacity: 0, x: 5 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="text-[14px] font-medium text-zinc-400 dark:text-zinc-500 tracking-wide"
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
            className="absolute bottom-6 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white dark:bg-[#1a1a1e] border border-zinc-200 dark:border-zinc-800 shadow-lg text-[12px] font-medium text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors"
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
/*  Turn Block                                                         */
/* ------------------------------------------------------------------ */

function TurnBlock({
  turn,
  isWorking,
  isLastTurn,
  totalAgentMessages,
  onPermissionRespond,
}: {
  turn: Turn;
  isWorking: boolean;
  isLastTurn: boolean;
  totalAgentMessages: number;
  onPermissionRespond: Props["onPermissionRespond"];
}) {
  // Build an interleaved timeline from task groups + agent messages + permissions + delegations
  const taskGroups = useMemo(() => groupTurnEvents(turn.events), [turn.events]);

  const timeline = useMemo(() => {
    const items: TimelineItem[] = [];

    for (const group of taskGroups) {
      items.push({ kind: "taskGroup", data: group, ts: group.ts });
    }
    for (const msg of turn.agentMessages) {
      items.push({ kind: "agentMessage", text: msg.text, ts: msg.ts });
    }
    for (const perm of turn.permissions) {
      items.push({ kind: "permission", data: perm, ts: perm.ts });
    }
    for (const del of turn.delegations) {
      items.push({ kind: "delegation", from: del.from, to: del.to, ts: del.ts });
    }

    items.sort((a, b) => a.ts - b.ts);
    return items;
  }, [taskGroups, turn.agentMessages, turn.permissions, turn.delegations]);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col gap-5 w-full"
    >
      {turn.userMessage && (
        <UserMessageCard text={turn.userMessage.text} />
      )}

      {timeline.map((item, idx) => {
        const isLastGroup = isWorking && idx === timeline.length - 1 && item.kind === "taskGroup";

        if (item.kind === "taskGroup") {
          return (
            <ThoughtAccordion
              key={`group-${item.data.id}`}
              task={item.data}
              isActive={isLastGroup}
            />
          );
        }

        if (item.kind === "agentMessage") {
          const msgIdx = turn.agentMessages.findIndex(m => m.ts === item.ts);
          const isLastMsg = isLastTurn && msgIdx === turn.agentMessages.length - 1;
          const shouldStream = isLastMsg && !isWorking && totalAgentMessages <= 3;
          return (
            <AgentMessageCard
              key={`msg-${item.ts}-${idx}`}
              text={item.text}
              stream={shouldStream}
            />
          );
        }

        if (item.kind === "permission") {
          return (
            <motion.div layout key={`perm-${idx}`} className="py-1">
              <PermissionCard
                taskId={item.data.task_id}
                approvalId={item.data.approval_id}
                durableTaskId={item.data.durable_task_id}
                description={item.data.description}
                estimatedSeconds={item.data.estimated_seconds}
                agent={item.data.agent}
                onRespond={onPermissionRespond}
              />
            </motion.div>
          );
        }

        if (item.kind === "delegation") {
          return <DelegationBadge key={`del-${idx}`} from={item.from} to={item.to} />;
        }

        return null;
      })}
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  User Message                                                       */
/* ------------------------------------------------------------------ */

function UserMessageCard({ text }: { text: string }) {
  return (
    <div className="flex w-full justify-end py-1">
      <div className="max-w-[80%] rounded-2xl bg-zinc-100 dark:bg-[#1a1a1e] px-5 py-3 text-[15px] leading-relaxed text-zinc-900 dark:text-zinc-100 border border-zinc-200/80 dark:border-zinc-800/60">
        {text}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Agent Message                                                      */
/* ------------------------------------------------------------------ */

function AgentMessageCard({ text, stream = false }: { text: string; stream?: boolean }) {
  return (
    <motion.div layout className="flex flex-col items-start w-full">
      <div className="w-full text-[15px] leading-[1.75] text-zinc-800 dark:text-zinc-100 font-medium">
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
/*  Thought Accordion                                                  */
/* ------------------------------------------------------------------ */

function buildSummary(task: TaskGroup): string {
  const thinkings = task.steps.filter(s => s.kind === "thinking").length;
  const toolSteps = task.steps.filter(s => s.kind === "tool_invocation");

  let viewedCount = 0;
  let ranCount = 0;
  let fetchedCount = 0;
  let otherCount = 0;

  for (const step of toolSteps) {
    if (step.kind !== "tool_invocation") continue;
    const provider = classifyAgentTool(step.tool);
    if (provider === "file") viewedCount++;
    else if (provider === "terminal") ranCount++;
    else if (provider === "browser") fetchedCount++;
    else otherCount++;
  }

  const parts: string[] = [`Thought ${Math.max(1, thinkings)} time(s)`];
  if (viewedCount > 0) parts.push(`Viewed ${viewedCount} file(s)`);
  if (ranCount > 0) parts.push(`Ran ${ranCount} command(s)`);
  if (fetchedCount > 0) parts.push(`Fetched ${fetchedCount} web(s)`);
  if (otherCount > 0) parts.push(`Used ${otherCount} tool(s)`);

  return parts.join(", ");
}

function ThoughtAccordion({
  task,
  isActive,
}: {
  task: TaskGroup;
  isActive: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const summary = useMemo(() => buildSummary(task), [task]);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: [0.23, 1, 0.32, 1] }}
      className="w-full flex flex-col"
    >
      {/* Accordion header */}
      <button
        className="flex items-center gap-1.5 w-fit text-left select-none group py-0.5"
        onClick={() => setExpanded(!expanded)}
      >
        <span className="text-[14px] text-zinc-400 dark:text-zinc-500 group-hover:text-zinc-600 dark:group-hover:text-zinc-300 transition-colors">
          {summary}
        </span>
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-zinc-400 dark:text-zinc-500 group-hover:text-zinc-300 transition-colors" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-zinc-400 dark:text-zinc-500 group-hover:text-zinc-300 transition-colors" />
        )}
        {isActive && (
          <Loader2 className="w-3 h-3 text-cyan-500 animate-spin ml-1" />
        )}
      </button>

      {/* Accordion content */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="flex flex-col gap-4 pt-3 pb-1 pl-1">
              {task.steps.map((step, index) => (
                <StepRow key={`${step.kind}-${index}`} item={step} />
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Step Row dispatcher                                                */
/* ------------------------------------------------------------------ */

function StepRow({ item }: { item: GroupedEvent }) {
  if (item.kind === "thinking") return <ThinkingBlock text={item.text} />;
  if (item.kind === "tool_invocation") return <ToolLine invocation={item} />;
  if (item.kind === "screenshot") return <ScreenshotCard item={item} />;
  if (item.kind === "error") return <ErrorLine message={item.message} />;
  return null;
}

/* ------------------------------------------------------------------ */
/*  Thinking Process Block                                             */
/* ------------------------------------------------------------------ */

function ThinkingBlock({ text }: { text: string }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2 text-[14px] text-zinc-400 dark:text-zinc-500 font-medium">
        <BrainCircuit className="w-4 h-4" />
        Thinking process
      </div>
      <div className="pl-6 border-l-2 border-zinc-200 dark:border-zinc-800 text-[14px] leading-[1.8] text-zinc-500 dark:text-zinc-400">
        <ChatMarkdown content={text} />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Tool Line (flat text-style rendering)                              */
/* ------------------------------------------------------------------ */

function ToolLine({
  invocation,
}: {
  invocation: Extract<GroupedEvent, { kind: "tool_invocation" }>;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const provider = classifyAgentTool(invocation.tool);
  const label = displayAgentToolName(invocation.tool);
  const isRunning = invocation.status === "running";
  const summary = getInlineSummary(invocation.tool, invocation.args);
  const output = invocation.result?.output;

  // Try parsing web search results
  let parsedResults: Array<{ url: string; title: string; snippet?: string }> | null = null;
  if (output && (invocation.tool === "search_web" || invocation.tool === "web_search" || invocation.tool === "scrape_web_page")) {
    try {
      const parsed = JSON.parse(output);
      if (Array.isArray(parsed) && parsed.length > 0 && parsed[0]?.url && parsed[0]?.title) {
        parsedResults = parsed;
      }
    } catch { /* not JSON */ }
  }

  // ── Terminal ──
  if (provider === "terminal") {
    const cmd = summary || "command";
    const truncated = cmd.length > 70 ? cmd.slice(0, 70) + "..." : cmd;
    return (
      <div className="flex items-center gap-2 text-[14px] font-mono min-w-0">
        <TerminalIcon className="w-4 h-4 text-zinc-400 dark:text-zinc-600 shrink-0" />
        <span className="text-zinc-400 dark:text-zinc-500 select-none shrink-0">Terminal</span>
        <span className="text-zinc-600 dark:text-zinc-400 truncate">{truncated}</span>
        {isRunning && <Loader2 className="w-3.5 h-3.5 text-cyan-500 animate-spin ml-1 shrink-0" />}
      </div>
    );
  }

  // ── Read File ──
  if (provider === "file") {
    const path = summary || "file";
    const truncated = path.length > 60 ? "..." + path.slice(-57) : path;
    return (
      <div className="flex items-center gap-2 text-[14px] font-mono min-w-0">
        <FileText className="w-4 h-4 text-zinc-400 dark:text-zinc-600 shrink-0" />
        <span className="text-zinc-400 dark:text-zinc-500 select-none shrink-0">Read File</span>
        <span className="text-zinc-600 dark:text-zinc-400 truncate">{truncated}</span>
        {isRunning && <Loader2 className="w-3.5 h-3.5 text-cyan-500 animate-spin ml-1 shrink-0" />}
      </div>
    );
  }

  // ── WebFetch with results ──
  if (parsedResults) {
    return (
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2 text-[14px] text-zinc-400 dark:text-zinc-500 font-medium">
          <Globe className="w-4 h-4" />
          WebFetch {parsedResults.length} results
        </div>
        <div className="flex flex-col gap-0 rounded-xl border border-zinc-200 dark:border-zinc-800 overflow-hidden ml-6">
          {parsedResults.map((res, idx) => {
            let domain = "";
            try { domain = new URL(res.url).hostname; } catch { /* */ }
            return (
              <a
                key={idx}
                href={res.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 px-4 py-2.5 text-[14px] text-zinc-500 dark:text-zinc-400 hover:text-zinc-800 dark:hover:text-zinc-200 hover:bg-zinc-50 dark:hover:bg-zinc-900/50 transition-colors border-b border-zinc-100 dark:border-zinc-800/60 last:border-b-0"
              >
                <Globe className="w-3.5 h-3.5 shrink-0" />
                <span className="truncate">{domain || res.url}</span>
              </a>
            );
          })}
        </div>
      </div>
    );
  }

  // ── Web browser tool (no parsed results) ──
  if (provider === "browser") {
    const desc = summary || label;
    const truncated = desc.length > 70 ? desc.slice(0, 70) + "..." : desc;
    return (
      <div className="flex items-center gap-2 text-[14px] font-mono min-w-0">
        <Globe className="w-4 h-4 text-zinc-400 dark:text-zinc-600 shrink-0" />
        <span className="text-zinc-400 dark:text-zinc-500 select-none shrink-0">WebFetch</span>
        <span className="text-zinc-600 dark:text-zinc-400 truncate">{truncated}</span>
        {isRunning && <Loader2 className="w-3.5 h-3.5 text-cyan-500 animate-spin ml-1 shrink-0" />}
      </div>
    );
  }

  // ── Generic tool with expandable detail card ──
  const hasDetails = Object.keys(invocation.args).length > 0 || !!output;

  return (
    <div className="flex flex-col gap-2">
      <button
        onClick={() => hasDetails && setDetailsOpen(!detailsOpen)}
        className={`flex items-center gap-2 text-[14px] min-w-0 text-left ${hasDetails ? "cursor-pointer" : "cursor-default"}`}
      >
        {getToolIcon(provider, "w-4 h-4 text-zinc-400 dark:text-zinc-600 shrink-0")}
        <span className="text-zinc-400 dark:text-zinc-500 select-none shrink-0">{label}</span>
        {summary && summary !== label && (
          <span className="text-zinc-600 dark:text-zinc-400 truncate max-w-[400px]">{summary}</span>
        )}
        {isRunning && <Loader2 className="w-3.5 h-3.5 text-cyan-500 animate-spin ml-1 shrink-0" />}
      </button>

      <AnimatePresence>
        {detailsOpen && hasDetails && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden ml-6"
          >
            <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 overflow-hidden">
              {/* Card header */}
              <div className="px-4 py-2.5 border-b border-zinc-200 dark:border-zinc-800 text-[13px] font-medium text-zinc-600 dark:text-zinc-300">
                {summary || label}
              </div>

              {/* Args */}
              {Object.keys(invocation.args).length > 0 && (
                <div className="px-4 py-3">
                  <div className="text-[12px] text-zinc-400 dark:text-zinc-500 mb-1.5 font-medium">Input</div>
                  <pre className="text-[12px] font-mono text-zinc-600 dark:text-zinc-400 whitespace-pre-wrap break-words leading-relaxed">
                    {JSON.stringify(invocation.args, null, 2)}
                  </pre>
                </div>
              )}

              {/* Output */}
              {output && (
                <div className="px-4 py-3 border-t border-zinc-100 dark:border-zinc-800/60">
                  <div className="text-[12px] text-zinc-400 dark:text-zinc-500 mb-1.5 font-medium">Output</div>
                  <pre className="text-[12px] font-mono text-zinc-600 dark:text-zinc-400 whitespace-pre-wrap break-words leading-relaxed max-h-40 overflow-y-auto">
                    {output.length > 500 ? output.slice(0, 500) + "\n..." : output}
                  </pre>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Error Line                                                         */
/* ------------------------------------------------------------------ */

function ErrorLine({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 text-[14px]">
      <X className="w-4 h-4 text-red-400 dark:text-red-500 shrink-0 mt-0.5" />
      <span className="text-red-500 dark:text-red-400">{message}</span>
    </div>
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
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2 text-[14px] text-zinc-400 dark:text-zinc-500 font-medium">
        <Eye className="w-4 h-4" />
        Vision Analysis
      </div>
      <div className="pl-6 space-y-3">
        {item.analysis && (
          <p className="text-[13px] text-zinc-500 dark:text-zinc-400 leading-relaxed">
            {item.analysis}
          </p>
        )}
        {item.image_b64 && (
          <div className="relative w-[160px] h-[100px] rounded-xl overflow-hidden border border-zinc-200 dark:border-zinc-800 brightness-90 hover:brightness-100 transition">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`data:image/png;base64,${item.image_b64}`}
              className="object-cover w-full h-full"
              alt="Screenshot"
            />
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Delegation Badge                                                   */
/* ------------------------------------------------------------------ */

function DelegationBadge({ from, to }: { from: string; to: string }) {
  return (
    <div className="flex justify-center py-4">
      <span className="text-[12px] font-medium text-zinc-400 dark:text-zinc-600 italic">
        {from} handed off to {to}
      </span>
    </div>
  );
}
