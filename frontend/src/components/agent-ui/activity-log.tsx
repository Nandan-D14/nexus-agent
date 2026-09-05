/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import type { ReactNode } from "react";
import {
  Bot,
  BookOpen,
  Calendar,
  Circle,
  Check,
  Eye,
  FileText,
  Globe,
  Layers,
  LayoutGrid,
  ListTodo,
  Loader2,
  Mail,
  Plug,
  RotateCw,
  Sparkles,
  Terminal as TerminalIcon,
  Wrench,
  X,
} from "lucide-react";
import type { AgentToolProvider } from "@/lib/agent-tool-classification";
import { cx } from "@/utils/cx";

/** Horizontal center of the rail line, in px — also half the node box. */
const NODE_SIZE = 22;
const RAIL_X = NODE_SIZE / 2;

export type ActivityStatus = "pending" | "running" | "ok" | "failed" | "retry";

/* ------------------------------------------------------------------ */
/*  Duration formatting                                                */
/* ------------------------------------------------------------------ */

/**
 * Human-readable elapsed time. Raw seconds ("1187s") are unreadable past a
 * minute, so anything longer rolls up into minutes and hours.
 */
export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "";
  if (ms < 1000) return `${Math.round(ms)}ms`;

  const totalSeconds = ms / 1000;
  if (totalSeconds < 10) {
    const rounded = Math.round(totalSeconds * 10) / 10;
    return Number.isInteger(rounded) ? `${rounded}s` : `${rounded.toFixed(1)}s`;
  }

  const whole = Math.round(totalSeconds);
  if (whole < 60) return `${whole}s`;

  const minutes = Math.floor(whole / 60);
  const seconds = whole % 60;
  if (minutes < 60) return `${minutes}m ${seconds}s`;

  const hours = Math.floor(minutes / 60);
  return `${hours}h ${String(minutes % 60).padStart(2, "0")}m`;
}

/* ------------------------------------------------------------------ */
/*  Iconography                                                        */
/* ------------------------------------------------------------------ */

export function getToolIcon(provider: AgentToolProvider, className: string) {
  switch (provider) {
    case "terminal": return <TerminalIcon className={className} />;
    case "browser": return <Globe className={className} />;
    case "desktop": return <Eye className={className} />;
    case "file": return <FileText className={className} />;
    case "gmail": return <Mail className={className} />;
    case "calendar": return <Calendar className={className} />;
    case "tasks": return <ListTodo className={className} />;
    case "skill": return <BookOpen className={className} />;
    case "subagent": return <Bot className={className} />;
    case "worker": return <Layers className={className} />;
    case "workflow": return <LayoutGrid className={className} />;
    case "mcp": return <Plug className={className} />;
    default: return <Wrench className={className} />;
  }
}

export function getAgentIcon(name: string, className: string) {
  const lower = name.toLowerCase();
  if (lower.includes("planner")) return <Sparkles className={className} />;
  if (lower.includes("worker") || lower.includes("terminal") || lower.includes("desktop")) {
    return <Layers className={className} />;
  }
  return <Bot className={className} />;
}

export function formatAgentName(name: string): string {
  const cleaned = name.replace(/^nexus_/i, "").replace(/_/g, " ");
  return (
    cleaned
      .split(" ")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ") || name
  );
}

/* ------------------------------------------------------------------ */
/*  Status node                                                        */
/* ------------------------------------------------------------------ */

const NODE_TONE: Record<ActivityStatus, string> = {
  pending: "text-foreground-icon-quaternary",
  running: "text-text-secondary",
  ok: "text-emerald-500",
  failed: "text-red-500",
  retry: "text-amber-500",
};

/**
 * The glyph that sits on the rail. Opaque background so the connector line
 * runs behind rows rather than through the glyph.
 */
