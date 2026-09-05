/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useMemo, useRef, useEffect, useState, memo, type ReactNode } from "react";
import { StreamingText } from "@/components/streaming-text";
import { PermissionCard } from "@/components/permission-card";
import {
  ActivityChip,
  ActivityNode,
  ActivityRail,
  ActivityRow,
  ActivityBlockRow,
  ActivitySummaryChips,
  Chevron,
  ElicitationUI,
  ThinkingReasoning,
  ThinkingState,
  WebSearchCard,
  formatAgentName,
  formatDuration,
  getAgentIcon,
  getToolIcon,
  hasRealReasoning,
  type ActivityStatus,
  type SummaryChip,
} from "@/components/agent-ui";
import {
  collectSearchRefsFromEventSegments,
  resolveSearchResults,
  type SearchCiteRef,
} from "@/lib/search-result-utils";
import { CocomputerMark } from "@/components/brand/cocomputer-logo";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  ArrowLeftRight,
  BookOpen,
  Bot,
  Calendar,
  Check,
  ChevronDown,
  Clipboard,
  Eye,
  ExternalLink,
  FileText,
  Globe,
  Layers,
  LayoutGrid,
  MessageSquare,
  RotateCw,
  Terminal as TerminalIcon,
  Wrench,
  X,
} from "lucide-react";
import {
  classifyAgentTool,
  displayAgentToolName,
  formatGroupedToolLabel,
  toolActionLabel,
} from "@/lib/agent-tool-classification";
import {
  groupTurnEvents,
  type GenerativeUiSegment,
  type ArtifactCreatedSegment,
  type AppPreviewSegment,
  type CanvasDocumentSegment,
  type TemplateDraftSegment,
  type TaskGroup,
  type GroupedEvent,
} from "@/lib/turn-event-grouper";
import { GenerativeUICard } from "@/components/generative-ui-card";
import { TemplateDraftCard, type TemplateDraftCardValue } from "@/components/session/template-draft-card";
import { ArtifactAttachmentCard } from "@/components/artifacts";
import { CanvasHandleCard } from "@/components/session/canvas-handle-card";
import { useSessionCanvas } from "@/lib/session-canvas-context";
import type { SessionCanvasDocument, SessionCanvasKind } from "@/lib/session-canvas";
import {
  DOC_ARTIFACT_TOOLS,
  artifactFromToolResult,
} from "@/lib/artifact-url";
import type { RunArtifact, UploadedInputFile } from "@/lib/message-types";
import { userVisibleCaption } from "@/lib/session-utils";
import { UploadedFilePreviewList } from "@/components/session/message-attachments";
import { cx } from "@/utils/cx";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type ChatItem =
  | { kind: "message"; role: "user" | "agent"; text: string; ts: number; attachments?: UploadedInputFile[] }
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
      risk?: string;
      action_hash?: string;
      tool?: string;
      decided_at?: number;
      ts: number;
    }
  | { kind: "delegation"; from: string; to: string; ts: number }
  | {
      kind: "elicitation";
      elicitation_id: string;
      question_id?: string;
      mode?: "choice" | "suggestion";
      question?: string;
      options?: string[];
      allow_free_text?: boolean;
      title?: string;
      items?: Array<{ name: string; description: string; action_label?: string }>;
      answer?: string;
      answered?: boolean;
      timedOut?: boolean;
      timeout_seconds?: number;
      ts: number;
    }
  | {
      kind: "user_question";
      question_id: string;
      question: string;
      options?: string[];
      answer?: string;
      answered?: boolean;
      timedOut?: boolean;
      timeout_seconds?: number;
      ts: number;
    };

type Props = {
  items: ChatItem[];
  isThinking: boolean;
  phase?: "idle" | "listening" | "thinking" | "acting" | "done";
  /** Live server status (e.g. "Reconnected — still working...") shown instead of
   * the generic phase label, so background work is visible in the chat itself
   * rather than only on the desktop tab. */
  statusLabel?: string;
  onPermissionRespond: (
    taskId: string,
    approved: boolean,
    approvalId?: string,
    durableTaskId?: string,
  ) => void;
  onQuestionRespond?: (questionId: string, answer: string) => void;
  onElicitationRespond?: (elicitationId: string, answer: string) => void;
  onTemplateDraftChange?: (patch: TemplateDraftCardValue) => void;
  onAppPreviewOpen?: (preview: {
    url: string;
    title?: string;
    port?: number;
    workspace_path?: string;
  }) => void;
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
  questions: (
    | Extract<ChatItem, { kind: "user_question" }>
    | Extract<ChatItem, { kind: "elicitation" }>
  )[];
};

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
  if (typeof args.relative_path === "string" && args.relative_path) return args.relative_path;
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
  | { kind: "app_preview"; data: AppPreviewSegment; ts: number }
  | { kind: "canvas_document"; data: CanvasDocumentSegment; ts: number }
  | { kind: "template_draft"; data: TemplateDraftSegment; ts: number }
  | { kind: "agentMessage"; text: string; ts: number }
  | { kind: "permission"; data: Extract<ChatItem, { kind: "permission" }>; ts: number }
  | { kind: "elicitation"; data: Extract<ChatItem, { kind: "elicitation" }>; ts: number }
  | { kind: "user_question"; data: Extract<ChatItem, { kind: "user_question" }>; ts: number };

