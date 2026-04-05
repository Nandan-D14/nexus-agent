"use client";

import { useRef, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

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
      <div className="flex items-center justify-center h-full animate-fade-in">
        <div className="text-center space-y-2">
          <div className="w-8 h-8 rounded-full border border-zinc-800 flex items-center justify-center mx-auto mb-4">
            <div className="w-1.5 h-1.5 rounded-full bg-zinc-800 animate-pulse" />
          </div>
          <p className="text-zinc-600 text-[10px] font-bold uppercase tracking-widest">Awaiting Telemetry</p>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={scrollRef}
      className="flex flex-col gap-3 p-4 overflow-y-auto h-full text-[11px] font-mono custom-scrollbar"
    >
      <AnimatePresence initial={false} mode="popLayout">
        {events.map((event, i) => (
          <ActivityEntry key={`${event.timestamp}-${i}`} event={event} />
        ))}
      </AnimatePresence>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Individual event renderers                                        */
/* ------------------------------------------------------------------ */

function ActivityEntry({ event }: { event: ActivityEvent }) {
  const time = new Date(event.timestamp).toLocaleTimeString([], {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <motion.div 
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 10 }}
      transition={{ duration: 0.3 }}
    >
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
                detail={event.detail as string | undefined}
                code={event.code as string | undefined}
              />
            );
          default:
            return (
              <div className="text-zinc-600 pl-2 border-l border-zinc-800">
                <TimeStamp time={time} />
                <span>{event.type.toUpperCase()}: {JSON.stringify(event)}</span>
              </div>
            );
        }
      })()}
    </motion.div>
  );
}

function TimeStamp({ time }: { time: string }) {
  return <span className="text-zinc-700 mr-2 select-none font-bold">[{time}]</span>;
}

/* --- Brain icon: agent_thinking --- */
function ThinkingEntry({ time, content }: { time: string; content: string }) {
  return (
    <div className="flex flex-col gap-1 pl-3 border-l-2 border-zinc-800/50 py-1">
      <div className="flex items-center gap-2">
        <TimeStamp time={time} />
        <span className="text-zinc-500 font-bold uppercase tracking-tighter">Thinking</span>
      </div>
      <span className="text-zinc-400 italic leading-relaxed">{content}</span>
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
    <div className="bg-cyan-500/5 border border-cyan-500/10 rounded-lg p-2.5 space-y-1">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TimeStamp time={time} />
          <span className="text-cyan-500 font-black uppercase tracking-widest">Call</span>
        </div>
        <div className="w-1.5 h-1.5 rounded-full bg-cyan-500/40 animate-pulse" />
      </div>
      <div className="min-w-0">
        <span className="text-zinc-100 font-bold">{tool}</span>
        <span className="text-zinc-500 ml-1.5 break-all">({argsStr})</span>
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
    <div className="bg-emerald-500/5 border border-emerald-500/10 rounded-lg p-2.5 space-y-1">
      <div className="flex items-center gap-2">
        <TimeStamp time={time} />
        <span className="text-emerald-500 font-black uppercase tracking-widest">Return</span>
      </div>
      <div className="min-w-0">
        <span className="text-zinc-400 font-bold">{tool}</span>
        <span className="text-zinc-500 mx-2">→</span>
        <span className="text-zinc-300 break-all leading-relaxed font-light">{truncated}</span>
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
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-2.5 space-y-2">
      <div className="flex items-center gap-2">
        <TimeStamp time={time} />
        <span className="text-amber-500 font-black uppercase tracking-widest">Optic</span>
      </div>
      
      {analysis && (
        <p className="text-zinc-400 leading-relaxed italic">{analysis}</p>
      )}

      {imageB64 && (
        <div className="space-y-2">
          <button
            onClick={() => setExpanded(!expanded)}
            aria-expanded={expanded}
            aria-label={expanded ? "Collapse screenshot" : "Expand screenshot"}
            className={`relative group w-full overflow-hidden rounded border border-zinc-800 bg-black transition-all duration-500 ${
              expanded ? "max-h-[400px]" : "max-h-20"
            }`}
          >
            <img
              src={`data:image/png;base64,${imageB64}`}
              alt="Agent screenshot"
              className={`w-full transition-all duration-500 object-contain ${
                expanded ? "opacity-100" : "opacity-60 blur-[1px] group-hover:opacity-80 group-hover:blur-0"
              }`}
            />
            {!expanded && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity">
                <span className="text-[9px] font-bold text-white uppercase tracking-widest">Expand Visual</span>
              </div>
            )}
          </button>
          <div className="flex justify-center">
            <button 
              onClick={() => setExpanded(!expanded)}
              className="text-[9px] font-bold text-zinc-600 hover:text-zinc-400 uppercase tracking-widest transition-colors"
            >
              {expanded ? "Collapse Optic" : "View Telemetry"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* --- X icon: error --- */
function ErrorEntry({
  time,
  message,
  detail,
  code,
}: {
  time: string;
  message: string;
  detail?: string;
  code?: string;
}) {
  return (
    <div className="bg-red-500/5 border border-red-500/15 rounded-lg p-2.5 space-y-1">
      <div className="flex items-center gap-2">
        <TimeStamp time={time} />
        <span className="text-red-500 font-black uppercase tracking-widest">Fault</span>
        {code && <span className="text-[9px] bg-red-500/20 text-red-400 px-1.5 rounded ml-1 font-bold tracking-tighter">{code}</span>}
      </div>
      <p className="text-red-400 font-medium leading-relaxed">{message}</p>
      {detail && detail !== message && (
        <p className="text-red-300/90 text-sm leading-relaxed break-words">{detail}</p>
      )}
    </div>
  );
}
