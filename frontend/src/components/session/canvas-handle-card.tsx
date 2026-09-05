/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
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
    <Artifact className="w-full max-w-xl rounded-xl border-card-border bg-background-secondary-default shadow-sm">
      <ArtifactHeader className="gap-3 border-b-0 bg-transparent px-3.5 py-3">
        <button
          type="button"
          onClick={onOpen}
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
        >
          {artifact ? (
            <ArtifactIconTile artifact={artifact} />
          ) : (
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-card-border bg-background-tertiary-default text-[10px] font-semibold uppercase tracking-wide text-text-secondary">
              {kind === "plan" ? "Plan" : kind === "file" ? "File" : "Doc"}
            </span>
          )}
          <div className="min-w-0">
            <ArtifactTitle className="truncate text-[14px] text-text-primary">
              {canvasHandleLabel(kind)}
            </ArtifactTitle>
            <ArtifactDescription className="mt-0.5 truncate text-[12px] text-text-secondary">
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
