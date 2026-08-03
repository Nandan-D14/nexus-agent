/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useMemo, useRef, useEffect, useState, memo, type ReactNode } from "react";
import { StreamingText } from "@/components/streaming-text";
import { PermissionCard } from "@/components/permission-card";
import {
  AgentQuestionCard,
  ThinkingReasoning,
  ThinkingState,
  WebSearchCard,
  hasRealReasoning,
} from "@/components/agent-ui";
import {
  collectSearchRefsFromEventSegments,
  resolveSearchResults,
  type SearchCiteRef,
} from "@/lib/search-result-utils";
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
  MessageSquare,
  BookOpen,
  Bot,
  LayoutGrid,
} from "lucide-react";
import {
  classifyAgentTool,
  displayAgentToolName,
  formatGroupedToolLabel,
  toolActionLabel,
  type AgentToolProvider,
} from "@/lib/agent-tool-classification";
import {
  groupTurnEvents,
  type GenerativeUiSegment,
  type ArtifactCreatedSegment,
  type TaskGroup,
  type GroupedEvent,
} from "@/lib/turn-event-grouper";
import { GenerativeUICard } from "@/components/generative-ui-card";
import { ArtifactAttachmentCard } from "@/components/artifacts";
import {
  DOC_ARTIFACT_TOOLS,
  artifactFromToolResult,
} from "@/lib/artifact-url";
import type { RunArtifact } from "@/lib/message-types";

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
      resolved?: boolean;
      decision?: "approved" | "denied" | "timed_out";
      ts: number;
    }
  | { kind: "delegation"; from: string; to: string; ts: number }
  | {
      kind: "user_question";
      question_id: string;
      question: string;
      answered?: boolean;
      timedOut?: boolean;
      timeout_seconds?: number;
      ts: number;
    };

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
  onQuestionRespond?: (questionId: string, answer: string) => void;
  /** Sticky dock rendered inside the chat scroll column (e.g. todos + composer). */
  footer?: ReactNode;
};

type Turn = {
  id: string;
  userMessage?: Extract<ChatItem, { kind: "message" }>;
  events: Extract<ChatItem, { kind: "event" }>[];
  agentMessages: Extract<ChatItem, { kind: "message" }>[];
  permissions: Extract<ChatItem, { kind: "permission" }>[];
  delegations: Extract<ChatItem, { kind: "delegation" }>[];
  questions: Extract<ChatItem, { kind: "user_question" }>[];
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
    case "skill": return <BookOpen className={className} />;
    case "subagent": return <Bot className={className} />;
    case "worker": return <TerminalIcon className={className} />;
    case "workflow": return <LayoutGrid className={className} />;
    case "mcp": return <Plug className={className} />;
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
  if (typeof args.prompt === "string" && args.prompt) {
    const p = args.prompt;
    return p.length > 80 ? `"${p.slice(0, 77)}..."` : `"${p}"`;
  }
  if (typeof args.question === "string" && args.question) return args.question;
  if (typeof args.Reason === "string" && args.Reason) return args.Reason;
  if (typeof args.skill_id === "string" && args.skill_id) return args.skill_id;
  if (typeof args.request === "string" && args.request) {
    const r = args.request;
    return r.length > 80 ? `${r.slice(0, 77)}...` : r;
  }
  if (typeof args.role === "string" && typeof args.type_name === "string") {
    return `${args.role} · ${args.type_name}`;
  }
  if (typeof args.role === "string" && args.role) return args.role;
  if (typeof args.subagent_id === "string" && args.subagent_id) {
    return args.subagent_id.slice(0, 12);
  }

  if (typeof args.DirectoryPath === "string" && args.DirectoryPath) return args.DirectoryPath;

  return null;
}

/* ------------------------------------------------------------------ */
/*  Timeline item type for interleaving                                */
/* ------------------------------------------------------------------ */

type TimelineItem =
  | { kind: "taskGroup"; data: TaskGroup; ts: number }
  | { kind: "generative_ui"; data: GenerativeUiSegment; ts: number }
  | { kind: "artifact_created"; data: ArtifactCreatedSegment; ts: number }
  | { kind: "agentMessage"; text: string; ts: number }
  | { kind: "permission"; data: Extract<ChatItem, { kind: "permission" }>; ts: number }
  | { kind: "delegation"; from: string; to: string; ts: number }
  | { kind: "user_question"; data: Extract<ChatItem, { kind: "user_question" }>; ts: number };

