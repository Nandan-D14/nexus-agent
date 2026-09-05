/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { Component, type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle } from "lucide-react";
import { ChatMarkdown } from "./chat-markdown";

// We intentionally avoid importing the Thesys SDK at module top level.
// It registers React context providers and pulls in framer-motion, both of
// which crash Next.js' static prerender step (useContext returns null because
// the providers are not mounted on the server). Instead we load it lazily in
// the browser via a dynamic import triggered from useEffect.
type C1ComponentType = React.ComponentType<{
  c1Response: string;
  isStreaming: boolean;
  onError?: (error: { code: number; c1Response: string }) => void;
}>;
type ThesysThemeProviderType = React.ComponentType<{
  children: ReactNode;
  mode?: "light" | "dark";
}>;

let cachedC1: C1ComponentType | null = null;
let cachedThemeProvider: ThesysThemeProviderType | null = null;

async function loadThesysComponents(): Promise<{
  C1: C1ComponentType;
  ThemeProvider: ThesysThemeProviderType;
}> {
  if (cachedC1 && cachedThemeProvider) return { C1: cachedC1, ThemeProvider: cachedThemeProvider };
  const mod = await import("@thesysai/genui-sdk");
  cachedC1 = mod.C1Component as C1ComponentType;
  cachedThemeProvider = mod.ThemeProvider as ThesysThemeProviderType;
  return { C1: cachedC1, ThemeProvider: cachedThemeProvider };
}

interface GenerativeUICardProps {
  componentType?: string;
  title: string;
  /** Raw C1 DSL response string from the Thesys C1 API. */
  component: unknown;
}

class C1ErrorBoundary extends Component<
  { children: ReactNode; onError: (error: Error) => void },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error) {
    this.props.onError(error);
  }

  render() {
    if (this.state.hasError) return null;
    return this.props.children;
  }
}

/**
 * Props the Thesys SDK calls .map() on internally — they MUST be arrays.
 * When a weak LLM emits a single object or string instead of an array for
 * any of these, the SDK throws "r.map is not a function".
 */
const C1_ARRAY_PROPS = new Set([
  "children", "items", "cards", "tiles", "metrics", "infoItems", "actions",
  "rows", "columns", "headers",
  "slides", "pages", "paragraphs", "fields",
  "data", "series", "labels", "datasets", "options", "points",
  "sources", "followUpText",
]);

function sanitizeC1Structure(data: unknown): unknown {
  if (Array.isArray(data)) return data.map(sanitizeC1Structure);
  if (data !== null && typeof data === "object") {
    const obj = data as Record<string, unknown>;
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(obj)) {
      if (C1_ARRAY_PROPS.has(k)) {
        if (v == null || v === "") out[k] = [];
        else if (Array.isArray(v)) out[k] = v.map(sanitizeC1Structure);
        else if (typeof v === "object") out[k] = [sanitizeC1Structure(v)];
        else if (typeof v === "string") out[k] = k === "sources" ? [{ title: v }] : [v];
        else out[k] = [];
      } else {
        out[k] = sanitizeC1Structure(v);
      }
    }
    return out;
  }
  return data;
}

function sanitizeDslString(raw: string): string {
  // Match all <content>...</content> tags globally and sanitize their inner JSON contents
  const sanitized = raw.replace(
    /(<content\b[^>]*>)([\s\S]*?)(<\/content>)/g,
    (match, tagOpen, inner, tagClose) => {
      try {
        const parsed = JSON.parse(inner.trim());
        const sanitizedJson = sanitizeC1Structure(parsed);
        return `${tagOpen}${JSON.stringify(sanitizedJson)}${tagClose}`;
      } catch {
        return match;
      }
    }
  );

  // If the whole string is JSON (or after trimming it starts with JSON syntax)
  const trimmed = sanitized.trim();
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try {
      const parsed = JSON.parse(trimmed);
      return JSON.stringify(sanitizeC1Structure(parsed));
    } catch {
      // Not valid JSON
    }
  }

  return sanitized;
}

