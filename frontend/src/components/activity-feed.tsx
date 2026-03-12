"use client";

import { useRef, useEffect, useState } from "react";

type ActivityEvent = {
  type: string;
  timestamp: number;
  [key: string]: unknown;
};

type Props = {
  events: ActivityEvent[];
  emptyState?: string;
};

export function ActivityFeed({
  events,
  emptyState = "Waiting for agent activity...",
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, [events]);

  if (events.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-zinc-500 text-sm">{emptyState}</p>
      </div>
    );
  }

  return (
    <div
      ref={scrollRef}
      className="flex flex-col gap-1.5 p-3 overflow-y-auto h-full text-xs font-mono scrollbar-thin scrollbar-track-transparent scrollbar-thumb-zinc-700"
    >
      {events.map((event, i) => (
        <ActivityEntry key={`${event.timestamp}-${i}`} event={event} />
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Individual event renderers                                        */
/* ------------------------------------------------------------------ */

function ActivityEntry({ event }: { event: ActivityEvent }) {
  const time = new Date(event.timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <div className="animate-in fade-in duration-300 slide-in-from-bottom-1">
      {(() => {
        switch (event.type) {
          case "agent_thinking":
            return <ThinkingEntry time={time} content={event.content as string} />;
          case "agent_tool_call":
            return (
              <ToolCallEntry
                time={time}
                tool={event.tool as string}
                args={event.args as Record<string, unknown>}
              />
            );
          case "agent_tool_result":
            return (
              <ToolResultEntry
                time={time}
                tool={event.tool as string}
                output={event.output as string}
              />
            );
          case "agent_screenshot":
            return (
              <ScreenshotEntry
                time={time}
                imageB64={event.image_b64 as string | undefined}
                analysis={event.analysis as string | undefined}
              />
            );
          case "error":
            return (
              <ErrorEntry
                time={time}
                message={event.message as string}
                code={event.code as string | undefined}
              />
            );
          default:
            return (
              <div className="text-zinc-500 px-2 py-1">
                <TimeStamp time={time} />
                <span>{event.type}: {JSON.stringify(event)}</span>
              </div>
            );
        }
      })()}
    </div>
  );
}

function TimeStamp({ time }: { time: string }) {
  return <span className="text-zinc-600 mr-2 select-none">{time}</span>;
}

/* --- Brain icon: agent_thinking --- */
function ThinkingEntry({ time, content }: { time: string; content: string }) {
  return (
    <div className="flex items-start gap-2 text-zinc-400 italic pl-2 border-l-2 border-zinc-700 py-1">
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        className="w-4 h-4 shrink-0 mt-0.5 text-zinc-500"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M9.75 3a3.75 3.75 0 0 0-2.4 6.63A4.5 4.5 0 0 0 3 14.25a4.5 4.5 0 0 0 4.5 4.5h.38A3 3 0 0 0 12 21a3 3 0 0 0 4.12-2.25h.38a4.5 4.5 0 0 0 4.5-4.5 4.5 4.5 0 0 0-4.35-4.62A3.75 3.75 0 0 0 14.25 3a3.75 3.75 0 0 0-2.25.75A3.73 3.73 0 0 0 9.75 3Z"
        />
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 13h.01M15 13h.01M10 17s1 1 2 1 2-1 2-1" />
      </svg>
      <div>
        <TimeStamp time={time} />
        <span>{content}</span>
      </div>
    </div>
  );
}

/* --- Wrench icon: agent_tool_call --- */
function ToolCallEntry({
  time,
  tool,
  args,
}: {
  time: string;
  tool: string;
  args: Record<string, unknown>;
}) {
  const argsStr = Object.entries(args)
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(", ");

  return (
    <div className="flex items-start gap-2 bg-blue-950/30 border border-blue-800/25 rounded px-2 py-1.5">
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        className="w-4 h-4 shrink-0 mt-0.5 text-blue-400"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M21.75 6.75a4.5 4.5 0 0 1-4.88 4.48l-7.12 7.12a2.25 2.25 0 1 1-3.18-3.18l7.12-7.12A4.5 4.5 0 0 1 18 3.75a4.5 4.5 0 0 1 3.75 3Z"
        />
        <path strokeLinecap="round" strokeLinejoin="round" d="m14.12 6 3.88 3.88" />
      </svg>
      <div className="min-w-0">
        <TimeStamp time={time} />
        <span className="text-blue-400 font-semibold">TOOL</span>{" "}
        <span className="text-zinc-200">{tool}</span>
        <span className="text-zinc-500 break-all">({argsStr})</span>
      </div>
    </div>
  );
}

/* --- Check icon: agent_tool_result --- */
function ToolResultEntry({
  time,
  tool,
  output,
}: {
  time: string;
  tool: string;
  output: string;
}) {
  const truncated = output.length > 200 ? output.slice(0, 200) + "..." : output;

  return (
    <div className="flex items-start gap-2 bg-emerald-950/25 border border-emerald-800/20 rounded px-2 py-1.5">
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        className="w-4 h-4 shrink-0 mt-0.5 text-emerald-400"
      >
        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
      </svg>
      <div className="min-w-0">
        <TimeStamp time={time} />
        <span className="text-emerald-400 font-semibold">RESULT</span>{" "}
        <span className="text-zinc-400">{tool}:</span>{" "}
        <span className="text-zinc-300 break-all">{truncated}</span>
      </div>
    </div>
  );
}

/* --- Camera icon: agent_screenshot --- */
function ScreenshotEntry({
  time,
  imageB64,
  analysis,
}: {
  time: string;
  imageB64?: string;
  analysis?: string;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-zinc-800/50 border border-zinc-700/40 rounded px-2 py-1.5">
      <div className="flex items-start gap-2">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          className="w-4 h-4 shrink-0 mt-0.5 text-amber-400"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M6.827 6.175A2.31 2.31 0 0 1 5.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.9 47.9 0 0 0-1.134-.175 2.31 2.31 0 0 1-1.64-1.055l-.822-1.316A2.19 2.19 0 0 0 14.49 3.75h-4.979a2.19 2.19 0 0 0-1.862 1.054l-.823 1.316.001.005Z"
          />
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M16.5 12.75a4.5 4.5 0 1 1-9 0 4.5 4.5 0 0 1 9 0Z"
          />
        </svg>
        <div className="min-w-0">
          <TimeStamp time={time} />
          <span className="text-amber-400 font-semibold">SCREENSHOT</span>
          {analysis && (
            <span className="text-zinc-400 ml-1.5">{analysis.slice(0, 120)}</span>
          )}
        </div>
      </div>

      {imageB64 && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-1.5 w-full text-left"
        >
          <img
            src={`data:image/png;base64,${imageB64}`}
            alt="Agent screenshot"
            className={`rounded border border-zinc-700 bg-black transition-all duration-200 ${
              expanded
                ? "w-full max-h-96 object-contain"
                : "w-full max-h-24 object-cover opacity-80 hover:opacity-100"
            }`}
          />
          <span className="text-[10px] text-zinc-600 mt-0.5 block">
            {expanded ? "Click to collapse" : "Click to expand"}
          </span>
        </button>
      )}
    </div>
  );
}

/* --- X icon: error --- */
function ErrorEntry({
  time,
  message,
  code,
}: {
  time: string;
  message: string;
  code?: string;
}) {
  return (
    <div className="flex items-start gap-2 bg-red-950/30 border border-red-800/25 rounded px-2 py-1.5">
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        className="w-4 h-4 shrink-0 mt-0.5 text-red-400"
      >
        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
      </svg>
      <div className="min-w-0">
        <TimeStamp time={time} />
        <span className="text-red-400 font-semibold">ERROR</span>
        {code && <span className="text-red-500/70 ml-1">[{code}]</span>}{" "}
        <span className="text-red-300 break-all">{message}</span>
      </div>
    </div>
  );
}
