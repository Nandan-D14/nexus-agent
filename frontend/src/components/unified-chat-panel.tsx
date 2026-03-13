"use client";

import { useRef, useEffect, useState } from "react";
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
  }, [items, isThinking]);

  return (
    <div
      ref={scrollRef}
      className="overflow-y-auto h-full custom-scrollbar flex flex-col px-4 py-6"
    >
      <div className="mx-auto max-w-3xl w-full flex flex-col gap-1.5 pb-4">
        {items.map((item, i) => (
          <div key={`${item.ts}-${item.kind}-${i}`} className="ucp-fade-in flex flex-col w-full">
            <ChatItemRouter
              item={item}
              onPermissionRespond={onPermissionRespond}
            />
          </div>
        ))}

        {isThinking && (
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

  return (
    <div
      className={`flex flex-col py-2 px-4 ${
        isUser ? "items-end" : "items-start"
      }`}
    >
      {/* Label + timestamp */}
      <div className="flex items-center gap-2 mb-1 px-1">
        <span
          className={`text-[9px] font-black uppercase tracking-[0.2em] ${
            isUser ? "text-cyan-500" : "text-emerald-500"
          }`}
        >
          {isUser ? "You" : "NEXUS"}
        </span>
        <span className="text-[9px] text-muted dark:text-zinc-600 font-mono">
          {formatTime(ts)}
        </span>
      </div>

      {/* Bubble */}
      <div
        className={`max-w-[85%] px-4 py-3 rounded-2xl text-sm leading-relaxed transition-colors duration-200 ${
          isUser
            ? "bg-cyan-500/5 text-cyan-50 border border-cyan-500/20 rounded-tr-none"
            : "bg-white dark:bg-zinc-900 text-foreground dark:text-zinc-200 border border-card-border dark:border-zinc-800 rounded-tl-none shadow-sm dark:shadow-none"
        }`}
      >
        {text}
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
  const argsStr = args
    ? Object.entries(args)
        .map(
          ([k, v]) =>
            `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`
        )
        .join(", ")
    : "";

  return (
    <div className="flex items-start gap-2 py-1 px-3">
      <span className="mt-1.5 block w-2 h-2 rounded-full bg-cyan-500 shrink-0" />
      <div className="min-w-0 font-mono text-[11px] leading-snug">
        <span className="text-muted dark:text-zinc-700 mr-1.5 select-none">
          {formatTime(ts)}
        </span>
        <span className="text-cyan-400">{tool}</span>
        <span className="text-zinc-400 dark:text-zinc-500">({argsStr})</span>
      </div>
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
    output && output.length > 120
      ? output.slice(0, 120) + "\u2026"
      : output || "";

  return (
    <div className="flex items-start gap-2 py-1 px-3">
      <span className="mt-1.5 block w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
      <div className="min-w-0 font-mono text-[11px] leading-snug">
        <span className="text-muted dark:text-zinc-700 mr-1.5 select-none">
          {formatTime(ts)}
        </span>
        <span className="text-emerald-400 font-bold">{tool}</span>
        <span className="text-muted dark:text-zinc-500 mx-1">&rarr;</span>
        <span className="text-zinc-500 dark:text-zinc-400 break-all">{display}</span>
      </div>
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
        <span className="text-zinc-600 dark:text-zinc-400 font-bold">Delegated to {to}</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Thinking indicator (three animated dots)                           */
/* ------------------------------------------------------------------ */

function ThinkingIndicator() {
  return (
    <div className="flex flex-col items-start py-2 px-4">
      <div className="flex items-center gap-2 mb-1 px-1">
        <span className="text-[9px] font-black text-emerald-500 uppercase tracking-[0.2em]">
          NEXUS
        </span>
      </div>
      <div className="flex items-center gap-3 px-4 py-2.5 rounded-2xl rounded-tl-none bg-white dark:bg-zinc-900 border border-card-border dark:border-zinc-800 shadow-sm dark:shadow-none">
        <div className="flex items-center gap-1">
          <span className="block w-1.5 h-1.5 rounded-full bg-emerald-500 ucp-dot-1" />
          <span className="block w-1.5 h-1.5 rounded-full bg-emerald-500 ucp-dot-2" />
          <span className="block w-1.5 h-1.5 rounded-full bg-emerald-500 ucp-dot-3" />
        </div>
        <span className="text-[10px] font-bold text-zinc-400 dark:text-zinc-500 uppercase tracking-widest">
          Processing...
        </span>
      </div>
    </div>
  );
}
