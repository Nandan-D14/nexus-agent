/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { Download, Loader2 } from "lucide-react";
import {
  Artifact,
  ArtifactAction,
  ArtifactActions,
  ArtifactDescription,
  ArtifactHeader,
  ArtifactTitle,
} from "@/components/ai-elements/artifact";
import { ArtifactIconTile } from "@/components/artifacts/artifact-icon";
import { cn } from "@/lib/utils";
import {
  canvasHandleLabel,
  type SessionCanvasKind,
} from "@/lib/session-canvas";
import type { RunArtifact } from "@/lib/message-types";

type Props = {
  kind: SessionCanvasKind;
  title: string;
  subtitle?: string;
  artifact?: RunArtifact;
  onOpen: () => void;
  onDownload?: () => void;
  downloading?: boolean;
};

export function CanvasHandleCard({
  kind,
  title,
  subtitle,
  artifact,
  onOpen,
  onDownload,
  downloading = false,
}: Props) {
  return (
    <Artifact className="w-full max-w-xl rounded-xl border-zinc-200 bg-zinc-50 shadow-sm dark:border-zinc-800 dark:bg-[#141414]">
      <ArtifactHeader className="gap-3 border-b-0 bg-transparent px-3.5 py-3 dark:bg-transparent">
        <button
          type="button"
          onClick={onOpen}
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
        >
          {artifact ? (
            <ArtifactIconTile artifact={artifact} />
          ) : (
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-zinc-200 bg-zinc-100 text-[10px] font-semibold uppercase tracking-wide text-zinc-600 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
              {kind === "plan" ? "Plan" : kind === "file" ? "File" : "Doc"}
            </span>
          )}
          <div className="min-w-0">
            <ArtifactTitle className="truncate text-[14px] text-zinc-800 dark:text-zinc-100">
              {canvasHandleLabel(kind)}
            </ArtifactTitle>
            <ArtifactDescription className="mt-0.5 truncate text-[12px] text-zinc-500">
              {subtitle || title}
            </ArtifactDescription>
          </div>
        </button>
        {onDownload ? (
          <ArtifactActions className="shrink-0">
            <ArtifactAction
              tooltip="Download"
              label="Download"
              icon={downloading ? Loader2 : Download}
              onClick={onDownload}
              disabled={downloading}
              className={cn(downloading && "[&_svg]:animate-spin")}
            />
          </ArtifactActions>
        ) : null}
      </ArtifactHeader>
    </Artifact>
  );
}
