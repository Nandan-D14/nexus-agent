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
  MapPin,
  Clock,
  User,
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
  | "tasks";

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
  if (type === "completion" || status === "completed") return <Check className="w-[11px] h-[11px] text-emerald-400" />;
  return <Bot className="w-[11px] h-[11px] text-zinc-400" />;
}


export function WorkflowStep({ step, isLast = false, disableDetails = false, onSelect }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [imageExpanded, setImageExpanded] = useState(false);

  const isFailed = step.status === "failed";
  const isInProgress = step.status === "in_progress";
  
  const hasDetails = !disableDetails && Boolean(
    step.detail || step.output || step.error || step.command || step.image_b64 || (step.args && Object.keys(step.args).length > 0)
  );
  const isSelectable = Boolean(onSelect);

  return (
    <div className="relative group">
      <div className="flex items-start gap-4">
        {/* Minimal Timeline Node */}
        <div className="relative flex flex-col items-center pt-[6px] shrink-0 ml-[6px]">
          <div 
            className={`w-6 h-6 rounded-full flex items-center justify-center z-10 transition-colors duration-300 ${
              isFailed 
                ? "bg-red-500/10 border border-red-500/20" 
                : isInProgress
                  ? "bg-[#1c1c1f] border border-zinc-700 shadow-sm"
                  : "bg-[#0e0e10] border border-zinc-800"
            }`}
          >
            {getStepIcon(step.step_type, step.status)}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0 pt-1 pb-2">
          <div 
            className={`flex items-start justify-between gap-4 rounded-md transition-colors ${(hasDetails || isSelectable) ? "cursor-pointer hover:bg-white/[0.02] -ml-2 -mt-1 p-2" : ""}`}
            onClick={() => {
              onSelect?.();
              if (hasDetails) setExpanded(!expanded);
            }}
          >
            <div className="flex-1 min-w-0">
              <div className={`text-[13.5px] leading-snug tracking-tight font-medium ${isFailed ? "text-red-400" : isInProgress ? "text-zinc-200" : "text-zinc-300"}`}>
                {step.title}
              </div>
            </div>
            
            <div className="flex items-center gap-3 shrink-0 mt-0.5">
              <span className="text-[10px] text-zinc-500/70 font-mono tracking-tighter">
                {formatTime(step.created_at)}
              </span>
              {hasDetails && (
                <div className={`w-4 h-4 flex items-center justify-center transition-colors ${expanded ? "text-zinc-400" : "text-zinc-600"}`}>
                  {expanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                </div>
              )}
            </div>
          </div>

          {/* Collapsible Details Panel (Terminal style) */}
          <AnimatePresence>
            {expanded && hasDetails && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.25, ease: [0.23, 1, 0.32, 1] }}
                className="overflow-hidden"
              >
                <div className="pt-2 space-y-2 pb-1">
                  {/* Detailed Description */}
                  {step.detail && (
                    <div className="text-[12.5px] text-zinc-400 leading-relaxed pl-1">
                      {step.detail}
                    </div>
                  )}

                  {/* Terminal / Command */}
                  {step.command && (
                    <div className="rounded border border-zinc-800/40 bg-[#09090b]">
                      <div className="px-3 py-1.5 border-b border-zinc-800/40 bg-[#121214] flex items-center gap-2">
                        <Terminal className="w-3 h-3 text-zinc-500" />
                        <span className="text-[9.5px] font-bold text-zinc-500 uppercase tracking-widest">Command</span>
                      </div>
                      <div className="p-3 overflow-x-auto custom-scrollbar">
                        <code className="text-[11.5px] text-zinc-300 font-mono whitespace-pre">{step.command}</code>
                      </div>
                    </div>
                  )}

                  {/* JSON Args */}
                  {step.args && Object.keys(step.args).length > 0 && (
                    <div className="rounded border border-zinc-800/40 bg-[#09090b]">
                      <div className="px-3 py-1.5 border-b border-zinc-800/40 bg-[#121214] flex items-center gap-2">
                        <Code2 className="w-3 h-3 text-zinc-500" />
                        <span className="text-[9.5px] font-bold text-zinc-500 uppercase tracking-widest">Parameters</span>
                      </div>
                      <div className="p-3 overflow-x-auto custom-scrollbar">
                        <pre className="text-[11.5px] text-zinc-400 font-mono">
                          {JSON.stringify(step.args, null, 2)}
                        </pre>
                      </div>
                    </div>
                  )}

                  {/* Output */}
                  {step.output && (
                    <div className="rounded border border-zinc-800/40 bg-[#09090b]">
                      <div className="px-3 py-1.5 border-b border-zinc-800/40 bg-[#121214] flex items-center gap-2">
                        <Terminal className="w-3 h-3 text-zinc-500" />
                        <span className="text-[9.5px] font-bold text-zinc-500 uppercase tracking-widest">Output</span>
                      </div>
                      <div className="p-3 overflow-x-auto custom-scrollbar max-h-64">
                        <pre className="text-[11.5px] text-zinc-400 font-mono whitespace-pre-wrap break-all leading-relaxed">
                          {step.output.length > 2000
                            ? step.output.slice(0, 2000) + "\n\n... [Output truncated]"
                            : step.output}
                        </pre>
                      </div>
                    </div>
                  )}

                  {/* Error */}
                  {step.error && (
                    <div className="rounded border border-red-500/20 bg-red-500/[0.03]">
                      <div className="px-3 py-1.5 border-b border-red-500/20 bg-red-500/10 flex items-center gap-2">
                        <X className="w-3 h-3 text-red-400" />
                        <span className="text-[9.5px] font-bold text-red-400 uppercase tracking-widest">Error</span>
                      </div>
                      <div className="p-3 overflow-x-auto custom-scrollbar max-h-64">
                        <p className="text-[11.5px] text-red-300 font-mono whitespace-pre-wrap break-all leading-relaxed">
                          {step.error}
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Gmail Visualizer */}
                  {step.step_type === "gmail" && step.args && (
                    <div className="rounded border border-zinc-800/40 bg-[#09090b] p-3 space-y-2">
                       <div className="flex items-center justify-between border-b border-zinc-800/40 pb-2">
                        <div className="flex items-center gap-2">
                          <Mail className="w-3.5 h-3.5 text-zinc-500" />
                          <span className="text-[11px] font-bold text-zinc-300 uppercase tracking-widest">Gmail</span>
                        </div>
                      </div>
                      <div className="space-y-1">
                        <div className="text-[13px] font-semibold text-zinc-200">{step.args.subject as string}</div>
                        <div className="flex items-center gap-2 text-[11px] text-zinc-500">
                          <User className="w-3 h-3" />
                          <span>{step.args.to as string}</span>
                        </div>
                        <div className="text-[12px] text-zinc-400 leading-relaxed whitespace-pre-wrap pt-1 border-t border-zinc-800/20">
                          {step.args.body as string}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Calendar Visualizer */}
                  {step.step_type === "calendar" && step.args && (
                    <div className="rounded border border-zinc-800/40 bg-[#09090b] p-3 space-y-2">
                       <div className="flex items-center justify-between border-b border-zinc-800/40 pb-2">
                        <div className="flex items-center gap-2">
                          <Calendar className="w-3.5 h-3.5 text-zinc-500" />
                          <span className="text-[11px] font-bold text-zinc-300 uppercase tracking-widest">Calendar</span>
                        </div>
                      </div>
                      <div className="space-y-1.5">
                        <div className="text-[13px] font-semibold text-zinc-200">{step.args.summary as string}</div>
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
                          <div className="text-[12px] text-zinc-500 leading-relaxed pt-1">
                            {step.args.description as string}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Tasks Visualizer */}
                  {step.step_type === "tasks" && step.args && (
                    <div className="rounded border border-zinc-800/40 bg-[#09090b] p-3 space-y-2">
                       <div className="flex items-center justify-between border-b border-zinc-800/40 pb-2">
                        <div className="flex items-center gap-2">
                          <ListTodo className="w-3.5 h-3.5 text-zinc-500" />
                          <span className="text-[11px] font-bold text-zinc-300 uppercase tracking-widest">Task</span>
                        </div>
                      </div>
                      <div className="space-y-1.5">
                        <div className="flex items-start gap-2">
                          <div className="w-4 h-4 rounded border border-zinc-700 mt-0.5 shrink-0" />
                          <div className="text-[13px] font-semibold text-zinc-200">{step.args.title as string}</div>
                        </div>
                        {Boolean(step.args.notes) && (
                          <div className="text-[12px] text-zinc-400 pl-6 leading-relaxed">
                            {step.args.notes as string}
                          </div>
                        )}
                        {Boolean(step.args.due) && (
                          <div className="flex items-center gap-1.5 pl-6 text-[10px] text-zinc-500">
                            <Clock className="w-3 h-3" />
                            <span>Due: {new Date(step.args.due as string).toLocaleDateString()}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Screenshot */}
                  {step.image_b64 && (
                    <div className="rounded border border-zinc-800/40 bg-[#09090b]">
                       <div className="px-3 py-1.5 border-b border-zinc-800/40 bg-[#121214] flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Eye className="w-3 h-3 text-zinc-500" />
                          <span className="text-[9.5px] font-bold text-zinc-500 uppercase tracking-widest">Vision</span>
                        </div>
                        <button 
                          onClick={(e) => {
                            e.stopPropagation();
                            setImageExpanded(!imageExpanded);
                          }}
                          className="text-[10px] text-zinc-500 hover:text-zinc-300 transition-colors"
                        >
                          {imageExpanded ? "Collapse" : "Expand"}
                        </button>
                      </div>
                      <div className={`p-1.5 transition-all duration-500 ${imageExpanded ? "" : "max-h-48 overflow-hidden relative"}`}>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={`data:image/png;base64,${step.image_b64}`}
                          alt="Screenshot"
                          className="w-full rounded-[4px] border border-zinc-800/30"
                        />
                        {!imageExpanded && (
                          <div className="absolute bottom-0 left-0 right-0 h-24 bg-gradient-to-t from-[#09090b] to-transparent pointer-events-none" />
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
