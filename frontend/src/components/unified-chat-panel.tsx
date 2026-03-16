"use client";

import { useMemo, useRef, useEffect, useState, type ReactNode } from "react";
import { ChatMarkdown } from "@/components/chat-markdown";
import { PermissionCard } from "@/components/permission-card";

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

type RenderItem =
  | { kind: "message"; item: Extract<ChatItem, { kind: "message" }> }
  | { kind: "permission"; item: Extract<ChatItem, { kind: "permission" }> }
  | { kind: "delegation"; item: Extract<ChatItem, { kind: "delegation" }> }
  | { kind: "event_group"; items: Extract<ChatItem, { kind: "event" }>[] };

/* ------------------------------------------------------------------ */
/*  CSS animation styles (injected once into <head>)                   */
/* ------------------------------------------------------------------ */

const STYLE_ID = "ucp-animations";

function injectStyles() {
  if (typeof document === "undefined") return;
  if (document.getElementById(STYLE_ID)) return;

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    @keyframes ucp-fade-in-up {
      from {
        opacity: 0;
        transform: translateY(8px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    @keyframes ucp-dot-pulse {
      0%, 80%, 100% {
        opacity: 0.3;
        transform: scale(0.8);
      }
      40% {
        opacity: 1;
        transform: scale(1.2);
      }
    }

    .ucp-fade-in {
      animation: ucp-fade-in-up 0.3s cubic-bezier(0.22, 1, 0.36, 1) both;
    }

    .ucp-dot-1 { animation: ucp-dot-pulse 1.4s ease-in-out infinite 0s; }
    .ucp-dot-2 { animation: ucp-dot-pulse 1.4s ease-in-out infinite 0.2s; }
    .ucp-dot-3 { animation: ucp-dot-pulse 1.4s ease-in-out infinite 0.4s; }
  `;
  document.head.appendChild(style);
}

/* ------------------------------------------------------------------ */
/*  Timestamp helper                                                   */
/* ------------------------------------------------------------------ */

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString([], {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
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
  const [filter, setFilter] = useState<"all" | "chat" | "logs">("all");

  // Inject CSS keyframes on mount
  useEffect(() => {
    injectStyles();
  }, []);

  // Auto-scroll to bottom when items change or thinking state changes
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, [items, isThinking, filter]);

  const renderItems = useMemo<RenderItem[]>(() => {
    const groups: RenderItem[] = [];
    let buffer: Extract<ChatItem, { kind: "event" }>[] = [];

    const flush = () => {
      if (buffer.length > 0) {
        groups.push({ kind: "event_group", items: buffer });
        buffer = [];
      }
    };

    for (const item of items) {
      if (item.kind === "event") {
        buffer.push(item);
        continue;
      }
      flush();
      if (item.kind === "message") {
        groups.push({ kind: "message", item });
      } else if (item.kind === "permission") {
        groups.push({ kind: "permission", item });
      } else if (item.kind === "delegation") {
        groups.push({ kind: "delegation", item });
      }
    }
    flush();
    return groups;
  }, [items]);

  const filteredItems = useMemo(() => {
    if (filter === "all") return renderItems;
    if (filter === "chat") {
      return renderItems.filter((item) => item.kind !== "event_group");
    }
    return renderItems.filter((item) => item.kind === "event_group");
  }, [filter, renderItems]);

  return (
    <div
      ref={scrollRef}
      className="overflow-y-auto h-full custom-scrollbar flex flex-col px-4 py-8"
    >
      <div className="mx-auto max-w-4xl w-full flex flex-col gap-2 pb-4">
        {/* Optional Filter (hidden/minimal to match clean layout) */}
        <div className="flex justify-end pb-4 opacity-50 hover:opacity-100 transition-opacity">
          <div className="flex items-center gap-1">
            {(["all", "chat", "logs"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setFilter(mode)}
                className={`px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest rounded-md transition-colors ${
                  filter === mode
                    ? "bg-zinc-200 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-200"
                    : "text-zinc-400 dark:text-zinc-500 hover:text-zinc-600 dark:hover:text-zinc-300"
                }`}
              >
                {mode}
              </button>
            ))}
          </div>
        </div>

        {filteredItems.map((item, i) => {
          if (item.kind === "event_group") {
            return (
              <div key={`event-group-${i}`} className="ucp-fade-in flex flex-col w-full">
                <EventGroupCard items={item.items} />
              </div>
            );
          }
          return (
            <div key={`${item.item.ts}-${item.kind}-${i}`} className="ucp-fade-in flex flex-col w-full">
              <ChatItemRouter
                item={item.item}
                onPermissionRespond={onPermissionRespond}
              />
            </div>
          );
        })}

        {isThinking && filter !== "logs" && (
          <div className="ucp-fade-in w-full">
            <ThinkingIndicator />
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Item router                                                        */
/* ------------------------------------------------------------------ */

function ChatItemRouter({
  item,
  onPermissionRespond,
}: {
  item: ChatItem;
  onPermissionRespond: (taskId: string, approved: boolean) => void;
}) {
  switch (item.kind) {
    case "message":
      return (
        <MessageBubble role={item.role} text={item.text} ts={item.ts} />
      );
    case "event":
      return <EventRenderer item={item} />;
    case "permission":
      return (
        <div className="py-1">
          <PermissionCard
            taskId={item.task_id}
            description={item.description}
            estimatedSeconds={item.estimated_seconds}
            agent={item.agent}
            onRespond={onPermissionRespond}
          />
        </div>
      );
    case "delegation":
      return (
        <DelegationBadge from={item.from} to={item.to} ts={item.ts} />
      );
    default:
      return null;
  }
}

/* ------------------------------------------------------------------ */
/*  Message bubbles                                                    */
/* ------------------------------------------------------------------ */

function MessageBubble({
  role,
  text,
  ts,
}: {
  role: "user" | "agent";
  text: string;
  ts: number;
}) {
  const isUser = role === "user";
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      const el = document.createElement("textarea");
      el.value = text;
      el.style.position = "fixed";
      el.style.top = "-9999px";
      document.body.appendChild(el);
      el.focus();
      el.select();
      document.execCommand("copy");
      document.body.removeChild(el);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    }
  };

  if (isUser) {
    return (
      <div className="flex w-full justify-end py-4 px-2">
        <div className="max-w-[80%] rounded-3xl bg-[#f4f4f5] dark:bg-[#212126] px-5 py-3 text-[15px] leading-relaxed text-zinc-900 dark:text-zinc-100 shadow-sm border border-zinc-200 dark:border-[#2f2f35]">
          <ChatMarkdown content={text} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-start py-4 px-2 group relative">
      <div className="flex items-center gap-3 mb-2">
        <div className="flex h-6 w-6 items-center justify-center text-zinc-800 dark:text-zinc-200">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
            <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
          </svg>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[15px] font-medium text-zinc-800 dark:text-zinc-200">
            Nexus
          </span>
          <span className="rounded-md border border-zinc-200 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-800/80 px-1.5 py-0.5 text-[10px] font-medium text-zinc-500">
            Lite
          </span>
        </div>
      </div>

      {/* Bubble text (transparent bg, normal flush left) */}
      <div className="w-full pl-9 pr-4 text-[15px] leading-relaxed text-zinc-700 dark:text-zinc-300">
        <ChatMarkdown content={text} />
      </div>

      <button
        type="button"
        onClick={handleCopy}
        className="absolute top-4 right-4 opacity-0 group-hover:opacity-100 transition-opacity text-[10px] uppercase tracking-widest font-bold px-2 py-1 rounded-md border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-[#1a1a1c] text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-200"
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Event groups (timeline style)                                      */
/* ------------------------------------------------------------------ */

function getEventGroupTitle(
  items: Extract<ChatItem, { kind: "event" }>[],
): string {
  const thinking = items.find(
    (item) => item.type === "agent_thinking" && typeof item["content"] === "string",
  );
  if (thinking && typeof thinking["content"] === "string") {
    return truncateText(thinking["content"], 64);
  }

  const toolCall = items.find((item) => item.type === "agent_tool_call");
  if (toolCall && typeof toolCall["tool"] === "string") {
    return `Running ${toolCall["tool"]}`;
  }

  const task = items.find((item) => item.type === "bg_task_progress");
  if (task && typeof task["message"] === "string") {
    return truncateText(task["message"], 64);
  }

  return "Agent activity";
}

function truncateText(text: string, max = 80) {
  if (text.length <= max) return text;
  return text.slice(0, max).trim() + "\u2026";
}

function EventGroupCard({
  items,
}: {
  items: Extract<ChatItem, { kind: "event" }>[];
}) {
  const title = getEventGroupTitle(items);
  const count = items.length;

  return (
    <div className="px-4 py-1.5 opacity-60 hover:opacity-100 transition-opacity my-1">
      <details className="bg-transparent border-none w-full outline-none [&_summary::-webkit-details-marker]:hidden" open>
        <summary className="flex items-center justify-between cursor-pointer list-none py-2 px-3 rounded-xl hover:bg-zinc-100 dark:hover:bg-zinc-800/50 transition-colors w-fit">
          <div className="flex items-center gap-3">
            <span className="w-2 h-2 rounded-full bg-zinc-400 dark:bg-zinc-600 animate-pulse" />
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                {title}
              </span>
              <span className="text-[10px] bg-zinc-200 dark:bg-zinc-800 text-zinc-500 rounded px-1.5 py-0.5">
                {count} step{count === 1 ? "" : "s"}
              </span>
            </div>
          </div>
        </summary>
        <div className="pl-6 pr-4 py-2 border-l border-zinc-200 dark:border-zinc-800 ml-4 mt-2 mb-2 flex flex-col gap-3">
          {items.map((item, index) => (
            <EventRow
              key={`${item.type}-${item.ts}-${index}`}
              item={item}
              isLast={index === items.length - 1}
            />
          ))}
        </div>
      </details>
    </div>
  );
}

function EventRow({
  item,
  isLast,
}: {
  item: Extract<ChatItem, { kind: "event" }>;
  isLast: boolean;
}) {
  const time = formatTime(item.ts);

  const base =
    "text-[11px] font-bold uppercase tracking-widest text-muted dark:text-zinc-500";

  switch (item.type) {
    case "agent_thinking":
      return (
        <TimelineRow
          isLast={isLast}
          dotClass="bg-zinc-400"
          time={time}
          label="Thinking"
          labelClass="text-zinc-300"
          content={typeof item["content"] === "string" ? item["content"] : "Thinking\u2026"}
        />
      );
    case "agent_tool_call":
      return (
        <TimelineRow
          isLast={isLast}
          dotClass="bg-cyan-400"
          time={time}
          label="Tool Call"
          labelClass="text-cyan-300"
          content={
            <div className="space-y-2">
              <div className="font-mono text-cyan-200">
                {String(item["tool"] || "tool")}
              </div>
              {item["args"] ? (
                <pre className="chat-code-block">
                  {JSON.stringify(item["args"], null, 2)}
                </pre>
              ) : (
                <div className="text-xs text-zinc-400">No args</div>
              )}
            </div>
          }
        />
      );
    case "agent_tool_result":
      return (
        <TimelineRow
          isLast={isLast}
          dotClass="bg-emerald-400"
          time={time}
          label="Tool Result"
          labelClass="text-emerald-300"
          content={
            <pre className="chat-code-block">
              {String(item["output"] || "No output")}
            </pre>
          }
        />
      );
    case "agent_screenshot":
      return (
        <TimelineRow
          isLast={isLast}
          dotClass="bg-amber-400"
          time={time}
          label="Screenshot"
          labelClass="text-amber-300"
          content={
            <div className="space-y-2">
              {typeof item["analysis"] === "string" && item["analysis"] && (
                <p className="text-xs text-zinc-400">{item["analysis"]}</p>
              )}
              {typeof item["image_b64"] === "string" && item["image_b64"] && (
                <img
                  src={`data:image/png;base64,${item["image_b64"]}`}
                  alt="Agent screenshot"
                  className="rounded-lg border border-zinc-800 max-h-64"
                />
              )}
            </div>
          }
        />
      );
    case "bg_task_progress":
      return (
        <TimelineRow
          isLast={isLast}
          dotClass="bg-amber-400"
          time={time}
          label="Background"
          labelClass="text-amber-300"
          content={
            <div className="space-y-2">
              <div className="text-xs text-zinc-300">
                {String(item["message"] || "")}
              </div>
              <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                <div
                  className="h-full bg-amber-400"
                  style={{
                    width: `${Math.min(100, Math.max(0, Number(item["progress"] ?? 0)))}%`,
                  }}
                />
              </div>
            </div>
          }
        />
      );
    case "bg_task_complete":
      return (
        <TimelineRow
          isLast={isLast}
          dotClass={item["success"] ? "bg-emerald-400" : "bg-red-400"}
          time={time}
          label={item["success"] ? "Task Done" : "Task Failed"}
          labelClass={item["success"] ? "text-emerald-300" : "text-red-300"}
          content={String(item["result"] || "")}
        />
      );
    case "agent_complete":
      return (
        <TimelineRow
          isLast={isLast}
          dotClass="bg-emerald-400"
          time={time}
          label="Complete"
          labelClass="text-emerald-300"
          content="Agent completed the task."
        />
      );
    case "voice_status":
      return (
        <TimelineRow
          isLast={isLast}
          dotClass="bg-zinc-400"
          time={time}
          label={String(item["status"] || "Voice")}
          labelClass="text-zinc-300"
          content={String(item["message"] || "")}
        />
      );
    case "error":
      return (
        <TimelineRow
          isLast={isLast}
          dotClass="bg-red-400"
          time={time}
          label="Error"
          labelClass="text-red-300"
          content={String(item["message"] || "An error occurred")}
        />
      );
    default:
      return (
        <TimelineRow
          isLast={isLast}
          dotClass="bg-zinc-500"
          time={time}
          label={item.type}
          labelClass={base}
          content={JSON.stringify(item)}
        />
      );
  }
}

function TimelineRow({
  isLast,
  dotClass,
  time,
  label,
  labelClass,
  content,
}: {
  isLast: boolean;
  dotClass: string;
  time: string;
  label: string;
  labelClass: string;
  content: ReactNode;
}) {
  return (
    <div className="chat-timeline-item">
      <div className={`chat-timeline-dot ${dotClass}`} />
      {!isLast && <div className="chat-timeline-line" />}
      <div className="min-w-0 space-y-1">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-muted dark:text-zinc-600">
            {time}
          </span>
          <span className={`text-[10px] font-bold uppercase tracking-widest ${labelClass}`}>
            {label}
          </span>
        </div>
        <div className="text-xs text-zinc-300 dark:text-zinc-400 leading-relaxed">
          {content}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Event dispatcher                                                   */
/* ------------------------------------------------------------------ */

function EventRenderer({
  item,
}: {
  item: { kind: "event"; type: string; ts: number; [key: string]: unknown };
}) {
  switch (item.type) {
    case "agent_tool_call":
      return (
        <ToolCallPill
          ts={item.ts}
          tool={item["tool"] as string}
          args={item["args"] as Record<string, unknown> | undefined}
        />
      );
    case "agent_tool_result":
      return (
        <ToolResultPill
          ts={item.ts}
          tool={item["tool"] as string}
          output={item["output"] as string}
        />
      );
    case "agent_screenshot":
      return (
        <ScreenshotItem
          ts={item.ts}
          imageB64={item["image_b64"] as string | undefined}
          analysis={item["analysis"] as string | undefined}
        />
      );
    case "agent_thinking":
      return (
        <ThinkingLine
          ts={item.ts}
          content={item["content"] as string | undefined}
        />
      );
    case "agent_complete":
      return <CompleteBadge ts={item.ts} />;
    case "voice_status":
      return (
        <VoiceStatusBadge
          ts={item.ts}
          status={item["status"] as string | undefined}
          message={item["message"] as string | undefined}
        />
      );
    case "bg_task_progress":
      return (
        <BgTaskProgressPill
          ts={item.ts}
          progress={item["progress"] as number}
          message={item["message"] as string}
        />
      );
    case "bg_task_complete":
      return (
        <BgTaskCompleteBadge
          ts={item.ts}
          success={item["success"] as boolean}
          result={item["result"] as string}
        />
      );
    case "error":
      return (
        <ErrorBadge
          ts={item.ts}
          message={item["message"] as string}
          code={item["code"] as string | undefined}
        />
      );
    default:
      return (
        <div className="py-1 px-3 text-[10px] text-zinc-600 font-mono">
          <span className="text-zinc-700 mr-2 select-none">
            [{formatTime(item.ts)}]
          </span>
          {item.type}: {JSON.stringify(item)}
        </div>
      );
  }
}

/* ------------------------------------------------------------------ */
/*  agent_tool_call  -- compact cyan pill with monospace                */
/* ------------------------------------------------------------------ */

function ToolCallPill({
  ts,
  tool,
  args,
}: {
  ts: number;
  tool: string;
  args?: Record<string, unknown>;
}) {
  const argsStr = args ? JSON.stringify(args, null, 2) : "";
  const preview = argsStr
    ? argsStr.length > 120
      ? argsStr.slice(0, 120) + "\u2026"
      : argsStr
    : "No args";

  return (
    <div className="flex items-start gap-2 py-1 px-3">
      <span className="mt-1.5 block w-2 h-2 rounded-full bg-cyan-500 shrink-0" />
      <details className="chat-details min-w-0 flex-1 rounded-lg border border-cyan-500/20 bg-cyan-500/5 px-3 py-2">
        <summary className="cursor-pointer list-none text-[11px] font-mono text-cyan-200 flex items-center gap-2">
          <span className="text-muted dark:text-zinc-700 select-none">
            {formatTime(ts)}
          </span>
          <span className="font-bold">{tool}</span>
          <span className="text-zinc-400 dark:text-zinc-500">{preview}</span>
        </summary>
        {argsStr && (
          <pre className="mt-2 text-[11px] text-zinc-300 whitespace-pre-wrap break-words">
            {argsStr}
          </pre>
        )}
      </details>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  agent_tool_result  -- compact emerald pill                         */
/* ------------------------------------------------------------------ */

function ToolResultPill({
  ts,
  tool,
  output,
}: {
  ts: number;
  tool: string;
  output: string;
}) {
  const display =
    output && output.length > 120 ? output.slice(0, 120) + "\u2026" : output || "";

  return (
    <div className="flex items-start gap-2 py-1 px-3">
      <span className="mt-1.5 block w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
      <details className="chat-details min-w-0 flex-1 rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-3 py-2">
        <summary className="cursor-pointer list-none text-[11px] font-mono text-emerald-200 flex items-center gap-2">
          <span className="text-muted dark:text-zinc-700 select-none">
            {formatTime(ts)}
          </span>
          <span className="font-bold">{tool}</span>
          <span className="text-muted dark:text-zinc-500 mx-1">&rarr;</span>
          <span className="text-zinc-400 dark:text-zinc-500 break-all">{display || "No output"}</span>
        </summary>
        {output && (
          <pre className="mt-2 text-[11px] text-zinc-300 whitespace-pre-wrap break-words">
            {output}
          </pre>
        )}
      </details>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  agent_screenshot  -- expandable thumbnail                          */
/* ------------------------------------------------------------------ */

function ScreenshotItem({
  ts,
  imageB64,
  analysis,
}: {
  ts: number;
  imageB64?: string;
  analysis?: string;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="flex items-start gap-2 py-1 px-3">
      <span className="mt-1.5 block w-2 h-2 rounded-full bg-amber-500 shrink-0" />
      <div className="min-w-0 flex-1 space-y-1">
        {/* Header line */}
        <div className="flex items-center gap-2 text-[11px]">
          <span className="text-zinc-700 select-none font-mono">
            {formatTime(ts)}
          </span>
          <span className="text-amber-500 font-black uppercase tracking-widest text-[10px]">
            Screenshot
          </span>
        </div>

        {/* Analysis text */}
        {analysis && (
          <p className="text-zinc-500 text-xs italic leading-relaxed">
            {analysis}
          </p>
        )}

        {/* Expandable image */}
        {imageB64 && (
          <div>
            <button
              type="button"
              onClick={() => setExpanded((prev) => !prev)}
              aria-expanded={expanded}
              aria-label={
                expanded ? "Collapse screenshot" : "Expand screenshot"
              }
              className="relative group w-full overflow-hidden rounded border border-card-border dark:border-zinc-800 bg-background dark:bg-black cursor-pointer transition-[max-height] duration-500 ease-in-out"
              style={{ maxHeight: expanded ? "400px" : "64px" }}
            >
              <img
                src={`data:image/png;base64,${imageB64}`}
                alt="Agent screenshot"
                className="w-full object-contain transition-[opacity,filter] duration-500"
                style={{
                  opacity: expanded ? 1 : 0.5,
                  filter: expanded ? "none" : "blur(1px)",
                }}
              />
              {!expanded && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                  <span className="text-[9px] font-bold text-white uppercase tracking-widest">
                    Click to expand
                  </span>
                </div>
              )}
            </button>
            <button
              type="button"
              onClick={() => setExpanded((prev) => !prev)}
              className="mt-1 text-[9px] font-bold text-muted dark:text-zinc-600 hover:text-zinc-500 dark:hover:text-zinc-400 uppercase tracking-widest transition-colors duration-200"
            >
              {expanded ? "Collapse" : "View full"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  agent_thinking  -- italic muted left-aligned line                  */
/* ------------------------------------------------------------------ */

function ThinkingLine({
  ts,
  content,
}: {
  ts: number;
  content?: string;
}) {
  return (
    <div className="flex items-start gap-2 py-1 px-3">
      <span className="mt-1.5 block w-2 h-2 rounded-full bg-zinc-400 dark:bg-zinc-600 shrink-0" />
      <div className="min-w-0 text-[11px]">
        <span className="text-muted dark:text-zinc-700 mr-1.5 select-none font-mono">
          {formatTime(ts)}
        </span>
        <span className="text-zinc-400 dark:text-zinc-500 italic">
          {content || "Thinking\u2026"}
        </span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  agent_complete  -- small emerald badge                             */
/* ------------------------------------------------------------------ */

function CompleteBadge({ ts }: { ts: number }) {
  return (
    <div className="flex items-center gap-2 py-1 px-3">
      <span className="text-muted dark:text-zinc-700 text-[11px] select-none font-mono">
        {formatTime(ts)}
      </span>
      <span className="inline-flex items-center gap-1.5 text-[10px] font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded-full px-3 py-0.5 uppercase tracking-widest">
        <span className="block w-1.5 h-1.5 rounded-full bg-emerald-500" />
        Task complete
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  voice_status  -- info badge for reconnect / fallback               */
/* ------------------------------------------------------------------ */

function VoiceStatusBadge({
  ts,
  status,
  message,
}: {
  ts: number;
  status?: string;
  message?: string;
}) {
  const tone =
    status === "connected"
      ? {
          dot: "bg-emerald-500",
          label: "text-emerald-400",
          box: "bg-emerald-500/5 border-emerald-500/20",
          text: "text-emerald-300/80",
        }
      : status === "reconnecting"
        ? {
            dot: "bg-amber-500 animate-pulse",
            label: "text-amber-400",
            box: "bg-amber-500/5 border-amber-500/20",
            text: "text-amber-200/80",
          }
        : {
            dot: "bg-zinc-500",
            label: "text-zinc-300",
            box: "bg-zinc-500/5 border-zinc-500/20",
            text: "text-zinc-400",
          };

  return (
    <div className="py-1 px-3">
      <div className={`rounded-lg border p-2.5 space-y-1 ${tone.box}`}>
        <div className="flex items-center gap-2">
          <span className="text-muted dark:text-zinc-700 text-[11px] select-none font-mono">
            {formatTime(ts)}
          </span>
          <span className={`block h-2 w-2 rounded-full ${tone.dot}`} />
          <span className={`text-[10px] font-black uppercase tracking-widest ${tone.label}`}>
            Voice {status || "status"}
          </span>
        </div>
        {message && (
          <p className={`text-xs leading-relaxed ${tone.text}`}>
            {message}
          </p>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  error  -- red badge with message                                   */
/* ------------------------------------------------------------------ */

function ErrorBadge({
  ts,
  message,
  code,
}: {
  ts: number;
  message: string;
  code?: string;
}) {
  return (
    <div className="py-1 px-3">
      <div className="bg-red-500/5 border border-red-500/15 rounded-lg p-2.5 space-y-1">
        <div className="flex items-center gap-2">
          <span className="text-muted dark:text-zinc-700 text-[11px] select-none font-mono">
            {formatTime(ts)}
          </span>
          <span className="text-red-500 text-[10px] font-black uppercase tracking-widest">
            Error
          </span>
          {code && (
            <span className="text-[9px] bg-red-500/20 text-red-400 px-1.5 rounded font-bold tracking-tight">
              {code}
            </span>
          )}
        </div>
        <p className="text-red-400 text-xs font-medium leading-relaxed">
          {message}
        </p>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  bg_task_progress  -- progress bar pill                             */
/* ------------------------------------------------------------------ */

function BgTaskProgressPill({
  ts,
  progress,
  message,
}: {
  ts: number;
  progress: number;
  message: string;
}) {
  return (
    <div className="flex items-start gap-2 py-1 px-3">
      <span className="mt-1.5 block w-2 h-2 rounded-full bg-amber-500 shrink-0 animate-pulse" />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex items-center gap-2 text-[11px]">
          <span className="text-muted dark:text-zinc-700 select-none font-mono">
            {formatTime(ts)}
          </span>
          <span className="text-amber-400 text-[10px] font-bold uppercase tracking-widest">
            Background Task
          </span>
          <span className="text-zinc-400 dark:text-zinc-500 text-[10px]">{progress}%</span>
        </div>
        <div className="w-full h-1 rounded-full bg-zinc-800 overflow-hidden">
          <div
            className="h-full rounded-full bg-amber-500 transition-all duration-500 ease-out"
            style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
          />
        </div>
        {message && (
          <p className="text-zinc-400 dark:text-zinc-500 text-[10px]">{message}</p>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  bg_task_complete  -- success/fail badge                            */
/* ------------------------------------------------------------------ */

function BgTaskCompleteBadge({
  ts,
  success,
  result,
}: {
  ts: number;
  success: boolean;
  result: string;
}) {
  return (
    <div className="py-1 px-3">
      <div
        className={`rounded-lg p-2.5 space-y-1 border ${
          success
            ? "bg-emerald-500/5 border-emerald-500/20"
            : "bg-red-500/5 border-red-500/15"
        }`}
      >
        <div className="flex items-center gap-2">
          <span className="text-muted dark:text-zinc-700 text-[11px] select-none font-mono">
            {formatTime(ts)}
          </span>
          <span
            className={`text-[10px] font-black uppercase tracking-widest ${
              success ? "text-emerald-400" : "text-red-500"
            }`}
          >
            {success ? "Task Done" : "Task Failed"}
          </span>
        </div>
        {result && (
          <p
            className={`text-xs leading-relaxed ${
              success ? "text-emerald-300/80" : "text-red-400"
            }`}
          >
            {result.length > 200 ? result.slice(0, 200) + "\u2026" : result}
          </p>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  delegation  -- centered dim badge                                  */
/* ------------------------------------------------------------------ */

function DelegationBadge({
  from,
  to,
  ts,
}: {
  from: string;
  to: string;
  ts: number;
}) {
  return (
    <div className="flex justify-center py-2">
      <div className="inline-flex items-center gap-2 text-[10px] text-zinc-600 dark:text-zinc-500 bg-zinc-100/60 dark:bg-zinc-900/60 border border-zinc-200 dark:border-zinc-800 rounded-full px-4 py-1">
        <span className="font-mono text-zinc-500 dark:text-zinc-700 select-none">
          {formatTime(ts)}
        </span>
        <span className="text-zinc-400 dark:text-zinc-500">&rarr;</span>
        <span className="text-zinc-600 dark:text-zinc-400 font-bold">
          {from} to {to}
        </span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Thinking indicator (spinner)                                       */
/* ------------------------------------------------------------------ */

function ThinkingIndicator() {
  return (
    <div className="flex flex-col items-start py-4 px-2">
      <div className="flex items-center gap-3 text-amber-500">
        <svg
          className="w-4 h-4 animate-[spin_3s_linear_infinite]"
          viewBox="0 0 24 24"
          fill="none"
        >
          <circle
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeDasharray="6 6"
            strokeLinecap="round"
          />
        </svg>
        <span className="text-[14px] font-medium">
          Nexus will continue working after your reply
        </span>
      </div>
    </div>
  );
}