/* ------------------------------------------------------------------ */
/*  Main exported component                                            */
/* ------------------------------------------------------------------ */

export const UnifiedChatPanel = memo(function UnifiedChatPanel({
  items,
  isThinking,
  phase = "idle",
  onPermissionRespond,
  onQuestionRespond,
  footer,
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
    let currentTurn: Turn = { id: "initial", events: [], agentMessages: [], permissions: [], delegations: [], questions: [] };

    const hasContent = (t: Turn) =>
      Boolean(t.userMessage) || t.events.length > 0 || t.agentMessages.length > 0 || t.permissions.length > 0 || t.questions.length > 0;

    for (const item of items) {
      if (item.kind === "message" && item.role === "user") {
        if (hasContent(currentTurn)) {
          grouped.push(currentTurn);
        }
        currentTurn = { id: `turn-${item.ts}`, userMessage: item, events: [], agentMessages: [], permissions: [], delegations: [], questions: [] };
      } else if (item.kind === "message" && item.role === "agent") {
        currentTurn.agentMessages.push(item);
      } else if (item.kind === "event") {
        currentTurn.events.push(item);
      } else if (item.kind === "permission") {
        currentTurn.permissions.push(item);
      } else if (item.kind === "delegation") {
        currentTurn.delegations.push(item);
      } else if (item.kind === "user_question") {
        currentTurn.questions.push(item);
      }
    }
    grouped.push(currentTurn);
    return grouped.filter(hasContent);
  }, [items]);

  const totalAgentMessages = turns.reduce((sum, t) => sum + t.agentMessages.length, 0);

  const phaseLabel = phase === "thinking" ? "Thinking…"
    : phase === "acting" ? "Working through..."
    : phase === "listening" ? "Listening..."
    : "Generating...";

  // Hide bottom ThinkingState when the last active task group already shows ThinkingReasoning.
  const showPhaseShimmer = useMemo(() => {
    if (!isThinking || turns.length === 0) return false;
    const lastTurn = turns[turns.length - 1];
    if (!lastTurn) return false;
    const segs = groupTurnEvents(lastTurn.events);
    const lastGroup = [...segs].reverse().find((s) => s.kind === "task_group");
    if (!lastGroup || lastGroup.kind !== "task_group") return true;
    const chunks = lastGroup.data.steps
      .filter((s): s is Extract<GroupedEvent, { kind: "thinking" }> => s.kind === "thinking")
      .map((s) => s.text);
    const show = !hasRealReasoning(chunks);
    return show;
  }, [isThinking, turns]);

  return (
    <div className="relative h-full bg-white dark:bg-[#0d0d0d] transition-colors">
      <div
        ref={scrollRef}
        className={`overflow-y-auto h-full custom-scrollbar flex flex-col px-6 pt-8 ${
          footer ? "pb-0" : "pb-8"
        }`}
      >
        <div
          className={`mx-auto max-w-3xl w-full flex flex-col gap-10 ${
            footer ? "pb-52" : "pb-6"
          }`}
        >
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
                  onQuestionRespond={onQuestionRespond}
                />
              );
            })}
          </AnimatePresence>

          {/* Phase-Aware Status Indicator — only when no live ThinkingReasoning */}
          <AnimatePresence>
            {showPhaseShimmer && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="flex items-center gap-3 py-2 mt-2"
              >
                <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center shadow-md shadow-blue-600/20">
                  <MessageSquare className="w-3.5 h-3.5 text-white" />
                </div>
                <motion.div
                  key={phase}
                  initial={{ opacity: 0, x: 5 }}
                  animate={{ opacity: 1, x: 0 }}
                >
                  <ThinkingState label={phaseLabel} />
                </motion.div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {footer ? (
        <div className="absolute inset-x-0 bottom-0 z-20 bg-[#0d0d0d] px-6 pt-1 pb-3">
          <AnimatePresence>
            {userScrolledUp && (
              <motion.button
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 10 }}
                onClick={scrollToBottom}
                className="mx-auto mb-2 flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white dark:bg-[#1a1a1e] border border-zinc-200 dark:border-zinc-800 shadow-lg text-[12px] font-medium text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors"
              >
                <ChevronDown className="w-3.5 h-3.5" />
                Scroll to bottom
              </motion.button>
            )}
          </AnimatePresence>
          <div className="mx-auto w-full max-w-3xl">{footer}</div>
        </div>
      ) : null}

      {/* Scroll to bottom button (no footer dock) */}
      <AnimatePresence>
        {!footer && userScrolledUp && (
          <motion.button
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            onClick={scrollToBottom}
            className="absolute bottom-6 left-1/2 -translate-x-1/2 z-30 flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white dark:bg-[#1a1a1e] border border-zinc-200 dark:border-zinc-800 shadow-lg text-[12px] font-medium text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors"
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
  onQuestionRespond,
}: {
  turn: Turn;
  isWorking: boolean;
  isLastTurn: boolean;
  totalAgentMessages: number;
  onPermissionRespond: Props["onPermissionRespond"];
  onQuestionRespond?: Props["onQuestionRespond"];
}) {
  // Build an interleaved timeline from event segments + messages + cards
  const eventSegments = useMemo(() => groupTurnEvents(turn.events), [turn.events]);

  const turnSearchRefs = useMemo(
    () => collectSearchRefsFromEventSegments(eventSegments),
    [eventSegments],
  );

  const timeline = useMemo(() => {
    const items: TimelineItem[] = [];

    for (const seg of eventSegments) {
      if (seg.kind === "task_group") {
        items.push({ kind: "taskGroup", data: seg.data, ts: seg.ts });
      } else if (seg.kind === "generative_ui") {
        items.push({ kind: "generative_ui", data: seg, ts: seg.ts });
      } else if (seg.kind === "artifact_created") {
        items.push({ kind: "artifact_created", data: seg, ts: seg.ts });
      }
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
    for (const question of turn.questions) {
      items.push({ kind: "user_question", data: question, ts: question.ts });
    }

    items.sort((a, b) => a.ts - b.ts);
    return items;
  }, [eventSegments, turn.agentMessages, turn.permissions, turn.delegations, turn.questions]);

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

        if (item.kind === "generative_ui") {
          return (
            <motion.div
              layout
              key={`genui-${item.data.ts}-${idx}`}
              className="w-full py-1"
            >
              <GenerativeUICard
                title={item.data.title}
                componentType={item.data.component_type}
                component={item.data.component}
              />
            </motion.div>
          );
        }

        if (item.kind === "artifact_created") {
          const raw = item.data.artifact;
          const artifact = coerceRunArtifact(raw);
          if (!artifact) return null;
          return (
            <motion.div
              layout
              key={`artifact-${artifact.artifact_id}-${idx}`}
              className="w-full max-w-xl py-1"
            >
              <ArtifactAttachmentCard artifact={artifact} compact />
            </motion.div>
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
              extraSources={turnSearchRefs}
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
                issuedAt={item.data.ts}
                decision={item.data.decision}
                timedOut={item.data.decision === "timed_out"}
                onRespond={onPermissionRespond}
              />
            </motion.div>
          );
        }

        if (item.kind === "delegation") {
          return <DelegationBadge key={`del-${idx}`} from={item.from} to={item.to} />;
        }

        if (item.kind === "user_question") {
          return (
            <motion.div layout key={`question-${item.data.question_id}`} className="py-1">
              <AgentQuestionCard
                questionId={item.data.question_id}
                question={item.data.question}
                answered={item.data.answered}
                timedOut={item.data.timedOut}
                timeoutSeconds={item.data.timeout_seconds}
                issuedAt={item.data.ts}
                onRespond={onQuestionRespond}
              />
            </motion.div>
          );
        }

        return null;
      })}
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Artifact coercion                                                  */
/* ------------------------------------------------------------------ */