export function ActivityNode({ status }: { status: ActivityStatus }) {
  return (
    <span
      className={cx(
        "relative z-10 flex shrink-0 items-center justify-center bg-background-full",
        NODE_TONE[status],
      )}
      style={{ width: NODE_SIZE, height: NODE_SIZE }}
      aria-hidden
    >
      {status === "running" ? <Loader2 className="size-3.5 animate-spin agent-loading-shine" /> : null}
      {status === "ok" ? <Check className="size-3.5" strokeWidth={2.4} /> : null}
      {status === "failed" ? <X className="size-3.5" strokeWidth={2.4} /> : null}
      {status === "retry" ? <RotateCw className="size-3.5" /> : null}
      {status === "pending" ? (
        <Circle className="size-2 fill-current" strokeWidth={0} />
      ) : null}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/*  Chips                                                              */
/* ------------------------------------------------------------------ */

const CHIP_TONE = {
  neutral: "border-separator-border text-text-tertiary",
  danger: "border-red-500/30 text-red-500 dark:text-red-400",
  warning: "border-amber-500/30 text-amber-600 dark:text-amber-400",
} as const;

export function ActivityChip({
  children,
  tone = "neutral",
  mono = false,
  title,
}: {
  children: ReactNode;
  tone?: keyof typeof CHIP_TONE;
  mono?: boolean;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cx(
        "shrink-0 rounded-md border px-1.5 py-px text-caption-2-medium whitespace-nowrap",
        mono && "font-mono uppercase",
        CHIP_TONE[tone],
      )}
    >
      {children}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/*  Rail                                                               */
/* ------------------------------------------------------------------ */

/** Vertical connector behind a run of {@link ActivityRow}s. */
export function ActivityRail({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("relative flex flex-col gap-0.5", className)}>
      <span
        className="absolute top-3 bottom-3 w-px bg-separator-border"
        style={{ left: RAIL_X }}
        aria-hidden
      />
      {children}
    </div>
  );
}

/** Indents free-form content (cards, nested rails) to the row text column. */
export function ActivityIndent({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("min-w-0", className)} style={{ paddingLeft: NODE_SIZE + 10 }}>
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Row                                                                */
/* ------------------------------------------------------------------ */

type ActivityRowProps = {
  status?: ActivityStatus;
  /** Provider glyph shown before the label. */
  icon?: ReactNode;
  label: ReactNode;
  /** The target of the action — path, query, command. Truncates. */
  detail?: ReactNode;
  detailMono?: boolean;
  durationMs?: number;
  /** Repeat count for grouped or deduped rows. */
  count?: number;
  chips?: ReactNode;
  tone?: "default" | "danger";
  /** Renders a chevron and makes the row a button. */
  expandable?: boolean;
  expanded?: boolean;
  onToggle?: () => void;
  /** Body revealed under the row, already indented to the text column. */
  children?: ReactNode;
};

export function ActivityRow({
  status = "ok",
  icon,
  label,
  detail,
  detailMono = false,
  durationMs,
  count,
  chips,
  tone = "default",
  expandable = false,
  expanded = false,
  onToggle,
  children,
}: ActivityRowProps) {
  const duration =
    typeof durationMs === "number" && durationMs > 0 ? formatDuration(durationMs) : "";
  const danger = tone === "danger";
  const showChildren = Boolean(children) && (!expandable || expanded);

  const body = (
    <>
      <ActivityNode status={status} />
      {icon ? (
        <span
          className={cx(
            "shrink-0",
            danger ? "text-red-500/80 dark:text-red-400/80" : "text-foreground-icon-tertiary",
          )}
        >
          {icon}
        </span>
      ) : null}
      <span
        className={cx(
          "shrink-0 text-body-2-medium select-none",
          danger
            ? "text-red-500 dark:text-red-400"
            : status === "running"
              ? "agent-progress-loading-text"
              : "text-text-secondary group-hover/row:text-text-primary transition-colors",
        )}
      >
        {label}
      </span>
      {detail ? (
        <span
          className={cx(
            "min-w-0 flex-1 truncate text-body-2-regular",
            detailMono && "font-mono",
            danger ? "text-red-500/90 dark:text-red-400/90" : "text-text-primary",
          )}
        >
          {detail}
        </span>
      ) : (
        <span className="min-w-0 flex-1" />
      )}
      {count && count > 1 ? (
        <ActivityChip tone={danger ? "danger" : "neutral"}>×{count}</ActivityChip>
      ) : null}
      {chips}
      {duration ? (
        <span className="shrink-0 font-mono text-caption-2-regular text-text-tertiary tabular-nums">
          {duration}
        </span>
      ) : null}
      {expandable ? (
        <Chevron className="shrink-0 text-foreground-icon-tertiary" open={expanded} />
      ) : null}
    </>
  );

  return (
    <div className="flex min-w-0 flex-col">
      {expandable ? (
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          className="group/row flex min-w-0 items-center gap-2.5 py-0.5 text-left"
        >
          {body}
        </button>
      ) : (
        <div className="group/row flex min-w-0 items-center gap-2.5 py-0.5">{body}</div>
      )}
      {showChildren ? <ActivityIndent className="pb-1">{children}</ActivityIndent> : null}
    </div>
  );
}

/** Multi-line row for content that can't truncate (errors, analyses). */
export function ActivityBlockRow({
  status = "ok",
  icon,
  label,
  tone = "default",
  chips,
  children,
}: {
  status?: ActivityStatus;
  icon?: ReactNode;
  label: ReactNode;
  tone?: "default" | "danger";
  chips?: ReactNode;
  children?: ReactNode;
}) {
  const danger = tone === "danger";
  return (
    <div className="flex min-w-0 flex-col">
      <div className="flex min-w-0 items-start gap-2.5 py-0.5">
        <ActivityNode status={status} />
        {icon ? (
          <span
            className={cx(
              "mt-[3px] shrink-0",
              danger ? "text-red-500/80 dark:text-red-400/80" : "text-foreground-icon-tertiary",
            )}
          >
            {icon}
          </span>
        ) : null}
        <span
          className={cx(
            "min-w-0 flex-1 text-body-2-regular",
            danger ? "text-red-500 dark:text-red-400" : "text-text-secondary",
          )}
        >
          {label}
        </span>
        {chips}
      </div>
      {children ? <ActivityIndent className="pb-1">{children}</ActivityIndent> : null}
    </div>
  );
}

export function Chevron({
  open,
  className,
}: {
  open: boolean;
  className?: string;
}) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cx("transition-transform duration-200", open && "rotate-180", className)}
      aria-hidden
    >
      <path d="m4.5 15.75 7.5-7.5 7.5 7.5" />
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/*  Summary chips (collapsed accordion header)                         */
/* ------------------------------------------------------------------ */

export type SummaryChip = {
  key: string;
  icon: ReactNode;
  count: number;
  label: string;
  tone?: "neutral" | "danger";
};

export function ActivitySummaryChips({ chips }: { chips: SummaryChip[] }) {
  if (chips.length === 0) return null;
  return (
    <span className="flex shrink-0 items-center gap-2.5">
      {chips.map((chip) => (
        <span
          key={chip.key}
          title={chip.label}
          className={cx(
            "flex items-center gap-1 text-caption-1-medium tabular-nums",
            chip.tone === "danger"
              ? "text-red-500 dark:text-red-400"
              : "text-text-tertiary",
          )}
        >
          {chip.icon}
          {chip.count}
        </span>
      ))}
    </span>
  );
}
