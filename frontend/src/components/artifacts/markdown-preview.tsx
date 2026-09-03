/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { ChatMarkdown } from "@/components/chat-markdown";
import type { RunArtifact } from "@/lib/message-types";
import { resolveArtifactUrl } from "@/lib/artifact-url";
import { cn } from "@/lib/utils";

type Props = {
  artifact?: RunArtifact;
  content?: string;
  className?: string;
};

export function MarkdownPreview({ artifact, content, className }: Props) {
  const [text, setText] = useState(content ?? artifact?.preview ?? "");
  const [loading, setLoading] = useState(!content && Boolean(artifact));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (content != null && content !== "") {
      setText(content);
      setLoading(false);
      setError(null);
      return;
    }
    if (!artifact) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    resolveArtifactUrl(artifact, { forPreview: false })
      .then(async (url) => {
        if (cancelled) return;
        if (!url || url.includes("storage.googleapis.com")) {
          setText(artifact.preview || "");
          return;
        }
        const res = await fetch(url);
        if (!res.ok) throw new Error("fetch failed");
        const body = await res.text();
        if (!cancelled) setText(body);
      })
      .catch(() => {
        if (!cancelled) {
          setError("Could not load this file.");
          setText(artifact.preview || "");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [artifact, content]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-zinc-400">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading document…
      </div>
    );
  }

  if (error && !text) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center text-sm text-red-400">
        {error}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "h-full overflow-y-auto custom-scrollbar bg-[#fbfaf6]",
        className,
      )}
    >
      <article className="doc-markdown min-h-full w-full bg-[#fbfaf6] px-10 py-12 text-zinc-900 sm:px-14 sm:py-16">
        {text.trim() ? (
          <ChatMarkdown content={text} />
        ) : (
          <p className="text-sm text-zinc-500">This file is empty.</p>
        )}
      </article>
    </div>
  );
}