function coerceRunArtifact(raw: Record<string, unknown>): RunArtifact | null {
  const artifactId = typeof raw.artifact_id === "string" ? raw.artifact_id : null;
  if (!artifactId) return null;
  return {
    artifact_id: artifactId,
    run_id: typeof raw.run_id === "string" ? raw.run_id : "",
    session_id: typeof raw.session_id === "string" ? raw.session_id : "",
    kind: typeof raw.kind === "string" ? raw.kind : "file",
    title: typeof raw.title === "string" ? raw.title : "Generated file",
    preview: typeof raw.preview === "string" ? raw.preview : "",
    created_at: typeof raw.created_at === "string" ? raw.created_at : null,
    path: typeof raw.path === "string" ? raw.path : null,
    url: typeof raw.url === "string" ? raw.url : null,
    metadata:
      raw.metadata && typeof raw.metadata === "object"
        ? (raw.metadata as Record<string, unknown>)
        : {},
  };
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

function AgentMessageCard({
  text,
  stream = false,
  extraSources,
}: {
  text: string;
  stream?: boolean;
  extraSources?: SearchCiteRef[];
}) {
  return (
    <motion.div layout className="flex flex-col items-start w-full">
      <div className="w-full text-[15px] leading-[1.75] font-medium text-text-primary">
        <StreamingText text={text} isStreaming={stream} extraSources={extraSources} />
      </div>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Thought Accordion                                                  */
/* ------------------------------------------------------------------ */

function buildSummary(task: TaskGroup): string {
  const hasThinking = task.steps.some(s => s.kind === "thinking");
  const toolSteps = task.steps.filter(s => s.kind === "tool_invocation");

  let viewedCount = 0;
  let wroteCount = 0;
  let ranCount = 0;
  let fetchedCount = 0;
  let skillCount = 0;
  let workerCount = 0;
  let subagentCount = 0;
  let otherCount = 0;

  for (const step of toolSteps) {
    if (step.kind !== "tool_invocation") continue;
    const tool = step.tool;
    const provider = classifyAgentTool(tool);
    if (provider === "skill") skillCount++;
    else if (provider === "worker") workerCount++;
    else if (provider === "subagent") subagentCount++;
    else if (tool === "read_workspace_file" || tool === "list_workspace_files") viewedCount++;
    else if (tool === "write_workspace_file") wroteCount++;
    else if (provider === "terminal") ranCount++;
    else if (provider === "browser") fetchedCount++;
    else otherCount++;
  }

  const parts: string[] = [];
  if (hasThinking) parts.push("Thought");
  if (skillCount > 0) parts.push(`Read ${skillCount} skill(s)`);
  if (workerCount > 0) parts.push(`Called ${workerCount} worker(s)`);
  if (subagentCount > 0) parts.push(`Spawned ${subagentCount} subagent(s)`);
  if (viewedCount > 0) parts.push(`Viewed ${viewedCount} file(s)`);
  if (wroteCount > 0) parts.push(`Wrote ${wroteCount} file(s)`);
  if (ranCount > 0) parts.push(`Ran ${ranCount} command(s)`);
  if (fetchedCount > 0) parts.push(`Fetched ${fetchedCount} web(s)`);
  if (otherCount > 0) parts.push(`Used ${otherCount} tool(s)`);
  if (parts.length === 0) parts.push("Working");

  return parts.join(", ");
}

function ThoughtAccordion({
  task,
  isActive,
}: {
  task: TaskGroup;
  isActive: boolean;
}) {
  const [expanded, setExpanded] = useState(true);
  const summary = useMemo(() => buildSummary(task), [task]);

  // Merge ALL thinking steps into one reasoning row, and group consecutive
  // identical tool invocations into counted rows (e.g. "Read 7 emails").
  const displayRows = useMemo(() => {
    type ToolInvocationStep = Extract<GroupedEvent, { kind: "tool_invocation" }>;
    type Row =
      | {
          kind: "reasoning";
          chunks: string[];
          startedAt: number;
          endedAt: number;
          key: string;
        }
      | { kind: "step"; item: GroupedEvent; key: string }
      | {
          kind: "tool_group";
          tool: string;
          items: ToolInvocationStep[];
          key: string;
        };

    const thinkingSteps = task.steps.filter(
      (step): step is Extract<GroupedEvent, { kind: "thinking" }> =>
        step.kind === "thinking",
    );
    const rows: Row[] = [];

    if (thinkingSteps.length > 0) {
      const chunks = thinkingSteps.map((step) => step.text);
      if (hasRealReasoning(chunks)) {
        rows.push({
          kind: "reasoning",
          chunks,
          startedAt: thinkingSteps[0].ts,
          endedAt: thinkingSteps[thinkingSteps.length - 1].ts,
          key: `reason-${thinkingSteps[0].ts}`,
        });
      }
    }

    let toolRun: ToolInvocationStep[] = [];
    const flushTools = () => {
      if (toolRun.length === 0) return;
      if (toolRun.length === 1) {
        rows.push({
          kind: "step",
          item: toolRun[0],
          key: `tool-${toolRun[0].callTs}`,
        });
      } else {
        rows.push({
          kind: "tool_group",
          tool: toolRun[0].tool,
          items: toolRun,
          key: `tool-group-${toolRun[0].callTs}`,
        });
      }
      toolRun = [];
    };

    task.steps.forEach((step, index) => {
      if (step.kind === "thinking") return;
      if (step.kind === "tool_invocation") {
        if (toolRun.length > 0 && toolRun[0].tool !== step.tool) {
          flushTools();
        }
        toolRun.push(step);
        return;
      }
      flushTools();
      rows.push({ kind: "step", item: step, key: `${step.kind}-${index}` });
    });
    flushTools();
    return rows;
  }, [task.steps]);

  const lastStep = task.steps[task.steps.length - 1];
  const reasoningIsLive = isActive && lastStep?.kind === "thinking";
  const hasToolSteps = displayRows.some(
    (r) => r.kind === "step" || r.kind === "tool_group",
  );
  const hasReasoningRows = displayRows.some((r) => r.kind === "reasoning");
  const hasRunningTool = task.steps.some(
    (s) => s.kind === "tool_invocation" && s.status === "running",
  );

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: [0.23, 1, 0.32, 1] }}
      className="w-full flex flex-col gap-3"
    >
      {displayRows.map((row) => {
        if (row.kind === "reasoning") {
          return (
            <ThinkingReasoning
              key={row.key}
              chunks={row.chunks}
              isActive={reasoningIsLive}
              startedAt={row.startedAt}
              endedAt={row.endedAt}
            />
          );
        }
        return null;
      })}

      {hasToolSteps ? (
        <>
          <button
            type="button"
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
            {isActive && !hasReasoningRows && !hasRunningTool && (
              <Loader2 className="w-3 h-3 text-cyan-500 animate-spin ml-1" />
            )}
            {hasRunningTool && (
              <Loader2 className="w-3 h-3 text-cyan-500 animate-spin ml-1" />
            )}
          </button>

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
                  {displayRows.map((row) => {
                    if (row.kind === "step") {
                      return <StepRow key={row.key} item={row.item} />;
                    }
                    if (row.kind === "tool_group") {
                      return (
                        <ToolGroupLine
                          key={row.key}
                          tool={row.tool}
                          items={row.items}
                        />
                      );
                    }
                    return null;
                  })}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </>
      ) : null}
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Step Row dispatcher                                                */
/* ------------------------------------------------------------------ */

function StepRow({ item }: { item: GroupedEvent }) {
  if (item.kind === "tool_invocation") return <ToolLine invocation={item} />;
  if (item.kind === "screenshot") return <ScreenshotCard item={item} />;
  if (item.kind === "error") return <ErrorLine message={item.message} />;
  return null;
}

function ToolGroupLine({
  tool,
  items,
}: {
  tool: string;
  items: Extract<GroupedEvent, { kind: "tool_invocation" }>[];
}) {
  const [open, setOpen] = useState(false);
  const provider = classifyAgentTool(tool);
  const isRunning = items.some((item) => item.status === "running");
  const label = formatGroupedToolLabel(tool, items.length);
  const icon = (() => {
    if (provider === "gmail") return <Mail className="w-3.5 h-3.5" />;
    if (provider === "calendar") return <Calendar className="w-3.5 h-3.5" />;
    if (provider === "tasks") return <ListTodo className="w-3.5 h-3.5" />;
    if (provider === "browser") return <Globe className="w-3.5 h-3.5" />;
    if (provider === "terminal") return <TerminalIcon className="w-3.5 h-3.5" />;
    if (provider === "skill") return <BookOpen className="w-3.5 h-3.5" />;
    if (provider === "worker") return <Bot className="w-3.5 h-3.5" />;
    if (tool.includes("file") || tool.includes("workspace")) {
      return <FileText className="w-3.5 h-3.5" />;
    }
    return <Plug className="w-3.5 h-3.5" />;
  })();

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        className="flex items-center gap-2 text-[14px] min-w-0 text-left group"
        onClick={() => setOpen((value) => !value)}
      >
        <span className="shrink-0 text-zinc-400 dark:text-zinc-600">{icon}</span>
        <span className="text-zinc-500 dark:text-zinc-400 select-none shrink-0 font-medium group-hover:text-zinc-700 dark:group-hover:text-zinc-200 transition-colors">
          {label}
        </span>
        {open ? (
          <ChevronDown className="w-3.5 h-3.5 text-zinc-400 dark:text-zinc-600 shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-zinc-400 dark:text-zinc-600 shrink-0" />
        )}
        {isRunning ? (
          <Loader2 className="w-3.5 h-3.5 text-cyan-500 animate-spin ml-1 shrink-0" />
        ) : null}
      </button>
      {open ? (
        <div className="flex flex-col gap-3 pl-5">
          {items.map((item) => (
            <ToolLine key={`${item.tool}-${item.callTs}`} invocation={item} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Tool Line (flat text-style rendering)                              */
/* ------------------------------------------------------------------ */

function ToolLogLine({
  icon,
  label,
  detail,
  isRunning,
}: {
  icon: ReactNode;
  label: string;
  detail?: string | null;
  isRunning?: boolean;
}) {
  const truncated =
    detail && detail.length > 80 ? `${detail.slice(0, 77)}...` : detail;
  return (
    <div className="flex items-center gap-2 text-[14px] min-w-0">
      <span className="shrink-0 text-zinc-400 dark:text-zinc-600">{icon}</span>
      <span className="text-zinc-500 dark:text-zinc-400 select-none shrink-0 font-medium">
        {label}
      </span>
      {truncated ? (
        <span className="text-zinc-600 dark:text-zinc-400 truncate">{truncated}</span>
      ) : null}
      {isRunning ? (
        <Loader2 className="w-3.5 h-3.5 text-cyan-500 animate-spin ml-1 shrink-0" />
      ) : null}
    </div>
  );
}

function ToolLine({
  invocation,
}: {
  invocation: Extract<GroupedEvent, { kind: "tool_invocation" }>;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const provider = classifyAgentTool(invocation.tool);
  const actionLabel = toolActionLabel(invocation.tool);
  const label = displayAgentToolName(invocation.tool);
  const iconClass = "w-4 h-4";
  const isRunning = invocation.status === "running";
  const summary = getInlineSummary(invocation.tool, invocation.args);
  const output = invocation.result?.output;

  const parsedResults = resolveSearchResults(invocation.tool, {
    output,
    resultSummary: invocation.result?.resultSummary,
  });
  const searchQuery =
    typeof invocation.args.query === "string"
      ? invocation.args.query
      : typeof invocation.args.q === "string"
        ? invocation.args.q
        : null;

  // ── Skill ──
  if (provider === "skill") {
    return (
      <ToolLogLine
        icon={<BookOpen className={iconClass} />}
        label={actionLabel}
        detail={summary}
        isRunning={isRunning}
      />
    );
  }

  // ── Workers ──
  if (provider === "worker") {
    const WorkerIcon =
      invocation.tool === "desktop_worker" ? Eye : TerminalIcon;
    return (
      <ToolLogLine
        icon={<WorkerIcon className={iconClass} />}
        label={actionLabel}
        detail={summary}
        isRunning={isRunning}
      />
    );
  }

  // ── Subagents ──
  if (provider === "subagent") {
    return (
      <ToolLogLine
        icon={<Bot className={iconClass} />}
        label={actionLabel}
        detail={summary}
        isRunning={isRunning}
      />
    );
  }

  // ── C1 / artifacts (card renders outside the log accordion) ──
  if (invocation.tool === "render_ui") {
    return (
      <ToolLogLine
        icon={<LayoutGrid className={iconClass} />}
        label={actionLabel}
        detail={summary || "visual component"}
        isRunning={isRunning}
      />
    );
  }

  // ── Document generation tools: short log + collapsed JSON (card comes from artifact_created) ──
  if (DOC_ARTIFACT_TOOLS.has(invocation.tool)) {
    const fromResult = artifactFromToolResult(
      invocation.tool,
      invocation.result?.output,
    );
    const detail =
      summary ||
      fromResult?.title ||
      (isRunning ? "generating…" : "document");
    return (
      <div className="flex flex-col gap-1.5 max-w-xl">
        <ToolLogLine
          icon={<FileText className={iconClass} />}
          label={actionLabel}
          detail={detail}
          isRunning={isRunning}
        />
        {!isRunning && (Object.keys(invocation.args).length > 0 || !!output) && (
          <details className="ml-6 text-[12px] text-zinc-500">
            <summary className="cursor-pointer select-none hover:text-zinc-300">
              Details
            </summary>
            <div className="mt-2 rounded-xl border border-zinc-200 dark:border-zinc-800 overflow-hidden">
              {Object.keys(invocation.args).length > 0 && (
                <div className="px-3 py-2">
                  <div className="text-[11px] text-zinc-400 mb-1 font-medium">Input</div>
                  <pre className="text-[11px] font-mono text-zinc-600 dark:text-zinc-400 whitespace-pre-wrap break-words max-h-32 overflow-y-auto">
                    {JSON.stringify(invocation.args, null, 2)}
                  </pre>
                </div>
              )}
              {output && (
                <div className="px-3 py-2 border-t border-zinc-100 dark:border-zinc-800/60">
                  <div className="text-[11px] text-zinc-400 mb-1 font-medium">Output</div>
                  <pre className="text-[11px] font-mono text-zinc-600 dark:text-zinc-400 whitespace-pre-wrap break-words max-h-32 overflow-y-auto">
                    {output.length > 500 ? output.slice(0, 500) + "\n..." : output}
                  </pre>
                </div>
              )}
            </div>
          </details>
        )}
      </div>
    );
  }

  if (invocation.tool === "ask_user") {
    return (
      <ToolLogLine
        icon={<MessageSquare className={iconClass} />}
        label={actionLabel}
        detail={summary}
        isRunning={isRunning}
      />
    );
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

  // ── Files ──
  if (provider === "file") {
    const fileLabel =
      invocation.tool === "write_workspace_file"
        ? "Writing file"
        : invocation.tool === "list_workspace_files"
          ? "Listing files"
          : "Reading file";
    const path = summary || "file";
    const truncated = path.length > 60 ? "..." + path.slice(-57) : path;
    return (
      <div className="flex items-center gap-2 text-[14px] font-mono min-w-0">
        <FileText className="w-4 h-4 text-zinc-400 dark:text-zinc-600 shrink-0" />
        <span className="text-zinc-400 dark:text-zinc-500 select-none shrink-0">{fileLabel}</span>
        <span className="text-zinc-600 dark:text-zinc-400 truncate">{truncated}</span>
        {isRunning && <Loader2 className="w-3.5 h-3.5 text-cyan-500 animate-spin ml-1 shrink-0" />}
      </div>
    );
  }

  // ── Web search with results ──
  if (parsedResults) {
    return (
      <WebSearchCard
        query={searchQuery}
        results={parsedResults}
        isRunning={isRunning}
      />
    );
  }

  // ── Web browser tool (no parsed results) ──
  if (provider === "browser") {
    return (
      <WebSearchCard
        query={searchQuery || summary}
        results={[]}
        isRunning={isRunning}
      />
    );
  }

  // ── Workflow / generic tool with expandable detail card ──
  const hasDetails = Object.keys(invocation.args).length > 0 || !!output;

  return (
    <div className="flex flex-col gap-2">
      <button
        onClick={() => hasDetails && setDetailsOpen(!detailsOpen)}
        className={`flex items-center gap-2 text-[14px] min-w-0 text-left ${hasDetails ? "cursor-pointer" : "cursor-default"}`}
      >
        {getToolIcon(provider, "w-4 h-4 text-zinc-400 dark:text-zinc-600 shrink-0")}
        <span className="text-zinc-500 dark:text-zinc-400 select-none shrink-0 font-medium">
          {actionLabel}
        </span>
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
