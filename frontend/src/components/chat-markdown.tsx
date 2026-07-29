/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import rehypeHighlight from "rehype-highlight";
import type { Components } from "react-markdown";

type Props = {
  content: string;
  /** When set, markdown links get a numbered citation badge after the anchor. */
  citationMap?: Map<string, number>;
};

function buildComponents(citationMap?: Map<string, number>): Components {
  return {
    a({ href, children, ...props }) {
      const n = href && citationMap ? citationMap.get(href) : undefined;
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
          {n != null ? (
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
    code({ className, children, ...props }) {
      const text = String(children).replace(/\n$/, "");
      const classNameValue = Array.isArray(className)
        ? className.join(" ")
        : className;
      return (
        <code {...props} className={classNameValue}>
          {text}
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

export function ChatMarkdown({ content, citationMap }: Props) {
  const components = useMemo(
    () => buildComponents(citationMap),
    [citationMap],
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
