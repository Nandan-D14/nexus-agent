/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useCallback, useEffect, useRef, useState, type ComponentType } from "react";
import {
  ChevronRight,
  Code2,
  Globe,
  LineChart,
  Presentation,
  Search,
  Sparkles,
  Table2,
  Terminal,
  Workflow,
} from "lucide-react";

import { providerLogo } from "@/lib/connectors";
import { cx } from "@/utils/cx";

type CategoryStarter = {
  id: string;
  label: string;
  prompt: string;
  icon: ComponentType<{ className?: string }>;
};

type ConnectorStarter = {
  id: string;
  label: string;
  prompt: string;
  provider: string;
};

const CATEGORY_STARTERS: CategoryStarter[] = [
  {
    id: "websites",
    label: "Websites",
    icon: Globe,
    prompt: "Create a modern marketing website for my product with a hero, features, pricing, and a contact section.",
  },
  {
    id: "slides",
    label: "Slides",
    icon: Presentation,
    prompt: "Make an 8-slide presentation that explains the product, the problem it solves, and a clear call to action.",
  },
  {
    id: "report",
    label: "Report",
    icon: LineChart,
    prompt: "Write a concise research report with key findings, analysis, and recommendations.",
  },
  {
    id: "sheets",
    label: "Sheets",
    icon: Table2,
    prompt: "Build a spreadsheet to track monthly budget, expenses, and a summary dashboard.",
  },
  {
    id: "workflows",
    label: "Workflows",
    icon: Workflow,
    prompt: "Design an automation workflow that triages incoming requests and drafts a reply.",
  },
  {
    id: "code",
    label: "Code",
    icon: Code2,
    prompt: "Write and execute code in the workspace to solve my task.",
  },
  {
    id: "research",
    label: "Research",
    icon: Search,
    prompt: "Deeply research a topic online, verify sources, and summarize the findings.",
  },
  {
    id: "terminal",
    label: "Terminal",
    icon: Terminal,
    prompt: "Run terminal commands to set up, test, or inspect the environment.",
  },
  {
    id: "other",
    label: "Other",
    icon: Sparkles,
    prompt: "Help me with a custom task, question, or project.",
  },
];

function GoogleProductIcon({ provider, className }: { provider: string; className?: string }) {
  const src = providerLogo(provider);
  if (!src) return null;
  return (
    // eslint-disable-next-line @next/next/no-img-element -- current Google product marks
    <img src={src} alt="" className={cx("object-contain", className)} />
  );
}

const CONNECTOR_STARTERS: ConnectorStarter[] = [
  {
    id: "calendar",
    label: "Check today's calendar",
    prompt: "Check today's calendar",
    provider: "google_calendar",
  },
  {
    id: "gmail",
    label: "Summarize my unread emails",
    prompt: "Summarize my unread emails",
    provider: "gmail",
  },
  {
    id: "drive",
    label: "Find a file in my Drive",
    prompt: "Find a file in my Drive",
    provider: "google_drive",
  },
];

type Props = {
  onInsertPrompt: (prompt: string) => void;
};

export function LandingPromptStarters({ onInsertPrompt }: Props) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [canScrollMore, setCanScrollMore] = useState(false);

  const updateOverflow = useCallback(() => {
    const el = scrollerRef.current;
    if (!el) return;
    setCanScrollMore(el.scrollLeft + el.clientWidth < el.scrollWidth - 8);
  }, []);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    updateOverflow();
    el.addEventListener("scroll", updateOverflow, { passive: true });
    const observer = new ResizeObserver(updateOverflow);
    observer.observe(el);
    return () => {
      el.removeEventListener("scroll", updateOverflow);
      observer.disconnect();
    };
  }, [updateOverflow]);

  return (
    <div className="flex w-full flex-col items-stretch gap-5">
      <div className="space-y-2.5">
        <p className="px-0.5 text-[11px] font-medium tracking-wide text-white/70 drop-shadow-[0_1px_8px_rgba(0,0,0,0.55)]">
          Featured in Agent mode
        </p>
        <div className="relative">
          <div
            ref={scrollerRef}
            className="no-scrollbar flex items-center gap-2 overflow-x-auto pr-10"
          >
            {CATEGORY_STARTERS.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onInsertPrompt(item.prompt)}
                  className={cx(
                    "inline-flex shrink-0 items-center gap-2 rounded-full border border-white/20 bg-black/35 px-3.5 py-1.5",
                    "text-[13px] font-medium text-white/90 shadow-[0_1px_8px_rgba(0,0,0,0.25)] backdrop-blur-sm",
                    "transition-colors hover:border-white/35 hover:bg-black/50",
                  )}
                >
                  <Icon className="h-3.5 w-3.5 text-white/80" />
                  {item.label}
                </button>
              );
            })}
          </div>
          {canScrollMore ? (
            <button
              type="button"
              aria-label="Show more starters"
              className="absolute right-0 top-1/2 z-10 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full border border-white/25 bg-black/55 text-white/90 shadow-sm backdrop-blur-sm hover:bg-black/75"
              onClick={() => {
                scrollerRef.current?.scrollBy({ left: 180, behavior: "smooth" });
              }}
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          ) : null}
        </div>
      </div>

      <div className="flex flex-col gap-1">
        {CONNECTOR_STARTERS.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => onInsertPrompt(item.prompt)}
            className="flex items-center gap-3 rounded-lg px-1 py-1.5 text-left text-[14px] text-white/85 transition-colors hover:bg-black/25 hover:text-white"
          >
            <GoogleProductIcon provider={item.provider} className="h-5 w-5 shrink-0" />
            <span className="drop-shadow-[0_1px_8px_rgba(0,0,0,0.55)]">{item.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
