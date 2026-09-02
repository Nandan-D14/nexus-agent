/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useState } from "react";
import { FileText, Loader2, X } from "lucide-react";

import { authenticatedFetch } from "@/lib/api-client";
import type { UploadedInputFile } from "@/lib/message-types";
import { cx } from "@/utils/cx";

export function isImageUploadedFile(file: UploadedInputFile): boolean {
  const mime = (file.mime_type || "").toLowerCase();
  if (mime.startsWith("image/")) return true;
  return /\.(png|jpe?g|gif|webp|bmp|svg|heic|heif)$/i.test(file.name || file.path || "");
}

export function uploadedFileKindLabel(file: UploadedInputFile): string {
  if (isImageUploadedFile(file)) return "Image";
  const name = (file.name || file.path || "").toLowerCase();
  if (name.endsWith(".pdf")) return "PDF";
  if (/\.(pptx?|key)$/i.test(name)) return "Presentation";
  if (/\.(xlsx?|csv)$/i.test(name)) return "Spreadsheet";
  return "Document";
}

function ImageAttachmentThumb({
  file,
  className,
}: {
  file: UploadedInputFile;
  className?: string;
}) {
  const [src, setSrc] = useState(file.previewUrl || "");

  useEffect(() => {
    if (file.previewUrl) {
      setSrc(file.previewUrl);
      return;
    }
    const artifactId = file.artifact_id;
    if (!artifactId || !isImageUploadedFile(file)) return;
    const controller = new AbortController();
    let objectUrl = "";
    void authenticatedFetch(`/api/v1/artifacts/${encodeURIComponent(artifactId)}/content`, {
      signal: controller.signal,
    })
      .then((response) => (response.ok ? response.blob() : null))
      .then((blob) => {
        if (!blob || controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      })
      .catch(() => undefined);
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [file.artifact_id, file.previewUrl, file.mime_type, file.name, file.path]);

  if (!src) {
    return (
      <span className={cx("flex items-center justify-center bg-background-secondary-default", className)}>
        <FileText className="h-6 w-6 text-blue-400" />
      </span>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={file.name} className={cx("object-cover", className)} />
  );
}

export function UploadedFilePreview({
  file,
  onRemove,
  compact = false,
}: {
  file: UploadedInputFile;
  onRemove?: () => void;
  compact?: boolean;
}) {
  const image = isImageUploadedFile(file);

  if (image) {
    return (
      <span className="relative inline-flex overflow-hidden rounded-2xl border border-border-button-default bg-background-secondary-default">
        <ImageAttachmentThumb
          file={file}
          className={compact ? "h-16 w-16" : "h-20 w-20"}
        />
        {file.uploading ? (
          <span className="absolute inset-0 flex items-center justify-center bg-black/45">
            <Loader2 className="h-5 w-5 animate-spin text-white" />
          </span>
        ) : null}
        {onRemove && !file.uploading ? (
          <button
            type="button"
            onClick={onRemove}
            className="absolute right-1 top-1 flex size-5 items-center justify-center rounded-full bg-black/70 text-white hover:bg-black"
            aria-label={`Remove ${file.name}`}
          >
            <X className="h-3 w-3" />
          </button>
        ) : null}
      </span>
    );
  }

  return (
    <span className="relative inline-flex max-w-[240px] items-center gap-2.5 rounded-2xl border border-border-button-default bg-background-secondary-default px-3 py-2">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-blue-500/15 text-blue-400">
        {file.uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
      </span>
      <span className="min-w-0">
        <span className="block truncate text-[13px] font-medium text-text-primary">{file.name}</span>
        <span className="block text-[11px] text-text-tertiary">
          {file.uploading ? "Uploading..." : uploadedFileKindLabel(file)}
        </span>
      </span>
      {onRemove && !file.uploading ? (
        <button
          type="button"
          onClick={onRemove}
          className="ml-1 text-text-tertiary hover:text-text-primary"
          aria-label={`Remove ${file.name}`}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      ) : null}
    </span>
  );
}

export function UploadedFilePreviewList({
  files,
  onRemove,
  align = "start",
}: {
  files: UploadedInputFile[];
  onRemove?: (path: string) => void;
  align?: "start" | "end";
}) {
  if (files.length === 0) return null;
  return (
    <div className={cx("flex flex-wrap gap-2", align === "end" ? "justify-end" : "justify-start")}>
      {files.map((file) => (
        <UploadedFilePreview
          key={file.path || file.artifact_id || file.name}
          file={file}
          onRemove={onRemove ? () => onRemove(file.path) : undefined}
        />
      ))}
    </div>
  );
}
