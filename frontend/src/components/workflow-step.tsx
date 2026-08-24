/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Terminal,
  Check,
  X,
  ChevronDown,
  ChevronRight,
  Eye,
  Code2,
  Globe,
  Bot,
  Brain,
  FileText,
  Search,
  Mail,
  Calendar,
  ListTodo,
  Plug,
  MapPin,
  Clock,
  User,
  LayoutGrid,
} from "lucide-react";

export type StepType =
  | "thinking"
  | "tool_call"
  | "tool_result"
  | "screenshot"
  | "file_created"
  | "browser"
  | "error"
  | "terminal"
  | "observation"
  | "completion"
  | "gmail"
  | "calendar"
  | "tasks"
  | "mcp"
  | "generative_ui"
  | "html_artifact";

export type StepStatus = "pending" | "in_progress" | "completed" | "failed";

export type WorkflowStepData = {
  step_id: string;
  step_type: StepType;
  title: string;
  status: StepStatus;
  detail?: string;
  output?: string;
  error?: string;
  image_b64?: string;
  command?: string;
  args?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  tool?: string;
  created_at: string;
  completed_at?: string;
};

type Props = {
  step: WorkflowStepData;
  isLast?: boolean;
  stepNumber?: number;
  disableDetails?: boolean;
  onSelect?: () => void;
};

function formatTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleTimeString([], {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function getStepIcon(type: StepType, status: StepStatus) {
  if (status === "failed") return <X className="w-[11px] h-[11px] text-red-400" />;
  if (type === "thinking") return <Brain className="w-[11px] h-[11px] text-zinc-400" />;
  if (type === "terminal") return <Terminal className="w-[11px] h-[11px] text-zinc-400" />;
  if (type === "browser") return <Globe className="w-[11px] h-[11px] text-zinc-400" />;
  if (type === "tool_call") return <Code2 className="w-[11px] h-[11px] text-zinc-400" />;
  if (type === "observation") return <Search className="w-[11px] h-[11px] text-zinc-400" />;
  if (type === "file_created") return <FileText className="w-[11px] h-[11px] text-zinc-400" />;
  if (type === "gmail") return <Mail className="w-[11px] h-[11px] text-zinc-400" />;
  if (type === "calendar") return <Calendar className="w-[11px] h-[11px] text-zinc-400" />;
  if (type === "tasks") return <ListTodo className="w-[11px] h-[11px] text-zinc-400" />;
  if (type === "mcp") return <Plug className="w-[11px] h-[11px] text-zinc-400" />;
  if (type === "generative_ui") return <LayoutGrid className="w-[11px] h-[11px] text-violet-400" />;
  if (type === "html_artifact") return <FileText className="w-[11px] h-[11px] text-amber-400" />;
  if (type === "completion" || status === "completed") return <Check className="w-[11px] h-[11px] text-emerald-400" />;
  return <Bot className="w-[11px] h-[11px] text-zinc-400" />;
}


export function WorkflowStep({ step, isLast = false, disableDetails = false, onSelect }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [imageExpanded, setImageExpanded] = useState(false);

  const isFailed = step.status === "failed";
  const isInProgress = step.status === "in_progress";
  
  // Extract web results if they exist (for inline rich display)
  const meta = step.metadata ?? {};
  const resultObj = meta.result && typeof meta.result === "object" && !Array.isArray(meta.result) 
    ? (meta.result as Record<string, unknown>) 
    : undefined;
    
  let webResults: Array<{ title: string; url: string; snippet: string }> = [];
  const rawResults = meta.results || resultObj?.results;
  if (Array.isArray(rawResults)) {
    webResults = rawResults.map((val) => {
      const item = val && typeof val === "object" && !Array.isArray(val) ? (val as Record<string, unknown>) : null;
      if (!item) return null;
      return {
        title: (item.title as string) || (item.name as string) || "",
        url: (item.url as string) || (item.href as string) || (item.link as string) || "",
        snippet: (item.snippet as string) || (item.body as string) || (item.description as string) || (item.summary as string) || "",
      };
    }).filter((x): x is { title: string; url: string; snippet: string } => Boolean(x && (x.title || x.url || x.snippet)));
  }

  const query = (meta.query as string) || (resultObj?.query as string) || (step.args?.query as string);

  const hasDetails = !disableDetails && Boolean(
    step.detail || step.output || step.error || step.command || step.image_b64 || (step.args && Object.keys(step.args).length > 0) || webResults.length > 0
  );
  const isSelectable = Boolean(onSelect);

  // Helper to extract domain for the favicon
  const getDomain = (urlStr: string) => {
    try {
      return new URL(urlStr).hostname;
    } catch {
      return urlStr.split("/")[0] || urlStr;
    }
  };

  return (
    <div className="relative group">
      <div className="flex items-start gap-3">
        {/* Minimal Timeline Node (icon on timeline) */}
        <div className="relative flex flex-col items-center pt-[2px] shrink-0 w-6">
          <div 
            className={`w-6 h-6 flex items-center justify-center bg-[#09090b] z-10 transition-colors duration-300 ${
              isFailed ? "text-red-400" : isInProgress ? "text-zinc-200" : "text-zinc-500"
            }`}
          >
            {getStepIcon(step.step_type, step.status)}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0 pb-6">
          <div 
            className={`flex items-start justify-between gap-4 transition-colors ${
              isSelectable ? "cursor-pointer group-hover:text-zinc-100" : ""
            }`}
            onClick={() => {
              onSelect?.();
              if (hasDetails) setExpanded(!expanded);
            }}
          >
            <div className="flex-1 min-w-0 pt-[3px]">
              <div className={`text-[13px] leading-snug font-normal ${
                isFailed ? "text-red-400" : isInProgress ? "text-zinc-200" : "text-zinc-400"
              } transition-colors ${isSelectable ? "group-hover:text-zinc-300" : ""}`}>
                {step.title}
                {query && step.step_type === "browser" && (
                  <span className="text-zinc-500 italic ml-2">
                    &quot;{query}&quot;
                  </span>
                )}
              </div>
            </div>
            
            <div className="flex items-center gap-2 shrink-0 pt-[3px]">
              {webResults.length > 0 && !expanded && (
                <span className="text-[11px] text-zinc-500 mr-2">{webResults.length} results</span>
              )}
              {hasDetails && (
                <div className={`w-4 h-4 flex items-center justify-center transition-colors ${expanded ? "text-zinc-400" : "text-zinc-600"}`}>
                  {expanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                </div>
              )}
            </div>
          </div>

          {/* Inline Rich Details Panel */}
          <AnimatePresence>
            {expanded && hasDetails && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.25, ease: [0.23, 1, 0.32, 1] }}
                className="overflow-hidden"
              >
                <div className="pt-3 space-y-3 pb-1">
                  
                  {/* Web Search Results Inline */}
                  {webResults.length > 0 && (
                    <div className="rounded-lg border border-zinc-800/60 bg-[#121214] overflow-hidden">
                      <div className="px-3 py-2 border-b border-zinc-800/60 bg-[#151518] flex items-center justify-between">
                        <span className="text-[11px] font-medium text-zinc-400">Search Results</span>
                        <span className="text-[10px] text-zinc-500">{webResults.length} results</span>
                      </div>
                      <div className="divide-y divide-zinc-800/40 max-h-64 overflow-y-auto custom-scrollbar">
                        {webResults.map((item, idx) => (
                          <a 
                            key={idx} 
                            href={item.url || "#"} 
                            target="_blank" 
                            rel="noreferrer"
                            className="block p-3 hover:bg-white/[0.02] transition-colors"
                            onClick={(e) => {
                              if (!item.url) e.preventDefault();
                              e.stopPropagation();
                            }}
                          >
                            <div className="flex items-center gap-2 mb-1">
                              {item.url ? (
                                /* eslint-disable-next-line @next/next/no-img-element */
                                <img 
                                  src={`https://www.google.com/s2/favicons?domain=${getDomain(item.url)}&sz=32`} 
                                  alt="" 
                                  className="w-3.5 h-3.5 rounded-sm bg-zinc-800"
                                  onError={(e) => { e.currentTarget.style.display = "none"; }}
                                />
                              ) : (
                                <Globe className="w-3.5 h-3.5 text-zinc-600" />
                              )}
                              <span className="text-[12px] font-medium text-zinc-200 truncate">{item.title || "Untitled"}</span>
                            </div>
                            <div className="text-[11px] text-zinc-500 truncate ml-5.5">{getDomain(item.url)}</div>
                          </a>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Detailed Description / Text content */}
                  {step.detail && step.step_type !== "browser" && (
                    <div className="text-[13px] text-zinc-400 leading-relaxed max-w-full break-words">
                      {step.detail}
                    </div>
                  )}

                  {/* Terminal / Command - Minimized */}
                  {step.command && (
                    <div className="rounded border border-zinc-800/40 bg-[#0e0e10]">
                      <div className="p-2.5 overflow-x-auto custom-scrollbar">
                        <code className="text-[11.5px] text-zinc-300 font-mono whitespace-pre"><span className="text-zinc-600 select-none mr-2">$</span>{step.command}</code>
                      </div>
                    </div>
                  )}

                  {/* JSON Args (subtle) */}
                  {step.args && Object.keys(step.args).length > 0 && !webResults.length && step.step_type !== "gmail" && step.step_type !== "calendar" && step.step_type !== "tasks" && (
                    <div className="rounded border border-zinc-800/40 bg-[#0e0e10] p-2.5 overflow-x-auto custom-scrollbar">
                       <pre className="text-[11px] text-zinc-400 font-mono">
                         {JSON.stringify(step.args, null, 2)}
                       </pre>
                    </div>
                  )}

                  {/* Output (subtle) */}
                  {step.output && step.step_type !== "browser" && (
                    <div className="rounded border border-zinc-800/40 bg-[#0e0e10] p-2.5 overflow-x-auto custom-scrollbar max-h-48">
                      <pre className="text-[11px] text-zinc-500 font-mono whitespace-pre-wrap break-all leading-relaxed">
                        {step.output.length > 2000
                          ? step.output.slice(0, 2000) + "\n\n... [Output truncated]"
                          : step.output}
                      </pre>
                    </div>
                  )}

                  {/* Error */}
                  {step.error && (
                    <div className="text-[12px] text-red-400 font-mono whitespace-pre-wrap break-words leading-relaxed pl-2 border-l-2 border-red-500/30">
                      {step.error}
                    </div>
                  )}

                  {/* Gmail Visualizer */}
                  {step.step_type === "gmail" && step.args && (
                    <div className="rounded-lg border border-zinc-800/40 bg-[#121214] p-3 space-y-2">
                      <div className="space-y-1">
                        <div className="text-[13px] font-medium text-zinc-200">{step.args.subject as string}</div>
                        <div className="flex items-center gap-2 text-[11px] text-zinc-500">
                          <User className="w-3 h-3" />
                          <span>{step.args.to as string}</span>
                        </div>
                        <div className="text-[12px] text-zinc-400 leading-relaxed whitespace-pre-wrap pt-2 mt-1 border-t border-zinc-800/40">
                          {step.args.body as string}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Calendar Visualizer */}
                  {step.step_type === "calendar" && step.args && (
                    <div className="rounded-lg border border-zinc-800/40 bg-[#121214] p-3 space-y-2">
                      <div className="space-y-1.5">
                        <div className="text-[13px] font-medium text-zinc-200">{step.args.summary as string}</div>
                        <div className="flex items-center gap-4 text-[11px] text-zinc-400">
                          <div className="flex items-center gap-1.5">
                            <Clock className="w-3 h-3 text-zinc-500" />
                            <span>{new Date(step.args.start_time as string).toLocaleString()}</span>
                          </div>
                          {Boolean(step.args.location) && (
                            <div className="flex items-center gap-1.5">
                              <MapPin className="w-3 h-3 text-zinc-500" />
                              <span>{step.args.location as string}</span>
                            </div>
                          )}
                        </div>
                        {Boolean(step.args.description) && (
                          <div className="text-[12px] text-zinc-500 leading-relaxed pt-2 mt-1 border-t border-zinc-800/40">
                            {step.args.description as string}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Tasks Visualizer */}
                  {step.step_type === "tasks" && step.args && (
                    <div className="rounded-lg border border-zinc-800/40 bg-[#121214] p-3 space-y-2">
                      <div className="space-y-1.5">
                        <div className="flex items-start gap-2">
                          <div className="w-3.5 h-3.5 rounded border border-zinc-600 mt-[3px] shrink-0" />
                          <div className="text-[13px] font-medium text-zinc-200">{step.args.title as string}</div>
                        </div>
                        {Boolean(step.args.notes) && (
                          <div className="text-[12px] text-zinc-400 pl-5.5 leading-relaxed">
                            {step.args.notes as string}
                          </div>
                        )}
                        {Boolean(step.args.due) && (
                          <div className="flex items-center gap-1.5 pl-5.5 text-[10px] text-zinc-500">
                            <Clock className="w-3 h-3" />
                            <span>Due: {new Date(step.args.due as string).toLocaleDateString()}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Screenshot */}
                  {step.image_b64 && (
                    <div className="rounded-lg border border-zinc-800/40 bg-[#0e0e10] overflow-hidden">
                      <div className={`p-1.5 transition-all duration-500 relative ${imageExpanded ? "" : "max-h-48 overflow-hidden cursor-pointer"}`}
                           onClick={(e) => {
                             e.stopPropagation();
                             if (!imageExpanded) setImageExpanded(true);
                           }}>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={`data:image/png;base64,${step.image_b64}`}
                          alt="Screenshot"
                          className="w-full rounded-[4px] border border-zinc-800/30"
                        />
                        {!imageExpanded && (
                          <div className="absolute inset-0 bg-gradient-to-t from-[#0e0e10] via-[#0e0e10]/20 to-transparent flex items-end justify-center pb-3">
                            <span className="text-[10px] font-medium text-zinc-400 bg-[#121214] border border-zinc-700/50 px-2 py-1 rounded-full shadow-lg">Click to expand</span>
                          </div>
                        )}
                        {imageExpanded && (
                           <button 
                             onClick={(e) => {
                               e.stopPropagation();
                               setImageExpanded(false);
                             }}
                             className="absolute top-3 right-3 text-[10px] bg-black/60 text-white px-2 py-1 rounded-md backdrop-blur-sm border border-white/10 hover:bg-black/80 transition-colors"
                           >
                             Collapse
                           </button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
