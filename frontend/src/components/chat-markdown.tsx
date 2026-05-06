/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import rehypeHighlight from "rehype-highlight";
import type { Components } from "react-markdown";

type Props = {
  content: string;
};

const components: Components = {
  a({ href, children, ...props }) {
    return (
      <a
        {...props}
        href={href}
        target="_blank"
        rel="noopener noreferrer"
      >
        {children}
      </a>
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
    return <img {...props} src={src} alt={alt ?? ""} loading="lazy" />;
  },
};

export function ChatMarkdown({ content }: Props) {
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