/* ------------------------------------------------------------------ */
/*  Main exported component                                            */
/* ------------------------------------------------------------------ */

export const UnifiedChatPanel = memo(function UnifiedChatPanel({
  items,
  isThinking,
  phase = "idle",
  statusLabel,
  onPermissionRespond,
  onQuestionRespond,
  onElicitationRespond,
  onTemplateDraftChange,
  onAppPreviewOpen,
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
  }, [items, isThinking, phase]);

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
      } else if (item.kind === "user_question" || item.kind === "elicitation") {
        currentTurn.questions.push(item);
      }
    }
    grouped.push(currentTurn);
    return grouped.filter(hasContent);
  }, [items]);

  // "acting" is real work too (tool calls, a durable worker we re-attached to).
  // Treating only "thinking" as busy is why a background run could look idle.
  const isBusy = isThinking || phase === "thinking" || phase === "acting";

  const phaseLabel = statusLabel?.trim()
    ? statusLabel.trim()
    : phase === "thinking" ? "Thinking…"
    : phase === "acting" ? "Working through..."
    : phase === "listening" ? "Listening..."
    : "Generating...";

  // Hide bottom ThinkingState when the last active task group already shows ThinkingReasoning.
  const showPhaseShimmer = useMemo(() => {
    if (!isBusy || turns.length === 0) return false;
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
  }, [isBusy, turns]);

  return (
    <div className="relative h-full bg-background-full transition-colors">
      <div
        ref={scrollRef}
        className={`overflow-y-auto h-full custom-scrollbar flex flex-col px-2 pt-8 ${
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
              const isWorking = isLastTurn && isBusy;
              return (
                <TurnBlock
                  key={turn.id}
                  turn={turn}
                  isWorking={isWorking}
                  isLastTurn={isLastTurn}
                  onPermissionRespond={onPermissionRespond}
                  onQuestionRespond={onQuestionRespond}
                  onElicitationRespond={onElicitationRespond}
                  onTemplateDraftChange={onTemplateDraftChange}
                  onAppPreviewOpen={onAppPreviewOpen}
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
                className="flex items-center gap-2 py-2 mt-2"
              >
                <CocomputerMark size={16} className="size-4 rounded-md" />
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
        <div className="absolute inset-x-0 bottom-0 z-20 bg-background-full px-2 pt-1 pb-2">
          <AnimatePresence>
            {userScrolledUp && (
              <motion.button
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 10 }}
                onClick={scrollToBottom}
                className="mx-auto mb-2 flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-background-primary-default border border-card-border shadow-lg text-[12px] font-medium text-text-secondary hover:text-text-primary transition-colors"
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
            className="absolute bottom-6 left-1/2 -translate-x-1/2 z-30 flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-background-primary-default border border-card-border shadow-lg text-[12px] font-medium text-text-secondary hover:text-text-primary transition-colors"
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
  onPermissionRespond,
  onQuestionRespond,
  onElicitationRespond,
  onTemplateDraftChange,
  onAppPreviewOpen,
}: {
  turn: Turn;
  isWorking: boolean;
  isLastTurn: boolean;
  onPermissionRespond: Props["onPermissionRespond"];
  onQuestionRespond?: Props["onQuestionRespond"];
  onElicitationRespond?: Props["onElicitationRespond"];
  onTemplateDraftChange?: Props["onTemplateDraftChange"];
  onAppPreviewOpen?: Props["onAppPreviewOpen"];
}) {
  // Build an interleaved timeline from event segments + messages + cards.
  // Permissions are folded into the log grouper as synthetic approval events
  // so the activity timeline shows them alongside tool calls (not just as a
  // detached card). The full card still renders in the interleaved timeline.
  const eventSegments = useMemo(() => {
    const approvalEvents: Array<Record<string, unknown> & { type: string; ts: number }> = [];
    for (const perm of turn.permissions) {
      approvalEvents.push({
        type: "permission_request",
        ts: perm.ts,
        task_id: perm.task_id,
        approval_id: perm.approval_id ?? perm.task_id,
        description: perm.description,
        agent: perm.agent,
        risk: perm.risk,
        tool: perm.tool,
        action_hash: perm.action_hash,
        estimated_seconds: perm.estimated_seconds,
      });
      if (perm.resolved && perm.decision) {
        approvalEvents.push({
          type: "approval_resolved",
          ts: (perm.decided_at ?? perm.ts) + 1,
          task_id: perm.task_id,
          approval_id: perm.approval_id ?? perm.task_id,
          approved: perm.decision === "approved",
          status: perm.decision,
          action_hash: perm.action_hash,
        });
      }
    }
    const combined = [...turn.events, ...approvalEvents].sort((a, b) => a.ts - b.ts);
    return groupTurnEvents(combined);
  }, [turn.events, turn.permissions]);

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
      } else if (seg.kind === "app_preview") {
        items.push({ kind: "app_preview", data: seg, ts: seg.ts });
      } else if (seg.kind === "canvas_document") {
        items.push({ kind: "canvas_document", data: seg, ts: seg.ts });
      } else if (seg.kind === "template_draft") {
        items.push({ kind: "template_draft", data: seg, ts: seg.ts });
      }
    }
    for (const msg of turn.agentMessages) {
      items.push({ kind: "agentMessage", text: msg.text, ts: msg.ts });
    }
    for (const perm of turn.permissions) {
      items.push({ kind: "permission", data: perm, ts: perm.ts });
    }
    for (const question of turn.questions) {
      if (question.kind === "elicitation") {
        items.push({ kind: "elicitation", data: question, ts: question.ts });
      } else {
        items.push({ kind: "user_question", data: question, ts: question.ts });
      }
    }

    items.sort((a, b) => a.ts - b.ts);
    return items;
  }, [eventSegments, turn.agentMessages, turn.permissions, turn.questions]);

  return (
    <div className="flex flex-col gap-5 w-full">
      {turn.userMessage && (
        <UserMessageCard
          text={turn.userMessage.text}
          attachments={turn.userMessage.attachments}
        />
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
            <div
              key={`genui-${item.data.ts}-${idx}`}
              className="w-full py-1"
            >
              <GenerativeUICard
                title={item.data.title}
                componentType={item.data.component_type}
                component={item.data.component}
              />
            </div>
          );
        }

        if (item.kind === "template_draft") {
          const fields = Array.isArray(item.data.input_fields)
            ? item.data.input_fields
            : [];
          return (
            <div
              key={`template-draft-${item.data.template_id}`}
              className="w-full py-1"
            >
              <TemplateDraftCard
                value={{
                  template_id: item.data.template_id,
                  status: item.data.status,
                  name: item.data.name,
                  description: item.data.description,
                  instructions: item.data.instructions,
                  input_fields: fields as TemplateDraftCardValue["input_fields"],
                  dismissed: item.data.dismissed,
                }}
                onChange={(patch) =>
                  onTemplateDraftChange?.({
                    template_id: item.data.template_id,
                    status: item.data.status,
                    name: item.data.name,
                    description: item.data.description,
                    instructions: item.data.instructions,
                    input_fields: fields as TemplateDraftCardValue["input_fields"],
                    dismissed: item.data.dismissed,
                    ...patch,
                  })
                }
              />
            </div>
          );
        }

        if (item.kind === "artifact_created") {
          const raw = item.data.artifact;
          const artifact = coerceRunArtifact(raw);
          if (!artifact) return null;
          return (
            <div
              key={`artifact-${artifact.artifact_id}-${idx}`}
              className="w-full max-w-xl py-1"
            >
              <ArtifactAttachmentCard artifact={artifact} compact />
            </div>
          );
        }

        if (item.kind === "app_preview") {
          return (
            <div
              key={`app-preview-${item.data.url}-${idx}`}
              className="w-full max-w-xl py-1"
            >
              <AppPreviewChatCard
                preview={item.data}
                onOpen={onAppPreviewOpen}
              />
            </div>
          );
        }

        if (item.kind === "canvas_document") {
          const doc = coerceCanvasDocument(item.data.document);
          if (!doc) return null;
          return (
            <div
              key={`canvas-doc-${doc.id}-${idx}`}
              className="w-full max-w-xl py-1"
            >
              <CanvasDocumentHandleCard document={doc} />
            </div>
          );
        }

        if (item.kind === "agentMessage") {
          const msgIdx = turn.agentMessages.findIndex(m => m.ts === item.ts);
          const isLastMsg = isLastTurn && msgIdx === turn.agentMessages.length - 1;
          const shouldStream = isLastMsg && isWorking;
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
            <div key={`perm-${idx}`} className="py-1">
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
                risk={item.data.risk}
                actionHash={item.data.action_hash}
                tool={item.data.tool}
                decidedAt={item.data.decided_at}
                onRespond={onPermissionRespond}
              />
            </div>
          );
        }

        if (item.kind === "elicitation") {
          return (
            <div key={`elicitation-${item.data.elicitation_id}`} className="py-1">
              <ElicitationUI
                elicitationId={item.data.elicitation_id}
                mode={item.data.mode || "choice"}
                question={item.data.question}
                options={item.data.options}
                allowFreeText={item.data.allow_free_text}
                title={item.data.title}
                items={item.data.items}
                answer={item.data.answer}
                answered={item.data.answered}
                timedOut={item.data.timedOut}
                timeoutSeconds={item.data.timeout_seconds}
                issuedAt={item.data.ts}
                onRespond={onElicitationRespond || onQuestionRespond}
              />
            </div>
          );
        }

        if (item.kind === "user_question") {
          return (
            <div key={`question-${item.data.question_id}`} className="py-1">
              <ElicitationUI
                elicitationId={item.data.question_id}
                mode="choice"
                question={item.data.question}
                options={item.data.options}
                answer={item.data.answer}
                answered={item.data.answered}
                timedOut={item.data.timedOut}
                timeoutSeconds={item.data.timeout_seconds}
                issuedAt={item.data.ts}
                onRespond={onElicitationRespond || onQuestionRespond}
              />
            </div>
          );
        }

        return null;
      })}
    </div>
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

function coerceCanvasKind(value: unknown): SessionCanvasKind | null {
  if (value === "plan" || value === "file" || value === "document") return value;
  return null;
}

function coerceCanvasDocument(raw: Record<string, unknown>): SessionCanvasDocument | null {
  const id = typeof raw.id === "string" ? raw.id : null;
  const kind = coerceCanvasKind(raw.kind);
  if (!id || !kind) return null;
  const artifactRaw =
    raw.artifact && typeof raw.artifact === "object"
      ? coerceRunArtifact(raw.artifact as Record<string, unknown>)
      : undefined;
  return {
    id,
    kind,
    title: typeof raw.title === "string" ? raw.title : "Untitled",
    artifact: artifactRaw || undefined,
    markdown: typeof raw.markdown === "string" ? raw.markdown : undefined,
    path: typeof raw.path === "string" ? raw.path : undefined,
  };
}

function CanvasDocumentHandleCard({ document }: { document: SessionCanvasDocument }) {
  const canvas = useSessionCanvas();
  return (
    <CanvasHandleCard
      kind={document.kind}
      title={document.title}
      subtitle={document.path || document.title}
      artifact={document.artifact}
      onOpen={() => canvas?.openDocument(document, "user")}
    />
  );
}

/* ------------------------------------------------------------------ */
/*  User Message                                                       */
/* ------------------------------------------------------------------ */

function UserMessageCard({
  text,
  attachments = [],
}: {
  text: string;
  attachments?: UploadedInputFile[];
}) {
  const caption = userVisibleCaption(text);
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    const copyText = caption || attachments.map((file) => file.name).filter(Boolean).join(", ");
    if (!copyText) return;
    try {
      await navigator.clipboard.writeText(copyText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // clipboard error
    }
  };

  if (!caption && attachments.length === 0) {
    return null;
  }

  return (
    <div className="group/user-msg relative flex w-full justify-end py-1">
      <div className="flex max-w-[85%] flex-col items-end gap-2">
        {attachments.length > 0 ? (
          <UploadedFilePreviewList files={attachments} align="end" />
        ) : null}

        {caption ? (
          <div className="relative flex items-center gap-2">
            <button
              type="button"
              aria-label={copied ? "Copied" : "Copy prompt"}
              title={copied ? "Copied" : "Copy prompt"}
              onClick={() => void handleCopy()}
              className="flex size-7 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-background-primary-default text-text-tertiary opacity-0 shadow-sm transition-all duration-150 group-hover/user-msg:opacity-100 hover:border-border-button-hover hover:bg-background-secondary-hover hover:text-text-primary focus-visible:opacity-100"
            >
              {copied ? (
                <Check className="size-3.5 text-emerald-500" aria-hidden />
              ) : (
                <Clipboard className="size-3.5" aria-hidden />
              )}
            </button>

            <div className="rounded-2xl border border-card-border bg-background-secondary-default px-5 py-3 text-[15px] leading-relaxed text-text-primary shadow-sm">
              {caption}
            </div>
          </div>
        ) : null}
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
    <div className="flex flex-col items-start w-full">
      <div className="w-full text-[15px] leading-[1.75] font-medium text-text-primary">
        <StreamingText text={text} isStreaming={stream} extraSources={extraSources} />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Thought Accordion                                                  */
/* ------------------------------------------------------------------ */

type ToolInvocationStep = Extract<GroupedEvent, { kind: "tool_invocation" }>;

function invocationDurationMs(invocation: ToolInvocationStep): number | undefined {
  if (typeof invocation.result?.latencyMs === "number" && invocation.result.latencyMs > 0) {
    return invocation.result.latencyMs;
  }
  if (invocation.result?.ts) {
    const delta = invocation.result.ts - invocation.callTs;
    return delta > 0 ? delta : undefined;
  }
  return undefined;
}

function invocationStatus(invocation: ToolInvocationStep): ActivityStatus {
  if (invocation.status === "running") return "running";
  if (invocation.status === "failed") return "failed";
  return "ok";
}

function invocationChips(invocation: ToolInvocationStep) {
  const errorCode = invocation.result?.errorCode;
  const retryReason = invocation.result?.retryReason;
  if (!errorCode && !retryReason) return undefined;
  return (
    <>
      {errorCode ? (
        <ActivityChip tone="danger" mono>
          {errorCode}
        </ActivityChip>
      ) : null}
      {retryReason ? <ActivityChip tone="warning">{retryReason}</ActivityChip> : null}
    </>
  );
}

function buildSummaryChips(task: TaskGroup): SummaryChip[] {
  const iconClass = "size-3";
  let fileCount = 0;
  let ranCount = 0;
  let fetchedCount = 0;
  let skillCount = 0;
  let workerCount = 0;
  let subagentCount = 0;
  let otherCount = 0;

  for (const step of task.steps) {
    if (step.kind !== "tool_invocation") continue;
    const provider = classifyAgentTool(step.tool);
    if (provider === "skill") skillCount++;
    else if (provider === "worker") workerCount++;
    else if (provider === "subagent") subagentCount++;
    else if (provider === "file") fileCount++;
    else if (provider === "terminal") ranCount++;
    else if (provider === "browser") fetchedCount++;
    else otherCount++;
  }

  const chips: SummaryChip[] = [];
  const handoffCount = task.steps.filter((s) => s.kind === "delegation").length;
  if (handoffCount > 0) {
    chips.push({
      key: "handoff",
      icon: <ArrowLeftRight className={iconClass} />,
      count: handoffCount,
      label: handoffCount === 1 ? "Handoff" : `${handoffCount} handoffs`,
    });
  }
  const approvalCount = task.steps.filter((s) => s.kind === "approval").length;
  if (approvalCount > 0) {
    chips.push({
      key: "approval",
      icon: <Check className={iconClass} />,
      count: approvalCount,
      label: approvalCount === 1 ? "1 approval" : `${approvalCount} approvals`,
    });
  }
  if (skillCount > 0) {
    chips.push({
      key: "skill",
      icon: <BookOpen className={iconClass} />,
      count: skillCount,
      label: skillCount === 1 ? "1 skill" : `${skillCount} skills`,
    });
  }
  if (workerCount > 0) {
    chips.push({
      key: "worker",
      icon: <Layers className={iconClass} />,
      count: workerCount,
      label: workerCount === 1 ? "1 worker" : `${workerCount} workers`,
    });
  }
  if (subagentCount > 0) {
    chips.push({
      key: "subagent",
      icon: <Bot className={iconClass} />,
      count: subagentCount,
      label: subagentCount === 1 ? "1 subagent" : `${subagentCount} subagents`,
    });
  }
  if (fileCount > 0) {
    chips.push({
      key: "files",
      icon: <FileText className={iconClass} />,
      count: fileCount,
      label: fileCount === 1 ? "1 file" : `${fileCount} files`,
    });
  }
  if (ranCount > 0) {
    chips.push({
      key: "terminal",
      icon: <TerminalIcon className={iconClass} />,
      count: ranCount,
      label: ranCount === 1 ? "1 command" : `${ranCount} commands`,
    });
  }
  if (fetchedCount > 0) {
    chips.push({
      key: "web",
      icon: <Globe className={iconClass} />,
      count: fetchedCount,
      label: fetchedCount === 1 ? "1 web lookup" : `${fetchedCount} web lookups`,
    });
  }
  if (otherCount > 0) {
    chips.push({
      key: "tools",
      icon: <Wrench className={iconClass} />,
      count: otherCount,
      label: otherCount === 1 ? "1 tool" : `${otherCount} tools`,
    });
  }
  const errorCount = task.steps.reduce(
    (n, s) => n + (s.kind === "error" ? s.count : 0),
    0,
  );
  if (errorCount > 0) {
    chips.push({
      key: "errors",
      icon: <AlertTriangle className={iconClass} />,
      count: errorCount,
      label: errorCount === 1 ? "1 error" : `${errorCount} errors`,
      tone: "danger",
    });
  }
  return chips;
}

function ThoughtAccordion({
  task,
  isActive,
}: {
  task: TaskGroup;
  isActive: boolean;
}) {
  const [expanded, setExpanded] = useState(true);
  const [now, setNow] = useState(() => Date.now());
  const chips = useMemo(() => buildSummaryChips(task), [task]);

  useEffect(() => {
    if (!isActive) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [isActive]);

  // Merge ALL thinking steps into one reasoning row, and group consecutive
  // identical tool invocations into counted rows (e.g. "Read 7 emails").
  const displayRows = useMemo(() => {
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
  const hasToolSteps =
    displayRows.some((r) => r.kind === "step" || r.kind === "tool_group") ||
    task.steps.some((s) => s.kind === "delegation");
  const hasRunningTool = task.steps.some(
    (s) =>
      (s.kind === "tool_invocation" && s.status === "running") ||
      (s.kind === "approval" && s.decision === "pending"),
  );
  const hasFailed =
    task.status === "failed" ||
    task.steps.some(
      (s) =>
        s.kind === "error" ||
        (s.kind === "tool_invocation" && s.status === "failed") ||
        (s.kind === "approval" && s.decision === "denied"),
    );
  const headerStatus: ActivityStatus = isActive || hasRunningTool
    ? "running"
    : hasFailed
      ? "failed"
      : "ok";
  const elapsedMs = Math.max(0, (isActive ? now : task.endTs) - task.ts);
  const elapsedLabel = formatDuration(elapsedMs) || "0s";

  return (
    <div className="flex w-full max-w-xl flex-col gap-2">
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
            className="group/summary flex w-full items-center gap-2.5 py-0.5 text-left select-none"
            onClick={() => setExpanded(!expanded)}
            aria-expanded={expanded}
          >
            <ActivityNode status={headerStatus} />
            <span
              className={cx(
                "shrink-0 text-body-medium",
                isActive || hasRunningTool
                  ? "agent-progress-loading-text"
                  : "text-text-secondary",
              )}
            >
              {isActive || hasRunningTool ? (
                "Working…"
              ) : (
                <>
                  Worked for <span className="text-text-primary">{elapsedLabel}</span>
                </>
              )}
            </span>
            <span className="min-w-0 flex-1" />
            <ActivitySummaryChips chips={chips} />
            <Chevron
              open={expanded}
              className="shrink-0 text-foreground-icon-tertiary"
            />
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
                <ActivityRail className="pt-1 pb-1">
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
                </ActivityRail>
              </motion.div>
            )}
          </AnimatePresence>
        </>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Step Row dispatcher                                                */
/* ------------------------------------------------------------------ */

function ApprovalLogLine({
  item,
}: {
  item: Extract<GroupedEvent, { kind: "approval" }>;
}) {
  const label =
    item.decision === "approved"
      ? "Approved"
      : item.decision === "denied"
        ? "Denied"
        : item.decision === "timed_out"
          ? "Approval timed out"
          : "Awaiting approval";
  const status =
    item.decision === "denied"
      ? "failed"
      : item.decision === "pending"
        ? "running"
        : "ok";
  const detail = item.description
    ? item.description.length > 140
      ? `${item.description.slice(0, 140)}…`
      : item.description
    : undefined;
  const durationMs =
    item.decidedAt && item.decidedAt > item.ts ? item.decidedAt - item.ts : undefined;
  return (
    <ActivityRow
      status={status as ActivityStatus}
      icon={
        item.decision === "denied" ? (
          <X className="size-3.5" />
        ) : (
          <Check className="size-3.5" />
        )
      }
      label={label}
      detail={detail}
      durationMs={durationMs}
      chips={
        <>
          {item.tool ? (
            <ActivityChip tone="neutral">{item.tool.replace(/_/g, " ")}</ActivityChip>
          ) : null}
          {item.risk ? <ActivityChip tone="warning">{`risk: ${item.risk}`}</ActivityChip> : null}
        </>
      }
    />
  );
}

function StepRow({ item }: { item: GroupedEvent }) {
  if (item.kind === "tool_invocation") return <ToolLine invocation={item} />;
  if (item.kind === "screenshot") return <ScreenshotCard item={item} />;
  if (item.kind === "approval") return <ApprovalLogLine item={item} />;
  if (item.kind === "error") {
    return <ErrorLine message={item.message} code={item.code} count={item.count} />;
  }
  if (item.kind === "delegation") return <HandoffLogLine from={item.from} to={item.to} />;
  if (item.kind === "retry") {
    const badge = item.nextModel
      ? `${item.model || "model"} → ${item.nextModel}`
      : item.attempt != null
        ? `attempt ${item.attempt}`
        : undefined;
    return (
      <ActivityRow
        status="retry"
        icon={<RotateCw className="size-3.5" />}
        label="Retry"
        detail={item.reason}
        durationMs={item.delayMs}
        chips={badge ? <ActivityChip tone="warning">{badge}</ActivityChip> : undefined}
      />
    );
  }
  if (item.kind === "bg_progress") {
    const suffix =
      typeof item.progress === "number" ? ` (${item.progress}%)` : "";
    return (
      <ProgressStatusLine
        message={`${item.message}${suffix}`}
        failed={item.complete && item.success === false}
        complete={item.complete}
      />
    );
  }
  if (item.kind === "subagent_status") {
    const label = item.role ? `${item.role}: ${item.detail}` : item.detail;
    return (
      <ProgressStatusLine
        message={label}
        failed={item.status === "failed"}
        complete={item.status === "completed"}
      />
    );
  }
  return null;
}

function ToolGroupLine({
  tool,
  items,
}: {
  tool: string;
  items: ToolInvocationStep[];
}) {
  const [open, setOpen] = useState(false);
  const provider = classifyAgentTool(tool);
  const isRunning = items.some((item) => item.status === "running");
  const isFailed = items.some((item) => item.status === "failed");
  const label = formatGroupedToolLabel(tool, items.length);
  const durationMs = items.reduce((sum, item) => sum + (invocationDurationMs(item) ?? 0), 0);
  const icon = tool.startsWith("schedules_")
    ? <Calendar className="size-3.5" />
    : getToolIcon(provider, "size-3.5");

  return (
    <>
      <ActivityRow
        status={isRunning ? "running" : isFailed ? "failed" : "ok"}
        icon={icon}
        label={label}
        count={items.length}
        durationMs={durationMs}
        expandable
        expanded={open}
        onToggle={() => setOpen((value) => !value)}
        tone={isFailed && !isRunning ? "danger" : "default"}
      />
      {open
        ? items.map((item) => (
            <ToolLine key={`${item.tool}-${item.callTs}`} invocation={item} />
          ))
        : null}
    </>
  );
}

function ToolDetailsPanel({
  title,
  args,
  output,
}: {
  title: string;
  args: Record<string, unknown>;
  output?: string;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-separator-border bg-background-secondary-default/50">
      <div className="border-b border-separator-border px-3 py-2 text-caption-1-medium text-text-secondary">
        {title}
      </div>
      {Object.keys(args).length > 0 ? (
        <div className="px-3 py-2">
          <div className="mb-1 text-caption-2-medium text-text-tertiary">Input</div>
          <pre className="max-h-32 overflow-y-auto whitespace-pre-wrap break-words font-mono text-caption-2-regular text-text-secondary">
            {JSON.stringify(args, null, 2)}
          </pre>
        </div>
      ) : null}
      {output ? (
        <div className="border-t border-separator-border px-3 py-2">
          <div className="mb-1 text-caption-2-medium text-text-tertiary">Output</div>
          <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap break-words font-mono text-caption-2-regular text-text-secondary">
            {output.length > 500 ? `${output.slice(0, 500)}\n...` : output}
          </pre>
        </div>
      ) : null}
    </div>
  );
}

function ToolLine({
  invocation,
}: {
  invocation: ToolInvocationStep;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const provider = classifyAgentTool(invocation.tool);
  const actionLabel = toolActionLabel(invocation.tool);
  const displayName = displayAgentToolName(invocation.tool);
  const isRunning = invocation.status === "running";
  const summary = getInlineSummary(invocation.tool, invocation.args);
  const output = invocation.result?.output;
  const status = invocationStatus(invocation);
  const durationMs = invocationDurationMs(invocation);
  const chips = invocationChips(invocation);
  const tone = invocation.status === "failed" ? "danger" as const : "default" as const;

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

  if (parsedResults || provider === "browser") {
    return (
      <div className="flex min-w-0 items-start gap-2.5 py-0.5">
        <ActivityNode status={status} />
        <div className="min-w-0 flex-1">
          <WebSearchCard
            query={searchQuery || summary}
            results={parsedResults || []}
            isRunning={isRunning}
          />
        </div>
      </div>
    );
  }

  let icon = invocation.tool.startsWith("schedules_")
    ? <Calendar className="size-3.5" />
    : getToolIcon(provider, "size-3.5");
  let label = actionLabel;
  let detail: string | null | undefined = summary;
  let detailMono = false;

  if (provider === "worker") {
    icon = invocation.tool === "desktop_worker"
      ? <Eye className="size-3.5" />
      : <TerminalIcon className="size-3.5" />;
  } else if (provider === "skill") {
    icon = <BookOpen className="size-3.5" />;
  } else if (provider === "subagent") {
    icon = <Bot className="size-3.5" />;
  } else if (invocation.tool === "render_ui") {
    icon = <LayoutGrid className="size-3.5" />;
    detail = summary || "visual component";
  } else if (invocation.tool === "ask_user") {
    icon = <MessageSquare className="size-3.5" />;
  } else if (DOC_ARTIFACT_TOOLS.has(invocation.tool)) {
    icon = <FileText className="size-3.5" />;
    const fromResult = artifactFromToolResult(
      invocation.tool,
      invocation.result?.output,
    );
    detail = summary || fromResult?.title || (isRunning ? "generating…" : "document");
  } else if (provider === "terminal") {
    label = "Terminal";
    detail = summary || "command";
    detailMono = true;
  } else if (provider === "file") {
    label =
      invocation.tool === "write_workspace_file"
        ? "Writing file"
        : invocation.tool === "list_workspace_files"
          ? "Listing files"
          : "Reading file";
    detail = summary || "file";
    detailMono = true;
  }

  const hasDetails =
    !isRunning &&
    (DOC_ARTIFACT_TOOLS.has(invocation.tool) || provider === "workflow" || provider === "generic" || provider === "mcp") &&
    (Object.keys(invocation.args).length > 0 || Boolean(output));

  return (
    <ActivityRow
      status={status}
      icon={icon}
      label={label}
      detail={detail && detail !== displayName ? detail : undefined}
      detailMono={detailMono}
      durationMs={durationMs}
      chips={chips}
      tone={tone}
      expandable={hasDetails}
      expanded={detailsOpen}
      onToggle={hasDetails ? () => setDetailsOpen((value) => !value) : undefined}
    >
      {hasDetails ? (
        <ToolDetailsPanel
          title={summary || displayName}
          args={invocation.args}
          output={output}
        />
      ) : null}
    </ActivityRow>
  );
}

function ErrorLine({
  message,
  code,
  count,
}: {
  message: string;
  code?: string;
  count?: number;
}) {
  return (
    <ActivityBlockRow
      status="failed"
      icon={<X className="size-3.5" />}
      label={message}
      tone="danger"
      chips={
        <>
          {count && count > 1 ? (
            <ActivityChip tone="danger">×{count}</ActivityChip>
          ) : null}
          {code ? (
            <ActivityChip tone="danger" mono>
              {code}
            </ActivityChip>
          ) : null}
        </>
      }
    />
  );
}

function ProgressStatusLine({
  message,
  failed = false,
  complete = false,
}: {
  message: string;
  failed?: boolean;
  complete?: boolean;
}) {
  const status: ActivityStatus = failed ? "failed" : complete ? "ok" : "running";
  return (
    <ActivityRow
      status={status}
      icon={<Bot className="size-3.5" />}
      label="Agent"
      detail={message}
      tone={failed ? "danger" : "default"}
    />
  );
}

function ScreenshotCard({
  item,
}: {
  item: Extract<GroupedEvent, { kind: "screenshot" }>;
}) {
  const [open, setOpen] = useState(Boolean(item.analysis || item.image_b64));
  const expandable = Boolean(item.analysis || item.image_b64);
  return (
    <ActivityRow
      status="ok"
      icon={<Eye className="size-3.5" />}
      label="Vision"
      detail={item.analysis ? "Screen analysis" : "Screenshot"}
      expandable={expandable}
      expanded={open}
      onToggle={expandable ? () => setOpen((value) => !value) : undefined}
    >
      {expandable ? (
        <div className="space-y-3">
          {item.analysis ? (
            <p className="text-body-2-regular leading-relaxed text-text-secondary">
              {item.analysis}
            </p>
          ) : null}
          {item.image_b64 ? (
            <div className="relative h-[100px] w-[160px] overflow-hidden rounded-xl border border-separator-border brightness-90 transition hover:brightness-100">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`data:image/png;base64,${item.image_b64}`}
                className="h-full w-full object-cover"
                alt="Screenshot"
              />
            </div>
          ) : null}
        </div>
      ) : null}
    </ActivityRow>
  );
}

function AppPreviewChatCard({
  preview,
  onOpen,
}: {
  preview: AppPreviewSegment;
  onOpen?: Props["onAppPreviewOpen"];
}) {
  return (
    <button
      type="button"
      onClick={() =>
        onOpen?.({
          url: preview.url,
          title: preview.title,
          port: preview.port,
          workspace_path: preview.workspacePath,
        })
      }
      className="flex w-full items-center gap-3 rounded-xl border border-card-border bg-background-secondary-default px-3 py-2.5 text-left transition-colors hover:border-border-button-hover hover:bg-background-secondary-hover"
    >
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-500">
        <Globe className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-body-2-medium text-text-primary">App preview</div>
        <div className="truncate font-mono text-caption-1-regular text-text-tertiary">
          {preview.title}
          {preview.port ? ` · :${preview.port}` : ""}
        </div>
      </div>
      <ExternalLink className="h-3.5 w-3.5 shrink-0 text-foreground-icon-tertiary" />
    </button>
  );
}

function HandoffLogLine({ from, to }: { from: string; to: string }) {
  return (
    <ActivityRow
      status="ok"
      icon={<ArrowLeftRight className="size-3.5" />}
      label="Handoff"
      detail={
        <span className="inline-flex min-w-0 items-center gap-1.5">
          <span className="inline-flex items-center gap-1">
            <span className="flex size-4 items-center justify-center rounded-md bg-indigo-500/10 text-indigo-500">
              {getAgentIcon(from, "size-2.5")}
            </span>
            <span>{formatAgentName(from)}</span>
          </span>
          <ArrowLeftRight className="size-2.5 text-foreground-icon-tertiary" />
          <span className="inline-flex items-center gap-1">
            <span className="flex size-4 items-center justify-center rounded-md bg-violet-500/10 text-violet-500">
              {getAgentIcon(to, "size-2.5")}
            </span>
            <span>{formatAgentName(to)}</span>
          </span>
        </span>
      }
    />
  );
}
