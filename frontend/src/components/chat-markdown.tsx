/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { isValidElement, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  Check,
  Clipboard,
  Info,
  Lightbulb,
  AlertTriangle,
  AlertCircle,
  ShieldAlert,
  Table,
  CheckSquare2,
  Square,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import remarkMath from "remark-math";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import type { Components } from "react-markdown";
import { CitationInline } from "@/components/agent-ui/citation-inline";
import type { CiteRef } from "@/components/agent-ui/inline-citations";
import { CodeBlockViewer } from "@/components/agent-ui/code-block-viewer";
import { MermaidDiagram } from "@/components/agent-ui/mermaid-diagram";
import { normalizeStreamingMarkdown } from "@/lib/stream-markdown-fixer";

type Props = {
  content: string;
  /** When set, markdown links get a citation pill after the anchor. */
  citationMap?: Map<string, number>;
  /** Full turn sources for citation hover carousels. */
  sources?: CiteRef[];
};

function nodeText(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(nodeText).join("");
  if (isValidElement(node)) {
    return nodeText((node.props as { children?: ReactNode }).children);
  }
  return "";
}

function extractLanguage(children: ReactNode): string {
  if (isValidElement(children)) {
    const props = children.props as { className?: string };
    if (props?.className) {
      const match = /language-([a-zA-Z0-9_-]+)/.exec(props.className);
      if (match) return match[1].toLowerCase();
    }
  }
  return "";
}

function BlockquoteAlert({ children }: { children: ReactNode }) {
  const text = nodeText(children).trim();
  const alertMatch = text.match(/^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]/i);

  if (alertMatch) {
    const alertType = alertMatch[1].toUpperCase();
    const config = {
      NOTE: {
        border: "border-blue-500/50 dark:border-blue-500/40",
        bg: "bg-blue-500/5 dark:bg-blue-500/10",
        text: "text-blue-700 dark:text-blue-300",
        icon: Info,
      },
      TIP: {
        border: "border-emerald-500/50 dark:border-emerald-500/40",
        bg: "bg-emerald-500/5 dark:bg-emerald-500/10",
        text: "text-emerald-700 dark:text-emerald-300",
        icon: Lightbulb,
      },
      IMPORTANT: {
        border: "border-purple-500/50 dark:border-purple-500/40",
        bg: "bg-purple-500/5 dark:bg-purple-500/10",
        text: "text-purple-700 dark:text-purple-300",
        icon: AlertCircle,
      },
      WARNING: {
        border: "border-amber-500/50 dark:border-amber-500/40",
        bg: "bg-amber-500/5 dark:bg-amber-500/10",
        text: "text-amber-700 dark:text-amber-300",
        icon: AlertTriangle,
      },
      CAUTION: {
        border: "border-red-500/50 dark:border-red-500/40",
        bg: "bg-red-500/5 dark:bg-red-500/10",
        text: "text-red-700 dark:text-red-300",
        icon: ShieldAlert,
      },
    }[alertType] || {
      border: "border-blue-500/50",
      bg: "bg-blue-500/5",
      text: "text-blue-700 dark:text-blue-300",
      icon: Info,
    };

    const Icon = config.icon;

    return (
      <div
        className={`my-4 flex gap-3 rounded-lg border-l-4 p-3.5 ${config.border} ${config.bg}`}
      >
        <Icon className={`mt-0.5 size-4 shrink-0 ${config.text}`} aria-hidden />
        <div className="min-w-0 flex-1 text-[13.5px] leading-relaxed [&>p]:m-0">
          {children}
        </div>
      </div>
    );
  }

  return (
    <blockquote className="my-4 border-l-4 border-zinc-300 pl-4 italic text-zinc-600 dark:border-zinc-700 dark:text-zinc-400">
      {children}
    </blockquote>
  );
}

