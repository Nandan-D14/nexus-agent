/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { isValidElement, useMemo, useState, type ReactNode } from "react";
import { Check, Clipboard } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import rehypeHighlight from "rehype-highlight";
import type { Components } from "react-markdown";
import { CitationInline } from "@/components/agent-ui/citation-inline";
import type { CiteRef } from "@/components/agent-ui/inline-citations";

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

function CodeBlockWithCopy({ children }: { children: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const text = nodeText(children).replace(/\n$/, "");

  const handleCopy = async () => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard may be denied.
    }
  };

  return (
    <div className="markdown-code-block group/code relative">
      <button
        type="button"
        aria-label={copied ? "Copied" : "Copy code"}
        onClick={() => void handleCopy()}
        className="absolute top-2.5 right-2.5 z-10 flex size-7 items-center justify-center rounded-lg border border-zinc-300 bg-white text-zinc-500 opacity-100 transition-colors hover:bg-zinc-50 hover:text-zinc-800 md:opacity-0 md:group-hover/code:opacity-100 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
      >
        {copied ? (
          <Check className="size-3.5 text-emerald-500" aria-hidden />
        ) : (
          <Clipboard className="size-3.5" aria-hidden />
        )}
      </button>
      {children}
    </div>
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
    pre({ children, ...props }) {
      return (
        <CodeBlockWithCopy>
          <pre {...props}>{children}</pre>
        </CodeBlockWithCopy>
      );
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
    table({ children, ...props }) {
      return (
        <div className="markdown-table-wrapper">
          <table {...props}>{children}</table>
        </div>
      );
    },
    img({ src, alt, ...props }) {
      if (!src) return null;
      // eslint-disable-next-line @next/next/no-img-element -- markdown content may use arbitrary remote URLs
      return <img {...props} src={src} alt={alt ?? ""} loading="lazy" />;
    },
  };
}

export function ChatMarkdown({ content, citationMap, sources }: Props) {
  const components = useMemo(
    () => buildComponents(citationMap, sources),
    [citationMap, sources],
  );

  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }]]}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
