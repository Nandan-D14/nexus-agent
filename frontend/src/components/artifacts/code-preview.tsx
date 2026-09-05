/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { ChatMarkdown } from "@/components/chat-markdown";
import type { RunArtifact } from "@/lib/message-types";
import {
  codeLanguageForArtifact,
  codeLanguageForPath,
  resolveArtifactUrl,
} from "@/lib/artifact-url";
import { cn } from "@/lib/utils";

type Props = {
  artifact?: RunArtifact;
  content?: string;
  filename?: string;
  language?: string;
  className?: string;
};

function fenceSource(language: string, text: string): string {
  const lang = language || "text";
  return `\`\`\`${lang}\n${text.replace(/\n$/, "")}\n\`\`\``;
}

export function CodePreview({ artifact, content, filename, language, className }: Props) {
  const [text, setText] = useState(content ?? "");
  const [loading, setLoading] = useState(!content && Boolean(artifact));
  const [error, setError] = useState<string | null>(null);
  const name =
    filename ||
    (artifact?.path || "").replace(/\\/g, "/").split("/").pop() ||
    artifact?.title ||
    "file";
  const lang =
    language ||
    (artifact ? codeLanguageForArtifact(artifact) : codeLanguageForPath(name));

  useEffect(() => {
    if (content != null) {
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

  const markdown = useMemo(() => fenceSource(lang, text), [lang, text]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center gap-2 bg-[#111113] text-sm text-zinc-400">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading file…
      </div>
    );
  }

  if (error && !text) {
    return (
      <div className="flex h-full items-center justify-center bg-[#111113] px-6 text-center text-sm text-red-400">
        {error}
      </div>
    );
  }

  return (
    <div className={cn("h-full overflow-y-auto custom-scrollbar bg-[#111113] p-4", className)}>
      <div className="mb-3 font-mono text-[11px] text-zinc-500">{name}</div>
      {text.trim() ? (
        <ChatMarkdown content={markdown} />
      ) : (
        <p className="px-4 py-10 text-center text-sm text-zinc-500">This file is empty.</p>
      )}
    </div>
  );
}
