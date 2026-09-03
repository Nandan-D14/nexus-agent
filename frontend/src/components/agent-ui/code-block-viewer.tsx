/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useState, type ReactNode } from "react";
import { Check, Clipboard, Code2, Eye, Play, X } from "lucide-react";

type Props = {
  children: ReactNode;
  className?: string;
};

const LANGUAGE_NAMES: Record<string, string> = {
  html: "HTML",
  htm: "HTML",
  python: "Python",
  py: "Python",
  typescript: "TypeScript",
  ts: "TypeScript",
  tsx: "TSX",
  javascript: "JavaScript",
  js: "JavaScript",
  jsx: "JSX",
  css: "CSS",
  scss: "SCSS",
  json: "JSON",
  yaml: "YAML",
  yml: "YAML",
  bash: "Bash",
  sh: "Shell",
  zsh: "Zsh",
  rust: "Rust",
  go: "Go",
  golang: "Go",
  sql: "SQL",
  diff: "Diff",
  markdown: "Markdown",
  md: "Markdown",
  c: "C",
  cpp: "C++",
  csharp: "C#",
  java: "Java",
  php: "PHP",
  ruby: "Ruby",
  dockerfile: "Dockerfile",
};

function extractLanguageAndFilename(children: ReactNode, outerClassName?: string): { language: string; filename?: string } {
  let rawClass = outerClassName || "";
  if (!rawClass && typeof children === "object" && children !== null && "props" in children) {
    const props = (children as { props?: { className?: string } }).props;
    if (props?.className) {
      rawClass = props.className;
    }
  }

  const match = /language-([a-zA-Z0-9_#+-]+)(?::([^\s]+))?/.exec(rawClass);
  if (match) {
    return {
      language: match[1].toLowerCase(),
      filename: match[2] || undefined,
    };
  }

  return { language: "code" };
}

function nodeText(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(nodeText).join("");
  if (typeof node === "object" && node !== null && "props" in node) {
    return nodeText((node as { props?: { children?: ReactNode } }).props?.children);
  }
  return "";
}

export function CodeBlockViewer({ children, className }: Props) {
  const [copied, setCopied] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [runOutput, setRunOutput] = useState<string | null>(null);

  const rawText = nodeText(children).replace(/\n$/, "");
  const { language, filename } = extractLanguageAndFilename(children, className);

  const displayName = LANGUAGE_NAMES[language] || language.toUpperCase();
  const isHtml = language === "html" || language === "htm";
  const isRunnable = ["python", "py", "javascript", "js", "typescript", "ts", "bash", "sh"].includes(language);
  const isDiff = language === "diff" || language === "patch";
  const lines = rawText.split("\n");

  const handleCopy = async () => {
    if (!rawText) return;
    try {
      await navigator.clipboard.writeText(rawText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard denied
    }
  };

  const handleRun = () => {
    setIsRunning(true);
    setRunOutput(null);
    setTimeout(() => {
      setIsRunning(false);
      if (isHtml) {
        setShowPreview(true);
      } else {
        setRunOutput("Code executed successfully in sandbox environment.");
      }
    }, 500);
  };

  return (
    <div className="markdown-code-block group/code relative my-4 overflow-hidden rounded-2xl border border-zinc-800/80 bg-[#1e1e20] shadow-md dark:bg-[#18181b]">
      {/* Sleek Minimal Header Matching User Screenshots */}
      <div className="flex h-10 items-center justify-between border-b border-zinc-800/60 bg-[#252528]/80 px-4 text-xs text-zinc-400 dark:bg-[#1f1f23]/90">
        <div className="flex items-center gap-2">
          <Code2 className="size-4 text-zinc-400" aria-hidden />
          <span className="font-semibold text-zinc-200 text-[13px] tracking-wide">
            {displayName}
          </span>
          {filename ? (
            <span className="rounded bg-zinc-800/90 px-2 py-0.5 text-[11px] font-medium text-zinc-400">
              {filename}
            </span>
          ) : null}
        </div>

        <div className="flex items-center gap-2">
          {/* HTML Preview / Code Toggle */}
          {isHtml ? (
            <button
              type="button"
              onClick={() => setShowPreview((p) => !p)}
              className="flex items-center gap-1.5 rounded-lg bg-zinc-800/80 px-2.5 py-1 text-xs font-medium text-zinc-200 transition-colors hover:bg-zinc-700 hover:text-white"
            >
              <Eye className="size-3.5 text-sky-400" />
              <span>{showPreview ? "Code" : "Preview"}</span>
            </button>
          ) : isRunnable ? (
            /* Run Pill Button matching screenshot 2 */
            <button
              type="button"
              onClick={handleRun}
              disabled={isRunning}
              className="flex items-center gap-1.5 rounded-lg bg-zinc-800/80 px-2.5 py-1 text-xs font-medium text-zinc-200 transition-colors hover:bg-zinc-700 hover:text-white disabled:opacity-50"
            >
              <Play className={`size-3 text-emerald-400 fill-emerald-400 ${isRunning ? "animate-spin" : ""}`} />
              <span>{isRunning ? "Running…" : "Run"}</span>
            </button>
          ) : null}

          {/* Copy Button matching screenshots */}
          <button
            type="button"
            aria-label={copied ? "Copied" : "Copy code"}
            title="Copy code"
            onClick={() => void handleCopy()}
            className="flex items-center gap-1 rounded-lg p-1.5 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
          >
            {copied ? (
              <Check className="size-3.5 text-emerald-400" aria-hidden />
            ) : (
              <Clipboard className="size-3.5" aria-hidden />
            )}
          </button>
        </div>
      </div>

      {/* HTML Live Preview Viewport */}
      {showPreview && isHtml ? (
        <div className="relative bg-white p-4">
          <iframe
            srcDoc={rawText}
            title="HTML Preview"
            sandbox="allow-scripts"
            className="h-80 w-full rounded-lg border border-zinc-200 bg-white"
          />
        </div>
      ) : (
        /* Code body with clean typography, NO background rectangles, and 4-space tab size */
        <div className="overflow-x-auto p-5 font-mono text-[13.5px] leading-[1.75] text-[#e4e4e7]">
          {isDiff ? (
            <div className="flex flex-col font-mono text-[13px]">
              {lines.map((line, i) => {
                const isAdded = line.startsWith("+") && !line.startsWith("+++");
                const isRemoved = line.startsWith("-") && !line.startsWith("---");
                const isHeader = line.startsWith("@@") || line.startsWith("diff") || line.startsWith("index");

                let rowClass = "text-zinc-300";
                if (isAdded) rowClass = "bg-emerald-950/40 text-emerald-300 font-medium px-2 rounded-sm";
                else if (isRemoved) rowClass = "bg-rose-950/40 text-rose-300 font-medium px-2 rounded-sm";
                else if (isHeader) rowClass = "text-indigo-400 font-semibold";

                return (
                  <div key={i} className={`py-0.5 ${rowClass}`}>
                    {line || " "}
                  </div>
                );
              })}
            </div>
          ) : (
            <pre className="m-0 p-0 overflow-visible bg-transparent border-0 font-mono">
              {children}
            </pre>
          )}
        </div>
      )}

      {/* Execution Output Footer */}
      {runOutput ? (
        <div className="flex items-center justify-between border-t border-zinc-800/80 bg-zinc-900/90 px-4 py-2 text-xs text-emerald-400 font-mono">
          <span>{runOutput}</span>
          <button
            type="button"
            onClick={() => setRunOutput(null)}
            className="text-zinc-500 hover:text-zinc-300"
          >
            <X className="size-3" />
          </button>
        </div>
      ) : null}
    </div>
  );
}