function decodeEntities(html: string): string {
  if (typeof document === "undefined") return html;
  const txt = document.createElement("textarea");
  txt.innerHTML = html;
  return txt.value;
}

export function GenerativeUICard({ title: _title, component }: GenerativeUICardProps) {
  const dslString = useMemo(() => {
    let raw: string;
    if (typeof component === "string") raw = component;
    else if (component == null) return "";
    else {
      try {
        raw = JSON.stringify(component);
      } catch {
        return String(component);
      }
    }
    // Sanitize before handing to the SDK so malformed responses don't crash
    try {
      return sanitizeDslString(raw);
    } catch {
      return raw;
    }
  }, [component]);

  const customMarkdownContent = useMemo(() => {
    if (!dslString) return null;
    const match = dslString.match(/<custommarkdown>([\s\S]*?)<\/custommarkdown>/);
    return match ? decodeEntities(match[1]) : null;
  }, [dslString]);

  const [C1, setC1] = useState<C1ComponentType | null>(null);
  const [ThesysThemeProvider, setThesysThemeProvider] = useState<ThesysThemeProviderType | null>(null);
  const [renderFailure, setRenderFailure] = useState<{
    dsl: string;
    message: string;
  } | null>(null);
  const renderError =
    renderFailure?.dsl === dslString ? renderFailure.message : null;
  const reportRenderError = useCallback((message: string) => {
    console.error("C1 component render error:", message, "with dslString:", dslString);
    fetch("/api/v1/health/log", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dslString, error: message }),
    }).catch((e) => console.error("Failed to send debug log:", e));

    window.setTimeout(() => {
      setRenderFailure((current) =>
        current?.dsl === dslString
          ? current
          : { dsl: dslString, message },
      );
    }, 0);
  }, [dslString]);

  useEffect(() => {
    let cancelled = false;
    loadThesysComponents()
      .then(({ C1: Comp, ThemeProvider }) => {
        if (!cancelled) {
          setC1(() => Comp);
          setThesysThemeProvider(() => ThemeProvider);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) reportRenderError(error instanceof Error ? error.message : "Failed to load Thesys renderer");
      });
    return () => {
      cancelled = true;
    };
  }, [reportRenderError]);

  return (
    <div className="my-2 w-full overflow-hidden rounded-2xl bg-transparent">
      <div className="themed-dark c1-host p-0 font-sans text-zinc-100">
        {customMarkdownContent ? (
          <ChatMarkdown content={customMarkdownContent} />
        ) : dslString && C1 && ThesysThemeProvider && !renderError ? (
          <C1ErrorBoundary key={dslString} onError={(error) => reportRenderError(error.message)}>
            <ThesysThemeProvider mode="dark">
              <C1
                key={dslString}
                c1Response={dslString}
                isStreaming={false}
                onError={(error) => reportRenderError(`Thesys render error ${error.code}`)}
              />
            </ThesysThemeProvider>
          </C1ErrorBoundary>
        ) : renderError ? (
          <div className="flex items-center gap-2 rounded-xl border border-border/60 bg-muted/30 p-3 text-sm text-zinc-500">
            <AlertCircle className="h-4 w-4" />
            <span>Thesys returned malformed UI. Try again.</span>
          </div>
        ) : dslString ? (
          <div className="flex items-center gap-2 rounded-xl border border-border/60 bg-muted/30 p-3 text-sm text-zinc-500">
            <AlertCircle className="h-4 w-4 animate-pulse" />
            <span>Loading visual…</span>
          </div>
        ) : (
          <div className="flex items-center gap-2 rounded-xl border border-border/60 bg-muted/30 p-3 text-sm text-zinc-500">
            <AlertCircle className="h-4 w-4" />
            <span>No component data</span>
          </div>
        )}
      </div>
    </div>
  );
}

export default GenerativeUICard;
