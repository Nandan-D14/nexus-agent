/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { ChatMarkdown } from "@/components/chat-markdown";
import {
  extractMarkdownCitations,
  InlineCitations,
  type CiteRef,
} from "@/components/agent-ui/inline-citations";
import { ArtifactAttachmentCard } from "@/components/artifacts";
import type { RunArtifact } from "@/lib/message-types";
import { cx } from "@/utils/cx";

type Props = {
  content: string;
  className?: string;
  /** When true, skip the sources footer only (inline citation pills still render). */
  hideCitations?: boolean;
  /**
   * Merged turn sources (markdown + search). When provided, used for hover
   * carousels; citation map still comes from markdown links in `content`.
   */
  sources?: CiteRef[];
};

type WorkerEnvelope = {
  status: string;
  summary: string;
  evidence?: unknown;
  artifacts?: unknown;
  remaining_work?: unknown;
  retryable?: unknown;
  sources?: unknown;
  error_code?: unknown;
};

function parseWorkerEnvelope(content: string): WorkerEnvelope | null {
  const raw = content.trim();
  if (!raw.startsWith("{") || !raw.endsWith("}")) return null;
  try {
    const payload = JSON.parse(raw) as unknown;
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
    const obj = payload as Record<string, unknown>;
    if (typeof obj.status !== "string" || typeof obj.summary !== "string") return null;
    const hasEnvelopeKeys =
      "evidence" in obj ||
      "artifacts" in obj ||
      "remaining_work" in obj ||
      "retryable" in obj ||
      "sources" in obj;
    if (!hasEnvelopeKeys) return null;
    return obj as WorkerEnvelope;
  } catch {
    return null;
  }
}

function envelopeArtifacts(envelope: WorkerEnvelope): RunArtifact[] {
  if (!Array.isArray(envelope.artifacts)) return [];
  return envelope.artifacts.flatMap((entry, index) => {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) return [];
    const item = entry as Record<string, unknown>;
    const path = typeof item.path === "string" ? item.path : "";
    const kind = typeof item.kind === "string" && item.kind.trim() ? item.kind : "file";
    const title =
      (typeof item.title === "string" && item.title.trim()) ||
      path.split("/").pop() ||
      `Artifact ${index + 1}`;
    return [
      {
        artifact_id: `envelope-${index}-${title}`,
        run_id: "",
        session_id: "",
        kind,
        title,
        preview: typeof item.preview === "string" ? item.preview : "",
        created_at: null,
        path: path || null,
        url: typeof item.url === "string" ? item.url : null,
        metadata: { role: "deliverable", ...(item.metadata as object | undefined) },
      } satisfies RunArtifact,
    ];
  });
}

function evidenceLines(envelope: WorkerEnvelope): string[] {
  if (!Array.isArray(envelope.evidence)) return [];
  return envelope.evidence
    .filter((line): line is string => typeof line === "string" && line.trim().length > 0)
    .map((line) => line.trim());
}

/** AICSS Text Response — prose + optional markdown-link citation pills. */
export function TextResponse({
  content,
  className,
  hideCitations,
  sources: sourcesProp,
}: Props) {
  const envelope = useMemo(() => parseWorkerEnvelope(content), [content]);
  const displayContent = envelope?.summary?.trim() || content;
  const artifacts = useMemo(
    () => (envelope ? envelopeArtifacts(envelope) : []),
    [envelope],
  );
  const evidence = useMemo(
    () => (envelope ? evidenceLines(envelope) : []),
    [envelope],
  );
  const [detailsOpen, setDetailsOpen] = useState(false);

  const { citationMap, refs: markdownRefs } = useMemo(
    () => extractMarkdownCitations(displayContent),
    [displayContent],
  );
  const sources = sourcesProp ?? markdownRefs;

  return (
    <div className={cx("w-full text-text-primary", className)}>
      <ChatMarkdown
        content={displayContent}
        citationMap={citationMap}
        sources={sources}
      />
      {artifacts.length > 0 ? (
        <div className="mt-3 flex flex-col gap-2">
          {artifacts.map((artifact) => (
            <ArtifactAttachmentCard
              key={artifact.artifact_id}
              artifact={artifact}
              compact
            />
          ))}
        </div>
      ) : null}
      {evidence.length > 0 ? (
        <div className="mt-2">
          <button
            type="button"
            className="inline-flex items-center gap-1 text-[12px] text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
            onClick={() => setDetailsOpen((open) => !open)}
          >
            {detailsOpen ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" />
            )}
            Details
          </button>
          {detailsOpen ? (
            <ul className="mt-1.5 list-disc space-y-1 pl-5 text-[12px] text-zinc-500 dark:text-zinc-400">
              {evidence.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
      {!hideCitations ? <InlineCitations refs={sources} /> : null}
    </div>
  );
}
