/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

type Props = {
  url: string;
  title: string;
  slideCount?: number;
};

export function SlidePreview({ url, title, slideCount }: Props) {
  const countLabel =
    typeof slideCount === "number" && slideCount > 0
      ? `${slideCount} slide${slideCount === 1 ? "" : "s"}`
      : null;

  return (
    <div className="flex h-full min-h-0 flex-col bg-[#0b1220]">
      <div className="flex min-h-0 flex-1 items-center justify-center p-4 sm:p-8">
        <div className="relative aspect-video w-full max-w-5xl overflow-hidden rounded-xl border border-white/10 bg-slate-950 shadow-[0_28px_80px_rgba(0,0,0,0.55)]">
          <iframe
            src={url}
            title={title}
            className="h-full w-full bg-slate-950"
            sandbox="allow-scripts allow-forms allow-modals"
          />
        </div>
      </div>
      <div className="shrink-0 border-t border-white/10 bg-[#080d18] px-4 py-2.5 text-center text-[12px] text-slate-400">
        Slide preview
        {countLabel ? ` · ${countLabel}` : ""}
        {" · "}
        scroll inside the deck to move between slides
      </div>
    </div>
  );
}
