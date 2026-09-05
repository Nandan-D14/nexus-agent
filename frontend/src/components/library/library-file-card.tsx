/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useState } from "react";
import { Download, Eye, ExternalLink, Loader2, MoreVertical } from "lucide-react";
import type { LibraryItem } from "@/lib/message-types";
import {
  downloadArtifactFile,
  durableInlineUrl,
  getPreviewUrl,
  previewKind,
  resolveArtifactUrl,
} from "@/lib/artifact-url";
import { ArtifactIcon } from "@/components/artifacts";
import {
  Dropdown,
  DropdownGroup,
  DropdownItem,
  DropdownPopover,
  DropdownTrigger,
} from "@/components/base/dropdown/dropdown";

const PDF_THUMBNAIL_PARAMS = "#toolbar=0&navpanes=0&scrollbar=0&view=FitH";
const LIBRARY_URL_OPTIONS = { allowSandbox: false } as const;

type Props = {
  item: LibraryItem;
  view: "grid" | "list";
  onPreview: (url: string | null) => void;
  onOpenSession: () => void;
};

export function LibraryFileCard({ item, view, onPreview, onOpenSession }: Props) {
  const { artifact } = item;
  const [previewUrl, setPreviewUrl] = useState<string | null>(
    durableInlineUrl(getPreviewUrl(artifact)),
  );
  const [loading, setLoading] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const kind = previewKind(artifact);
  const previewable = kind !== "none";
  const title = artifact.title || artifact.kind.replace(/_/g, " ");

  const handlePreview = async () => {
    setLoading(true);
    try {
      const url = previewable
        ? previewUrl ||
          (await resolveArtifactUrl(artifact, { forPreview: true, ...LIBRARY_URL_OPTIONS }))
        : null;
      if (url) setPreviewUrl(url);
      onPreview(url);
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async () => {
    setLoading(true);
    try {
      await downloadArtifactFile(artifact, LIBRARY_URL_OPTIONS);
    } finally {
      setLoading(false);
    }
  };

  const menu = (
    <div
      onClick={(event) => event.stopPropagation()}
      onPointerDown={(event) => event.stopPropagation()}
    >
      <Dropdown isOpen={menuOpen} onOpenChange={setMenuOpen}>
        <DropdownTrigger
          aria-label={`Actions for ${title}`}
          className="rounded-md p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
        >
          <MoreVertical className="size-4" />
        </DropdownTrigger>
        <DropdownPopover aria-label="File actions" placement="bottom end" className="w-[180px]">
          <DropdownGroup>
            <DropdownItem
              onSelect={() => {
                setMenuOpen(false);
                void handlePreview();
              }}
            >
              <Eye className="size-4" />
              <span>Preview</span>
            </DropdownItem>
            <DropdownItem
              onSelect={() => {
                setMenuOpen(false);
                void handleDownload();
              }}
            >
              <Download className="size-4" />
              <span>Download</span>
            </DropdownItem>
            <DropdownItem
              onSelect={() => {
                setMenuOpen(false);
                onOpenSession();
              }}
            >
              <ExternalLink className="size-4" />
              <span>Open in session</span>
            </DropdownItem>
          </DropdownGroup>
        </DropdownPopover>
      </Dropdown>
    </div>
  );

  if (view === "list") {
    return (
      <div className="group flex items-center gap-3 rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2.5 transition-colors hover:bg-zinc-100 dark:border-zinc-800 dark:bg-[#141414] dark:hover:bg-[#1a1a1c]">
        <button
          type="button"
          onClick={() => void handlePreview()}
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
        >
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-zinc-200 dark:bg-zinc-800">
            {loading ? (
              <Loader2 className="size-4 animate-spin text-zinc-400" />
            ) : (
              <ArtifactIcon artifact={artifact} className="size-4" />
            )}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">
              {title}
            </span>
            {artifact.preview ? (
              <span className="mt-0.5 block truncate text-xs text-zinc-500">{artifact.preview}</span>
            ) : null}
          </span>
        </button>
        {menu}
      </div>
    );
  }

  return (
    <div className="group flex flex-col overflow-hidden rounded-xl border border-zinc-200 bg-zinc-50 shadow-sm transition-colors hover:border-zinc-300 dark:border-zinc-800 dark:bg-[#141414] dark:hover:border-zinc-700 dark:hover:bg-[#1a1a1c]">
      <div className="flex items-center gap-2 border-b border-zinc-200 px-3 py-2 dark:border-zinc-800">
        <ArtifactIcon artifact={artifact} className="size-4 shrink-0" />
        <button
          type="button"
          onClick={() => void handlePreview()}
          className="min-w-0 flex-1 truncate text-left text-sm font-medium text-zinc-800 dark:text-zinc-200"
          title={title}
        >
          {title}
        </button>
        {menu}
      </div>
      <button
        type="button"
        onClick={() => void handlePreview()}
        className="relative aspect-[16/10] w-full overflow-hidden bg-zinc-100 text-left dark:bg-[#1c1c1e]"
        aria-label={`Open ${title}`}
      >
        {kind === "image" && previewUrl ? (
          // eslint-disable-next-line @next/next/no-img-element -- remote artifact thumbnail
          <img
            src={previewUrl}
            alt=""
            className="h-full w-full object-cover opacity-80 transition-opacity group-hover:opacity-100"
          />
        ) : kind === "html" && previewUrl ? (
          <iframe
            src={previewUrl}
            title={`${title} thumbnail`}
            className="pointer-events-none h-[200%] w-[200%] origin-top-left scale-50 bg-white opacity-80"
            sandbox="allow-scripts allow-forms allow-modals"
          />
        ) : kind === "pdf" && previewUrl ? (
          <object
            data={`${previewUrl}${PDF_THUMBNAIL_PARAMS}`}
            type="application/pdf"
            className="pointer-events-none h-[200%] w-[200%] origin-top-left scale-50 bg-white opacity-80"
            aria-label={`${title} thumbnail`}
          />
        ) : (
          <div className="flex h-full flex-col gap-2 p-4">
            {artifact.preview ? (
              <p className="line-clamp-6 whitespace-pre-wrap text-left text-[12px] leading-5 text-zinc-500 dark:text-zinc-400">
                {artifact.preview}
              </p>
            ) : (
              <div className="flex flex-1 flex-col items-center justify-center gap-2 opacity-50">
                <ArtifactIcon artifact={artifact} className="size-10" />
                <span className="text-[10px] uppercase tracking-wide text-zinc-500">
                  {previewable ? "Preview" : "Download to open"}
                </span>
              </div>
            )}
          </div>
        )}
      </button>
    </div>
  );
}
