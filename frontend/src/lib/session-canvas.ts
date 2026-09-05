/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

import type { RunArtifact } from "@/lib/message-types";
import {
  isDeliverableArtifact,
  isHtmlArtifact,
  isOfficeArtifact,
  isPdfArtifact,
  isCodePath,
  isMarkdownPath,
} from "@/lib/artifact-url";

/** Big session objects that belong on the right-hand canvas, not in chat. */
export type SessionCanvasKind = "plan" | "file" | "document";

export type SessionCanvasDocument = {
  id: string;
  kind: SessionCanvasKind;
  title: string;
  artifact?: RunArtifact;
  /** Inline text for markdown/HTML workspace files. */
  markdown?: string;
  path?: string;
};

export type SessionCanvasOpenReason = "user" | "agent";

const CANVAS_KINDS = new Set([
  "pdf",
  "pdf_report",
  "document",
  "spreadsheet",
  "presentation",
  "html",
  "markdown",
  "plan",
  "file",
]);

const CANVAS_FILE_EXT =
  /\.(md|markdown|html|htm|pdf|docx|xlsx|xls|csv|pptx|txt|py|pyw|ts|tsx|js|jsx|mjs|cjs|json|css|scss|go|rs|java|kt|swift|rb|php|yml|yaml|toml|sh|bash|sql|c|cc|cpp|h|hpp|cs|xml|vue|svelte|lua|r|ipynb)$/i;
const TEXT_FILE_EXT = /\.(md|markdown|txt)$/i;
const CODE_FILE_EXT =
  /\.(py|pyw|ts|tsx|js|jsx|mjs|cjs|json|css|scss|go|rs|java|kt|swift|rb|php|c|cc|cpp|h|hpp|cs|sql|sh|bash|yml|yaml|toml|xml)$/i;

/** Skip empty files; this surface is for reports, decks, and written deliverables. */
const MIN_CANVAS_FILE_CHARS = 1;

function artifactName(artifact: Pick<RunArtifact, "title" | "path">): string {
  return `${artifact.title || ""} ${artifact.path || ""}`.replace(/\\/g, "/");
}

function looksLikePlanName(value: string): boolean {
  return /(^|\/|[\s_-])plan([\s._-]|$)/i.test(value);
}

export function isCanvasWorkspacePath(path: string): boolean {
  const normalized = path.replace(/\\/g, "/").replace(/^\.\//, "");
  if (!normalized.startsWith("outputs/")) return false;
  return (
    CANVAS_FILE_EXT.test(normalized) ||
    isMarkdownPath(normalized) ||
    isCodePath(normalized)
  );
}

export function isCanvasWorkspaceWrite(
  path: string,
  content: string,
  append: boolean,
): boolean {
  if (append) return false;
  if (!isCanvasWorkspacePath(path)) return false;
  return content.trim().length >= MIN_CANVAS_FILE_CHARS;
}

export function isCanvasArtifact(
  artifact: Pick<RunArtifact, "kind" | "path" | "title" | "metadata">,
): boolean {
  if (!isDeliverableArtifact(artifact)) return false;
  const metaKind = String(artifact.metadata?.canvas_kind || "").toLowerCase();
  if (metaKind === "plan" || metaKind === "file" || metaKind === "document") {
    return true;
  }
  if (artifact.kind === "plan" || CANVAS_KINDS.has(artifact.kind)) return true;
  if (isPdfArtifact(artifact) || isHtmlArtifact(artifact) || isOfficeArtifact(artifact)) {
    return true;
  }
  const path = (artifact.path || "").replace(/\\/g, "/");
  if (path.startsWith("outputs/") && (CANVAS_FILE_EXT.test(path) || isCodePath(path) || isMarkdownPath(path))) {
    return true;
  }
  if (CANVAS_FILE_EXT.test(artifact.title || "") || isCodePath(artifact.title || "") || isMarkdownPath(artifact.title || "")) {
    return true;
  }
  return false;
}

export function canvasKindForPath(path: string): SessionCanvasKind {
  const name = path.replace(/\\/g, "/");
  if (looksLikePlanName(name)) return "plan";
  if (
    TEXT_FILE_EXT.test(name) ||
    CODE_FILE_EXT.test(name) ||
    isMarkdownPath(name) ||
    isCodePath(name)
  ) {
    return "file";
  }
  return "document";
}

export function canvasKindForArtifact(
  artifact: Pick<RunArtifact, "kind" | "path" | "title" | "metadata">,
): SessionCanvasKind {
  const metaKind = String(artifact.metadata?.canvas_kind || "").toLowerCase();
  if (metaKind === "plan" || metaKind === "file" || metaKind === "document") {
    return metaKind;
  }
  if (artifact.kind === "plan") return "plan";
  if (looksLikePlanName(artifactName(artifact))) return "plan";
  if (artifact.kind === "markdown" || artifact.kind === "file") return "file";
  const path = (artifact.path || artifact.title || "").replace(/\\/g, "/");
  if (TEXT_FILE_EXT.test(path) || CODE_FILE_EXT.test(path) || isMarkdownPath(path) || isCodePath(path)) {
    return "file";
  }
  return "document";
}

export function canvasHandleLabel(kind: SessionCanvasKind): string {
  if (kind === "plan") return "Created plan";
  if (kind === "file") return "Created file";
  return "Created document";
}

export function canvasKindLabel(kind: SessionCanvasKind): string {
  if (kind === "plan") return "Plan";
  if (kind === "file") return "File";
  return "Document";
}

export function documentFromArtifact(artifact: RunArtifact): SessionCanvasDocument {
  return {
    id: artifact.artifact_id,
    kind: canvasKindForArtifact(artifact),
    title: artifact.title || "Untitled",
    artifact,
    path: artifact.path || undefined,
  };
}

export function documentFromWorkspaceFile(
  path: string,
  content: string,
): SessionCanvasDocument {
  const normalized = path.replace(/\\/g, "/");
  const title = normalized.split("/").pop() || normalized;
  return {
    id: `file:${normalized}`,
    kind: canvasKindForPath(normalized),
    title,
    path: normalized,
    markdown: content,
  };
}

export function upsertCanvasDocument(
  documents: SessionCanvasDocument[],
  next: SessionCanvasDocument,
): SessionCanvasDocument[] {
  const index = documents.findIndex((doc) => doc.id === next.id);
  if (index < 0) return [...documents, next];
  const copy = documents.slice();
  copy[index] = { ...copy[index], ...next };
  return copy;
}

export function looksLikeHtml(value: string): boolean {
  return /<!doctype\s+html|<html[\s>]/i.test(value.trim());
}
