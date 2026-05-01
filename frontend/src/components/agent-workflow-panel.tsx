"use client";

import { useRef, useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Bot,
  Brain,
  Check,
  Clipboard,
  Code2,
  ExternalLink,
  FileText,
  Globe,
  Loader2,
  Mail,
  MonitorCog,
  Plug,
  Search,
  Terminal,
  Calendar,
  ListTodo,
  X,
} from "lucide-react";
import { WorkflowStep, WorkflowStepData, StepStatus, StepType } from "./workflow-step";
import {
  classifyAgentTool,
  displayAgentToolName,
  providerLabel,
} from "@/lib/agent-tool-classification";

export type WorkflowRun = {
  run_id: string;
  title: string;
  status: "running" | "completed" | "failed" | "pending";
  steps: WorkflowStepData[];
  started_at?: string;
  completed_at?: string;
};

type Props = {
  run: WorkflowRun | null;
  emptyState?: string;
};

export function AgentWorkflowPanel({
  run,
  emptyState = "Agent is ready...",
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const outputRef = useRef<HTMLDivElement>(null);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [pinnedSelection, setPinnedSelection] = useState(false);
  const [copied, setCopied] = useState(false);

  const focusStep = useMemo(() => {
    if (!run?.steps.length) return null;
    return (
      run.steps.find((step) => step.status === "in_progress") ??
      [...run.steps]
        .reverse()
        .find((step) => step.output || step.error || step.image_b64 || step.command || step.detail) ??
      run.steps[run.steps.length - 1]
    );
  }, [run]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, [run?.steps.length, run?.status]);

  useEffect(() => {
    const el = outputRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, [selectedStepId, run?.steps]);

  if (!run || run.steps.length === 0) {
    return (
      <div className="h-full flex items-center justify-center bg-[#111113] p-8 text-center">
        <div className="rounded-xl border border-zinc-800 bg-[#19191b] px-6 py-5">
          <Bot className="mx-auto mb-3 h-5 w-5 text-zinc-500" />
          <p className="text-[13px] text-zinc-500 font-medium tracking-tight leading-relaxed max-w-[220px]">
            {emptyState}
          </p>
        </div>
      </div>
    );
  }

  const isRunning = run.status === "running";
  const completedSteps = run.steps.filter((step) => step.status === "completed").length;
  const failedSteps = run.steps.filter((step) => step.status === "failed").length;
  const activeStep = focusStep;
  const pinnedStep = pinnedSelection
    ? run.steps.find((step) => step.step_id === selectedStepId)
    : null;
  const selectedStep = pinnedStep ?? activeStep ?? run.steps[run.steps.length - 1];
  const outputText = buildOutputText(selectedStep);

  const copyOutput = async () => {
    if (!outputText || typeof navigator === "undefined") return;
    await navigator.clipboard.writeText(outputText);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  };

  return (
    <div className="h-full flex flex-col bg-[#111113] text-zinc-100">
      <div className="shrink-0 border-b border-zinc-800 bg-[#141416] px-4 py-2">
        <div className="flex items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-zinc-700 bg-[#202023]">
              <MonitorCog className="h-5 w-5 text-zinc-300" />
            </div>
            <div className="min-w-0">
              <div className="truncate text-[14px] font-semibold tracking-tight text-zinc-100">
                {run.title || "CoComputer"}
              </div>
              <div className="mt-1 flex min-w-0 items-center gap-2 text-[12px] text-zinc-400">
                <span className={`h-2 w-2 shrink-0 rounded-full ${statusDotClass(run.status)}`} />
                <span className="shrink-0 font-medium text-zinc-200">
                  {run.status === "completed"
                    ? "Task completed"
                    : run.status === "failed"
                      ? "Task failed"
                      : `Task Progress ${completedSteps}/${run.steps.length}`}
                </span>
                {activeStep && (
                  <>
                    <span className="h-3 w-px shrink-0 bg-zinc-700" />
                    <span className="truncate">{activeStep.title}</span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {failedSteps > 0 && (
              <span className="rounded-md border border-red-500/20 bg-red-500/10 px-2 py-1 text-[11px] font-medium text-red-300">
                {failedSteps} failed
              </span>
            )}
            {isRunning && (
              <span className="inline-flex items-center gap-2 rounded-md border border-emerald-500/20 bg-emerald-500/10 px-2 py-1 text-[11px] font-medium text-emerald-300">
                <Loader2 className="h-3 w-3 animate-spin" />
                Live
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-[minmax(10px,14%)_1fr] gap-0 bg-[#111113] max-md:grid-cols-1">
        <div className="min-h-0 border-r border-zinc-800 bg-[#09090b] max-md:h-[38vh] max-md:border-b max-md:border-r-0">
          <div ref={scrollRef} className="h-full overflow-y-auto px-4 py-4 relative scroll-smooth custom-scrollbar">
            <div className="absolute left-[36px] top-10 bottom-10 w-[1px] bg-zinc-800/40" />
            <div className="space-y-1 relative z-10">
              <AnimatePresence initial={false} mode="popLayout">
                {run.steps.map((step, index) => (
                  <motion.div
                    key={step.step_id}
                    initial={{ opacity: 0, y: 4, filter: "blur(1px)" }}
                    animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                    transition={{ duration: 0.25, ease: [0.23, 1, 0.32, 1] }}
                    className="relative"
                  >
                    <WorkflowStep
                      step={step}
                      isLast={index === run.steps.length - 1 && !isRunning}
                      stepNumber={index + 1}
                      disableDetails
                      onSelect={() => {
                        setSelectedStepId(step.step_id);
                        setPinnedSelection(true);
                      }}
                    />
                  </motion.div>
                ))}
              </AnimatePresence>

              <AnimatePresence>
                {isRunning && (
                  <motion.div
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    className="relative flex items-center gap-4 ml-1.5 py-4"
                  >
                    <div className="w-5 h-5 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center shrink-0 z-10">
                      <div className="w-1 h-1 rounded-full bg-zinc-500 animate-pulse" />
                    </div>
                    <div className="text-[13px] text-zinc-500 font-medium italic tracking-tight">
                      Reasoning...
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>

        <div className="min-h-0 bg-[#111113] p-4">
          <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-zinc-800 bg-[#252525]">
            <div className="flex min-h-10 shrink-0 items-center justify-between gap-3 border-b border-zinc-700/70 bg-[#292929] px-4">
              <div className="flex min-w-0 items-center gap-2">
                {stepIcon(selectedStep.step_type, selectedStep.status)}
                <span className="truncate text-[12px] font-medium text-zinc-300">
                  {selectedStep.title}
                </span>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {pinnedSelection && focusStep?.step_id !== selectedStep.step_id && (
                  <button
                    type="button"
                    onClick={() => {
                      setPinnedSelection(false);
                      setSelectedStepId(focusStep?.step_id ?? null);
                    }}
                    className="rounded-md px-2 py-1 text-[11px] font-medium text-zinc-400 transition-colors hover:bg-white/5 hover:text-zinc-200"
                  >
                    Follow
                  </button>
                )}
                {outputText && (
                  <button
                    type="button"
                    onClick={copyOutput}
                    title="Copy output"
                    className="rounded-md p-1.5 text-zinc-500 transition-colors hover:bg-white/5 hover:text-zinc-200"
                  >
                    {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Clipboard className="h-3.5 w-3.5" />}
                  </button>
                )}
              </div>
            </div>

            <div ref={outputRef} className="min-h-0 flex-1 overflow-auto p-5 custom-scrollbar">
              <DynamicStepOutput step={selectedStep} outputText={outputText} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function DynamicStepOutput({
  step,
  outputText,
}: {
  step: WorkflowStepData;
  outputText: string;
}) {
  const tool = toolName(step);

  if (tool === "run_command" || step.step_type === "terminal") {
    return <TerminalOutput step={step} outputText={outputText} />;
  }

  if (
    tool === "web_search" ||
    tool === "scrape_web_page" ||
    tool === "open_browser" ||
    step.step_type === "browser"
  ) {
    return <WebOutput step={step} outputText={outputText} />;
  }

  if (
    tool === "write_workspace_file" ||
    tool === "read_workspace_file" ||
    tool === "list_workspace_files" ||
    step.step_type === "file_created"
  ) {
    return <FileOutput step={step} outputText={outputText} />;
  }

  if (step.image_b64 || step.step_type === "screenshot") {
    return <ScreenshotOutput step={step} outputText={outputText} />;
  }

  if (step.step_type === "gmail" || step.step_type === "calendar" || step.step_type === "tasks" || step.step_type === "mcp") {
    return <IntegrationOutput step={step} outputText={outputText} />;
  }

  if (!outputText) {
    return (
      <div className="flex h-full items-center justify-center text-[13px] font-medium text-zinc-500">
        {step.status === "in_progress" ? "Working..." : "No output"}
      </div>
    );
  }

  return <PlainOutput text={outputText} />;
}

function TerminalOutput({
  step,
  outputText,
}: {
  step: WorkflowStepData;
  outputText: string;
}) {
  const meta = step.metadata ?? {};
  const result = objectValue(meta.result);
  const command = stringValue(step.command, meta.command, result?.command, step.args?.command);
  const stdout = stringValue(meta.stdout_excerpt, result?.stdout_excerpt);
  const stderr = stringValue(meta.stderr_excerpt, result?.stderr_excerpt, step.error);
  const exitCode = numberValue(meta.exit_code, result?.exit_code);

  return (
    <div className="overflow-hidden rounded-lg border border-zinc-700 bg-[#111111]">
      <div className="flex items-center justify-between border-b border-zinc-700 bg-[#1b1b1c] px-4 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <Terminal className="h-3.5 w-3.5 text-zinc-400" />
          <span className="truncate text-[12px] font-medium text-zinc-300">Terminal</span>
        </div>
        {typeof exitCode === "number" && (
          <span className={`text-[11px] font-medium ${exitCode === 0 ? "text-emerald-300" : "text-red-300"}`}>
            Exit {exitCode}
          </span>
        )}
      </div>

      {command && (
        <pre className="border-b border-zinc-800 px-4 py-3 font-mono text-[12px] leading-6 text-zinc-100">
          <span className="text-fuchsia-400">$</span> {command}
        </pre>
      )}
      {!command && step.status === "in_progress" && (
        <pre className="border-b border-zinc-800 px-4 py-3 font-mono text-[12px] leading-6 text-zinc-500">
          Waiting for command...
        </pre>
      )}

      <div className="space-y-3 p-4">
        {stdout && <OutputBlock label="stdout" text={stdout} />}
        {stderr && <OutputBlock label="stderr" text={stderr} tone="error" />}
        {!stdout && !stderr && (
          <PlainOutput text={step.status === "in_progress" ? "Running..." : outputText || "No terminal output"} />
        )}
      </div>
    </div>
  );
}

function WebOutput({
  step,
  outputText,
}: {
  step: WorkflowStepData;
  outputText: string;
}) {
  const meta = step.metadata ?? {};
  const result = objectValue(meta.result);
  const query = stringValue(meta.query, result?.query, step.args?.query);
  const url = stringValue(meta.url, result?.url, step.args?.url);
  const savedPath = stringValue(meta.saved_path, result?.saved_path);
  const results = normalizeSearchResults(arrayValue(meta.results, result?.results));

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-zinc-700 bg-[#1b1b1c] px-4 py-3">
        <div className="flex items-center gap-2 text-[12px] font-medium text-zinc-300">
          <Globe className="h-3.5 w-3.5 text-zinc-400" />
          <span>{query ? "Web search" : "Web activity"}</span>
        </div>
        {(query || url || savedPath) && (
          <div className="mt-2 space-y-1 font-mono text-[11px] leading-5 text-zinc-400">
            {query && <div>query: {query}</div>}
            {url && <div>url: {url}</div>}
            {savedPath && <div>saved: {savedPath}</div>}
          </div>
        )}
      </div>

      {results.length > 0 ? (
        <div className="space-y-2">
          {results.map((item, index) => (
            <div key={`${item.url}-${index}`} className="rounded-lg border border-zinc-700 bg-[#19191a] p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-[13px] font-semibold leading-5 text-zinc-100">
                    {item.title || item.url || `Result ${index + 1}`}
                  </div>
                  {item.snippet && (
                    <p className="mt-2 text-[12px] leading-5 text-zinc-400">{item.snippet}</p>
                  )}
                </div>
                {item.url && (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noreferrer"
                    className="shrink-0 rounded-md p-1.5 text-zinc-500 transition-colors hover:bg-white/5 hover:text-zinc-200"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                )}
              </div>
              {item.url && <div className="mt-2 truncate font-mono text-[11px] text-zinc-500">{item.url}</div>}
            </div>
          ))}
        </div>
      ) : (
        <PlainOutput text={step.status === "in_progress" ? "Searching..." : outputText || "No web results"} />
      )}
    </div>
  );
}

function FileOutput({
  step,
  outputText,
}: {
  step: WorkflowStepData;
  outputText: string;
}) {
  const meta = step.metadata ?? {};
  const result = objectValue(meta.result);
  const path = stringValue(
    meta.relative_path,
    result?.relative_path,
    step.args?.relative_path,
    meta.workspace_file,
    result?.workspace_file,
    meta.output_path,
  );
  const content = stringValue(meta.content, result?.content, step.args?.content);
  const bytes = numberValue(meta.bytes_written, result?.bytes_written);
  const append = booleanValue(meta.append, result?.append, step.args?.append);

  return (
    <div className="overflow-hidden rounded-lg border border-zinc-700 bg-[#171718]">
      <div className="flex items-center justify-between gap-3 border-b border-zinc-700 bg-[#202021] px-4 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <FileText className="h-3.5 w-3.5 text-zinc-400" />
          <span className="truncate text-[12px] font-medium text-zinc-300">{path || "Workspace file"}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2 text-[11px] text-zinc-500">
          {typeof bytes === "number" && <span>{bytes} bytes</span>}
          {append === true && <span>append</span>}
        </div>
      </div>

      {content ? (
        <pre className="whitespace-pre-wrap break-words p-4 font-mono text-[12px] leading-6 text-zinc-100">
          {content}
        </pre>
      ) : (
        <div className="p-4">
          <PlainOutput text={step.status === "in_progress" ? "Writing file..." : outputText || "No file preview"} />
        </div>
      )}
    </div>
  );
}

function ScreenshotOutput({
  step,
  outputText,
}: {
  step: WorkflowStepData;
  outputText: string;
}) {
  return (
    <div className="space-y-4">
      {step.image_b64 && (
        <div className="overflow-hidden rounded-lg border border-zinc-700 bg-black/30">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={`data:image/png;base64,${step.image_b64}`}
            alt="Agent screenshot"
            className="w-full"
          />
        </div>
      )}
      {outputText && <PlainOutput text={outputText} />}
    </div>
  );
}

function IntegrationOutput({
  step,
  outputText,
}: {
  step: WorkflowStepData;
  outputText: string;
}) {
  const tool = toolName(step);
  const provider =
    step.step_type === "gmail" ||
    step.step_type === "calendar" ||
    step.step_type === "tasks" ||
    step.step_type === "mcp"
      ? step.step_type
      : classifyAgentTool(tool);
  const Icon =
    provider === "gmail"
      ? Mail
      : provider === "calendar"
        ? Calendar
        : provider === "tasks"
          ? ListTodo
          : Plug;
  const meta = step.metadata ?? {};
  const result = objectValue(meta.result);
  const title = tool ? displayAgentToolName(tool) : step.title || `${providerLabel(provider)} Tool`;
  const args = step.args && Object.keys(step.args).length > 0 ? step.args : undefined;

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-zinc-700 bg-[#1b1b1c] px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <Icon className="h-3.5 w-3.5 text-zinc-400" />
            <span className="truncate text-[12px] font-medium text-zinc-300">{title}</span>
          </div>
          <span className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-zinc-400">
            {providerLabel(provider)}
          </span>
        </div>
      </div>

      {args ? <JsonBlock label="Parameters" value={args} /> : null}
      {result ? <JsonBlock label="Result" value={result} /> : null}
      {outputText ? <PlainOutput text={outputText} /> : null}
      {!args && !result && !outputText ? (
        <div className="flex h-full items-center justify-center text-[13px] font-medium text-zinc-500">
          {step.status === "in_progress" ? "Calling integration..." : "No integration output"}
        </div>
      ) : null}
    </div>
  );
}

function JsonBlock({ label, value }: { label: string; value: Record<string, unknown> }) {
  return (
    <div className="rounded-md border border-zinc-800 bg-black/20">
      <div className="border-b border-zinc-800 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
        {label}
      </div>
      <pre className="whitespace-pre-wrap break-words p-3 font-mono text-[12px] leading-6 text-zinc-100">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}

function OutputBlock({
  label,
  text,
  tone = "normal",
}: {
  label: string;
  text: string;
  tone?: "normal" | "error";
}) {
  return (
    <div className={`rounded-md border ${tone === "error" ? "border-red-500/20 bg-red-500/[0.04]" : "border-zinc-800 bg-black/20"}`}>
      <div className={`border-b px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider ${tone === "error" ? "border-red-500/20 text-red-300" : "border-zinc-800 text-zinc-500"}`}>
        {label}
      </div>
      <pre className={`whitespace-pre-wrap break-words p-3 font-mono text-[12px] leading-6 ${tone === "error" ? "text-red-200" : "text-zinc-100"}`}>
        {text}
      </pre>
    </div>
  );
}

function PlainOutput({ text }: { text: string }) {
  return (
    <pre className="whitespace-pre-wrap break-words font-mono text-[12px] leading-6 text-zinc-100">
      {text}
    </pre>
  );
}

function stepIcon(type: StepType, status: StepStatus) {
  if (status === "failed") return <X className="h-3.5 w-3.5 text-red-400" />;
  if (status === "completed") return <Check className="h-3.5 w-3.5 text-emerald-400" />;
  if (type === "thinking") return <Brain className="h-3.5 w-3.5 text-zinc-400" />;
  if (type === "terminal") return <Terminal className="h-3.5 w-3.5 text-zinc-400" />;
  if (type === "browser") return <Globe className="h-3.5 w-3.5 text-zinc-400" />;
  if (type === "tool_call") return <Code2 className="h-3.5 w-3.5 text-zinc-400" />;
  if (type === "file_created") return <FileText className="h-3.5 w-3.5 text-zinc-400" />;
  if (type === "gmail") return <Mail className="h-3.5 w-3.5 text-zinc-400" />;
  if (type === "calendar") return <Calendar className="h-3.5 w-3.5 text-zinc-400" />;
  if (type === "tasks") return <ListTodo className="h-3.5 w-3.5 text-zinc-400" />;
  if (type === "mcp") return <Plug className="h-3.5 w-3.5 text-zinc-400" />;
  if (type === "observation" || type === "screenshot") return <Search className="h-3.5 w-3.5 text-zinc-400" />;
  return <Bot className="h-3.5 w-3.5 text-zinc-400" />;
}

function statusDotClass(status: WorkflowRun["status"]) {
  if (status === "completed") return "bg-emerald-400";
  if (status === "failed") return "bg-red-400";
  if (status === "running") return "bg-emerald-400 animate-pulse";
  return "bg-zinc-500";
}

function buildOutputText(step: WorkflowStepData) {
  const blocks: string[] = [];
  const meta = step.metadata ?? {};
  const result = objectValue(meta.result);

  if (step.detail) blocks.push(step.detail.trim());
  const command = stringValue(step.command, meta.command, result?.command, step.args?.command);
  if (command) blocks.push(`$ ${command.trim()}`);
  if (step.args && Object.keys(step.args).length > 0) {
    blocks.push(JSON.stringify(step.args, null, 2));
  }
  const stdout = stringValue(meta.stdout_excerpt, result?.stdout_excerpt);
  const stderr = stringValue(meta.stderr_excerpt, result?.stderr_excerpt);
  const content = stringValue(meta.content, result?.content, step.args?.content);
  const results = normalizeSearchResults(arrayValue(meta.results, result?.results));
  if (stdout) blocks.push(stdout.trim());
  if (stderr) blocks.push(stderr.trim());
  if (content) blocks.push(content.trim());
  if (results.length > 0) {
    blocks.push(
      results
        .map((item, index) => `${index + 1}. ${item.title || item.url || "Result"}\n${item.url || ""}\n${item.snippet || ""}`)
        .join("\n\n"),
    );
  }
  if (step.output && !blocks.includes(step.output.trim())) blocks.push(step.output.trim());
  if (step.error) blocks.push(`Error:\n${step.error.trim()}`);

  return Array.from(new Set(blocks.filter(Boolean))).join("\n\n");
}

function toolName(step: WorkflowStepData) {
  return stringValue(step.tool, step.metadata?.tool, objectValue(step.metadata?.result)?.tool) ?? "";
}

function objectValue(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined;
}

function arrayValue(...values: unknown[]): unknown[] {
  for (const value of values) {
    if (Array.isArray(value)) return value;
  }
  return [];
}

function stringValue(...values: unknown[]): string | undefined {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value;
  }
  return undefined;
}

function numberValue(...values: unknown[]): number | undefined {
  for (const value of values) {
    if (typeof value === "number") return value;
    if (typeof value === "string" && value.trim() && !Number.isNaN(Number(value))) {
      return Number(value);
    }
  }
  return undefined;
}

function booleanValue(...values: unknown[]): boolean | undefined {
  for (const value of values) {
    if (typeof value === "boolean") return value;
  }
  return undefined;
}

function normalizeSearchResults(values: unknown[]) {
  return values
    .map((value) => {
      const item = objectValue(value);
      if (!item) return null;
      return {
        title: stringValue(item.title, item.name) ?? "",
        url: stringValue(item.url, item.href, item.link) ?? "",
        snippet: stringValue(item.snippet, item.body, item.description, item.summary) ?? "",
      };
    })
    .filter((item): item is { title: string; url: string; snippet: string } => Boolean(item));
}