function TableWithActions({ children, ...props }: { children: ReactNode }) {
  const [copied, setCopied] = useState<"md" | "csv" | null>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const tableRef = useRef<HTMLTableElement>(null);

  const checkScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 4);
    setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 4);
  };

  useEffect(() => {
    checkScroll();
    window.addEventListener("resize", checkScroll);
    return () => window.removeEventListener("resize", checkScroll);
  }, []);

  const handleCopyMarkdown = async () => {
    const text = nodeText(children);
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied("md");
      window.setTimeout(() => setCopied(null), 1600);
    } catch {
      // Clipboard denied
    }
  };

  const handleCopyCSV = async () => {
    if (!tableRef.current) return;
    const rows = Array.from(tableRef.current.querySelectorAll("tr"));
    const csv = rows
      .map((row) =>
        Array.from(row.querySelectorAll("th, td"))
          .map((cell) => `"${(cell.textContent || "").replace(/"/g, '""').trim()}"`)
          .join(","),
      )
      .join("\n");

    try {
      await navigator.clipboard.writeText(csv);
      setCopied("csv");
      window.setTimeout(() => setCopied(null), 1600);
    } catch {
      // Clipboard denied
    }
  };

  return (
    <div className="group/table relative my-4 w-full max-w-full overflow-hidden rounded-xl border border-zinc-200 bg-zinc-50/50 shadow-sm dark:border-zinc-800 dark:bg-zinc-950/40">
      {/* Table toolbar */}
      <div className="flex h-8 items-center justify-between border-b border-zinc-200/80 bg-zinc-100/90 px-3 text-xs text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900/90 dark:text-zinc-400">
        <span className="flex items-center gap-1.5 font-mono text-[11px] font-semibold uppercase tracking-wider text-zinc-600 dark:text-zinc-300">
          <Table className="size-3.5 text-indigo-500" />
          Table
        </span>

        <div className="flex items-center gap-1">
          <button
            type="button"
            title="Copy as CSV"
            onClick={() => void handleCopyCSV()}
            className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium text-zinc-500 transition-colors hover:bg-zinc-200 hover:text-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
          >
            {copied === "csv" ? (
              <>
                <Check className="size-3 text-emerald-500" />
                <span className="text-emerald-500">CSV Copied</span>
              </>
            ) : (
              <span>CSV</span>
            )}
          </button>

          <button
            type="button"
            title="Copy Table Markdown"
            onClick={() => void handleCopyMarkdown()}
            className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium text-zinc-500 transition-colors hover:bg-zinc-200 hover:text-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
          >
            {copied === "md" ? (
              <>
                <Check className="size-3 text-emerald-500" />
                <span className="text-emerald-500">Copied</span>
              </>
            ) : (
              <>
                <Clipboard className="size-3" />
                <span>Copy</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Horizontal scroll container with left/right scroll shadows */}
      <div className="relative w-full max-w-full">
        {canScrollLeft ? (
          <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-6 bg-gradient-to-r from-zinc-200/60 dark:from-zinc-900/80 to-transparent" />
        ) : null}

        <div
          ref={scrollRef}
          onScroll={checkScroll}
          className="markdown-table-wrapper w-full max-w-full overflow-x-auto p-2"
        >
          <table
            ref={tableRef}
            {...props}
            className="w-full min-w-max border-collapse text-left text-sm"
          >
            {children}
          </table>
        </div>

        {canScrollRight ? (
          <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-6 bg-gradient-to-l from-zinc-200/60 dark:from-zinc-900/80 to-transparent" />
        ) : null}
      </div>
    </div>
  );
}

function DetailsCollapsible({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <details
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
      className="my-3 overflow-hidden rounded-lg border border-zinc-200 bg-zinc-50/50 text-sm dark:border-zinc-800 dark:bg-zinc-900/30"
    >
      {children}
    </details>
  );
}

function SummaryHeader({ children }: { children: ReactNode }) {
  return (
    <summary className="flex cursor-pointer select-none items-center gap-2 px-3.5 py-2.5 font-medium text-zinc-700 transition-colors hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800/50">
      {children}
    </summary>
  );
}

function buildComponents(
  citationMap?: Map<string, number>,
  sources?: CiteRef[],
): Components {
  return {
    a({ href, children, ...props }) {
      const n = href && citationMap ? citationMap.get(href) : undefined;
      const active =
        href && sources?.length
          ? sources.find((s) => s.url === href)
          : undefined;

      return (
        <>
          <a
            {...props}
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-indigo-600 underline underline-offset-4 transition-colors hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300"
          >
            {children}
          </a>
          {active && sources?.length ? (
            <CitationInline active={active} sources={sources} />
          ) : n != null ? (
            <a
              href={`#cite-ref-${n}`}
              className="ml-0.5 inline-flex items-center rounded-md bg-background-tertiary-default px-1 align-super text-[10px] font-semibold text-text-secondary no-underline hover:bg-background-tertiary-hover hover:text-text-primary"
              aria-label={`Source ${n}`}
              onClick={(e) => {
                e.stopPropagation();
              }}
            >
              {n}
            </a>
          ) : null}
        </>
      );
    },
    pre({ children }) {
      const lang = extractLanguage(children);
      const rawText = nodeText(children).trim();

      if (lang === "mermaid") {
        return <MermaidDiagram chart={rawText} />;
      }

      return <CodeBlockViewer>{children}</CodeBlockViewer>;
    },
    code({ className, children, ...props }) {
      const classNameValue = Array.isArray(className)
        ? className.join(" ")
        : className;
      return (
        <code {...props} className={classNameValue}>
          {children}
        </code>
      );
    },
    blockquote({ children }) {
      return <BlockquoteAlert>{children}</BlockquoteAlert>;
    },
    table({ children, ...props }) {
      return <TableWithActions {...props}>{children}</TableWithActions>;
    },
    details({ children }) {
      return <DetailsCollapsible>{children}</DetailsCollapsible>;
    },
    summary({ children }) {
      return <SummaryHeader>{children}</SummaryHeader>;
    },
    input({ type, checked, ...props }) {
      if (type === "checkbox") {
        return checked ? (
          <CheckSquare2 className="mr-1.5 inline-block size-4 text-emerald-500 align-sub" />
        ) : (
          <Square className="mr-1.5 inline-block size-4 text-zinc-400 align-sub dark:text-zinc-600" />
        );
      }
      return <input type={type} checked={checked} {...props} />;
    },
    img({ src, alt, ...props }) {
      if (!src) return null;
      // eslint-disable-next-line @next/next/no-img-element -- markdown content may use arbitrary remote URLs
      return (
        <img
          {...props}
          src={src}
          alt={alt ?? ""}
          loading="lazy"
          className="my-4 h-auto max-w-full rounded-xl border border-zinc-200 dark:border-zinc-800 shadow-md"
        />
      );
    },
  };
}

export function ChatMarkdown({ content, citationMap, sources }: Props) {
  const normalizedContent = useMemo(
    () => normalizeStreamingMarkdown(content),
    [content],
  );

  const components = useMemo(
    () => buildComponents(citationMap, sources),
    [citationMap, sources],
  );

  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks, remarkMath]}
        rehypePlugins={[rehypeKatex, [rehypeHighlight, { detect: true, ignoreMissing: true }]]}
        components={components}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
}
