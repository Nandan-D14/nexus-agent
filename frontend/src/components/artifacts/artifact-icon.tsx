/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import {
  Database,
  File,
  FileCode,
  FileSpreadsheet,
  FileText,
  FileType,
  Image as ImageIcon,
  Presentation,
} from "lucide-react";
import type { RunArtifact } from "@/lib/message-types";
import {
  isCodeArtifact,
  isCsvArtifact,
  isHtmlArtifact,
  isMarkdownArtifact,
  isOfficeArtifact,
  isPdfArtifact,
  isPlainTextArtifact,
  isPresentationArtifact,
  isSpreadsheetArtifact,
} from "@/lib/artifact-url";

type ArtifactLike = Pick<RunArtifact, "kind" | "metadata" | "path" | "title">;

/** Tailwind tints for the icon glyph and the rounded tile behind it. */
export type ArtifactAccent = { icon: string; tile: string };

const ACCENTS: Record<string, ArtifactAccent> = {
  pdf: { icon: "text-red-400", tile: "bg-red-500/10 border-red-500/20" },
  document: { icon: "text-blue-400", tile: "bg-blue-500/10 border-blue-500/20" },
  spreadsheet: { icon: "text-emerald-400", tile: "bg-emerald-500/10 border-emerald-500/20" },
  csv: { icon: "text-teal-400", tile: "bg-teal-500/10 border-teal-500/20" },
  presentation: { icon: "text-orange-400", tile: "bg-orange-500/10 border-orange-500/20" },
  markdown: { icon: "text-violet-400", tile: "bg-violet-500/10 border-violet-500/20" },
  code: { icon: "text-lime-400", tile: "bg-lime-500/10 border-lime-500/20" },
  html: { icon: "text-amber-400", tile: "bg-amber-500/10 border-amber-500/20" },
  image: { icon: "text-sky-400", tile: "bg-sky-500/10 border-sky-500/20" },
  data: { icon: "text-emerald-400", tile: "bg-emerald-500/10 border-emerald-500/20" },
  default: { icon: "text-zinc-400", tile: "bg-zinc-800 border-zinc-700" },
};

/** Normalizes an artifact to one of the accent/icon families above. */
function artifactFamily(artifact: ArtifactLike): keyof typeof ACCENTS {
  if (isPdfArtifact(artifact)) return "pdf";
  if (artifact.kind === "image" || artifact.kind === "screenshot") return "image";
  if (isCsvArtifact(artifact)) return "csv";
  if (isSpreadsheetArtifact(artifact)) return "spreadsheet";
  if (isPresentationArtifact(artifact)) return "presentation";
  if (isMarkdownArtifact(artifact) || isPlainTextArtifact(artifact)) return "markdown";
  if (isCodeArtifact(artifact)) return "code";
  if (isHtmlArtifact(artifact)) return "html";
  if (artifact.kind === "document") return "document";
  if (artifact.kind === "data" || artifact.kind === "json") {
    return "data";
  }
  if (isOfficeArtifact(artifact)) {
    const contentType = String(artifact.metadata?.content_type ?? "").toLowerCase();
    if (contentType.includes("presentationml") || contentType.includes("ms-powerpoint")) {
      return "presentation";
    }
    if (contentType.includes("spreadsheetml") || contentType.includes("ms-excel")) {
      return "spreadsheet";
    }
    return "document";
  }
  return "default";
}

export function artifactAccent(artifact: ArtifactLike): ArtifactAccent {
  return ACCENTS[artifactFamily(artifact)];
}

/** Short uppercase type chip, e.g. PDF / DOCX / XLSX. */
export function artifactBadge(artifact: ArtifactLike): string {
  switch (artifactFamily(artifact)) {
    case "pdf":
      return "PDF";
    case "document":
      return "DOCX";
    case "spreadsheet":
      return "XLSX";
    case "csv":
      return "CSV";
    case "presentation":
      return "PPTX";
    case "markdown":
      return isPlainTextArtifact(artifact) ? "TXT" : "MD";
    case "code":
      return (artifact.path || artifact.title || "CODE").replace(/\\/g, "/").split(".").pop()?.toUpperCase() || "CODE";
    case "html":
      return "HTML";
    case "image":
      return "Image";
    default:
      return artifact.kind.replace(/_/g, " ").toUpperCase();
  }
}

export function ArtifactIcon({
  artifact,
  className = "w-5 h-5",
}: {
  artifact: ArtifactLike;
  className?: string;
}) {
  const { icon } = artifactAccent(artifact);
  const cls = `${className} ${icon}`;

  switch (artifactFamily(artifact)) {
    case "pdf":
      return <FileText className={cls} />;
    case "image":
      return <ImageIcon className={cls} />;
    case "spreadsheet":
      return <FileSpreadsheet className={cls} />;
    case "csv":
      return <FileSpreadsheet className={cls} />;
    case "presentation":
      return <Presentation className={cls} />;
    case "markdown":
      return <FileText className={cls} />;
    case "code":
      return <FileCode className={cls} />;
    case "document":
      return <FileType className={cls} />;
    case "html":
      return <FileText className={cls} />;
    case "data":
      return <Database className={cls} />;
    default:
      return <File className={cls} />;
  }
}

/** Icon inside its tinted rounded tile, as used in card rows and the viewer header. */
export function ArtifactIconTile({
  artifact,
  className = "h-10 w-10",
  iconClassName = "w-5 h-5",
}: {
  artifact: ArtifactLike;
  className?: string;
  iconClassName?: string;
}) {
  const { tile } = artifactAccent(artifact);
  return (
    <div
      className={`flex shrink-0 items-center justify-center rounded-lg border ${tile} ${className}`}
    >
      <ArtifactIcon artifact={artifact} className={iconClassName} />
    </div>
  );
}
