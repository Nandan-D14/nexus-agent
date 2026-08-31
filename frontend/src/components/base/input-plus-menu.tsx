/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

/**
 * InputPlusMenu — a self-contained dropdown menu surface that mirrors the
 * ChatComposer's ComposerPlusMenu UI.  It can be attached to any textarea
 * or input field to expose skills, plugins, and upload/voice capabilities.
 *
 * Unlike ComposerPlusMenu, this component:
 *  - Fetches its own data (skills + connectors) via React Query hooks.
 *  - Doesn't require external state management for connector/tool selection.
 *  - Inserts text references (skill ids, tool ids) into a target textarea
 *    or input via an `onInsertText` callback instead of DOM manipulation.
 *
 * Usage:
 *   <div className="relative">
 *     <textarea ... />
 *     <InputPlusMenu onInsertText={(text) => setInstructions(prev => prev + text)} />
 *   </div>
 */

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import Link from "next/link";
import {
  AtSign,
  AudioLines,
  Blend,
  ChevronRight,
  FolderDown,
  Plus,
  Settings2,
  Upload,
  Zap,
} from "lucide-react";
import { ToolPickerPanel } from "@/components/session/tool-picker";
import type { SessionConnector } from "@/lib/session-utils";
import { useSkillsQuery, type AgentSkill } from "@/lib/queries/skills";
import { useIntegrationsConnectionsQuery } from "@/lib/queries/integrations";
import { SYSTEM_CONNECTOR } from "@/lib/session-utils";
import { APP_SKILLS, settingsPath } from "@/lib/app-paths";
import { cx } from "@/utils/cx";

/* ── Surface & item classes (same tokens as ComposerPlusMenu) ────────── */

export const INPUT_MENU_SURFACE =
  "border border-border-button-default bg-background-primary-default shadow-dropdown rounded-2xl";

const menuItemClass = cx(
  "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] transition-colors",
  "text-text-primary",
  "hover:bg-dropdown-item-hover-background",
  "disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent",
);

/* ── Feature flags ────────────────────────────────────────────────────── */

type FeatureFlags = {
  showUpload?: boolean;
  showSkills?: boolean;
  showPlugins?: boolean;
  showVoice?: boolean;
};

/* ── Props ────────────────────────────────────────────────────────────── */

type FlyoutId = "plugins" | "skills" | "voice";

type InputPlusMenuProps = FeatureFlags & {
  /** Called when a user selects a skill or tool — inserts text at cursor. */
  onInsertText?: (text: string) => void;
  /** Optional file-picker callback; hides Upload if omitted. */
  onOpenFilePicker?: (kind?: "image" | "file") => void;
  /** Optional mic toggle; hides Voice if omitted. */
  onToggleMic?: () => void;
  isRecording?: boolean;
  voiceStatus?: string;
  /** Override trigger rendering; defaults to a "+" icon button. */
  trigger?: (props: { open: boolean; onClick: () => void }) => ReactNode;
  /** Classname for the root wrapper. */
  className?: string;
};

/* ── Component ────────────────────────────────────────────────────────── */

export function InputPlusMenu({
  showUpload = true,
  showSkills = true,
  showPlugins = true,
  showVoice = false,
  onInsertText,
  onOpenFilePicker,
  onToggleMic,
  isRecording = false,
  voiceStatus = "",
  trigger,
  className,
}: InputPlusMenuProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<number | null>(null);

  const [open, setOpen] = useState(false);
  const [flyout, setFlyout] = useState<FlyoutId | null>(null);
  const [placement, setPlacement] = useState<"top" | "bottom">("top");
  const [flyoutSide, setFlyoutSide] = useState<"right" | "left">("right");

  // Selected connector/tool ids for the tool picker (local state)
  const [selectedConnectorIds, setSelectedConnectorIds] = useState<string[]>([]);
  const [selectedToolIds, setSelectedToolIds] = useState<string[]>([]);

  // Fetch skills & connectors
  const { data: skillList } = useSkillsQuery();
  const skills = (skillList ?? []).filter((s) => s.enabled);
  const connectionsQuery = useIntegrationsConnectionsQuery();
  const availableConnectors: SessionConnector[] = [
    SYSTEM_CONNECTOR,
    ...(connectionsQuery.data ?? [])
      .filter((c) => c.enabled && c.status === "connected")
      .map((c) => ({
        connection_id: c.connection_id,
        connector_type: c.connector_type,
        provider: c.provider,
        name: c.name,
        enabled: c.enabled,
        status: c.status,
      })),
  ];

  /* ── Timer helpers ─────────────────────────────────────────────────── */

  const clearCloseTimer = () => {
    if (closeTimer.current != null) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  };

  const openFlyout = (id: FlyoutId) => {
    clearCloseTimer();
    setFlyout(id);
  };

  const scheduleCloseFlyout = () => {
    clearCloseTimer();
    closeTimer.current = window.setTimeout(() => setFlyout(null), 180);
  };

  /* ── Outside click / Escape ────────────────────────────────────────── */

  useEffect(() => {
    if (!open) {
      setFlyout(null);
      return;
    }
    const onDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (flyout) {
        setFlyout(null);
        return;
      }
      setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, flyout]);

  useEffect(() => () => clearCloseTimer(), []);

  /* ── Placement / flyout side ───────────────────────────────────────── */

  useLayoutEffect(() => {
    if (!open) return;
    const VIEWPORT_MARGIN = 16;
    const TRIGGER_GAP = 8;
    const update = () => {
      const trigger = rootRef.current;
      if (!trigger) return;
      const rect = trigger.getBoundingClientRect();
      const spaceAbove = rect.top - VIEWPORT_MARGIN - TRIGGER_GAP;
      const spaceBelow = window.innerHeight - rect.bottom - VIEWPORT_MARGIN - TRIGGER_GAP;
      setPlacement(spaceAbove >= 240 || spaceAbove >= spaceBelow ? "top" : "bottom");
      const primaryWidth = 252;
      const flyoutWidth = 280;
      const spaceRight = window.innerWidth - (rect.left + primaryWidth) - VIEWPORT_MARGIN;
      setFlyoutSide(spaceRight >= flyoutWidth ? "right" : "left");
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [open]);

  /* ── Callbacks ─────────────────────────────────────────────────────── */

  const handleAddSkill = useCallback(
    (skill: AgentSkill) => {
      onInsertText?.(`/${skill.skill_id} `);
      setOpen(false);
    },
    [onInsertText],
  );

  const toggleConnector = useCallback((id: string) => {
    setSelectedConnectorIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }, []);

  const toggleTool = useCallback((id: string) => {
    setSelectedToolIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }, []);

  const voiceReady = voiceStatus === "connected";

  /* ── Render ─────────────────────────────────────────────────────────── */

  const selectionCount = selectedToolIds.length + selectedConnectorIds.length;

  return (
    <div className={cx("relative", className)} ref={rootRef}>
      {/* Trigger */}
      {trigger ? (
        trigger({ open, onClick: () => setOpen((o) => !o) })
      ) : (
        <button
          type="button"
          className={cx(
            "relative flex h-8 w-8 items-center justify-center rounded-full transition-colors",
            "text-text-secondary hover:bg-background-secondary-hover hover:text-text-primary",
            open && "bg-background-secondary-hover text-text-primary",
          )}
          aria-label="Add skill or plugin"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
        >
          <Plus className="h-4 w-4" />
          {selectionCount > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-foreground text-[10px] font-bold text-background">
              {selectionCount}
            </span>
          )}
        </button>
      )}

      {/* Menu panel */}
      {open && (
        <div
          className={cx(
            INPUT_MENU_SURFACE,
            "absolute left-0 z-50 flex w-[252px] flex-col p-1.5",
            placement === "top"
              ? "bottom-full mb-2 origin-bottom-left"
              : "top-full mt-2 origin-top-left",
            "animate-in fade-in-0 zoom-in-95 duration-150",
          )}
        >
          {/* Upload */}
          {showUpload && onOpenFilePicker && (
            <button
              type="button"
              className={menuItemClass}
              onClick={() => {
                onOpenFilePicker("file");
                setOpen(false);
              }}
            >
              <Upload className="h-4 w-4 shrink-0 text-text-tertiary" />
              <span className="flex-1 text-left">Upload files or images</span>
            </button>
          )}

          {/* Plugins flyout */}
          {showPlugins && (
            <FlyoutRow
              id="plugins"
              label="@ Plugins"
              icon={<AtSign className="h-4 w-4 shrink-0 text-text-tertiary" />}
              open={flyout === "plugins"}
              flyoutSide={flyoutSide}
              onOpen={openFlyout}
              onScheduleClose={scheduleCloseFlyout}
            >
              <div className="flex h-[320px] w-[280px] flex-col py-1">
                <ToolPickerPanel
                  availableConnectors={availableConnectors}
                  selectedConnectorIds={selectedConnectorIds}
                  onToggleConnector={toggleConnector}
                  selectedToolIds={selectedToolIds}
                  onToggleTool={toggleTool}
                  loading={connectionsQuery.isPending}
                />
              </div>
            </FlyoutRow>
          )}

          {/* Skills flyout */}
          {showSkills && (
            <FlyoutRow
              id="skills"
              label="Use Agent Skills"
              icon={<Zap className="h-4 w-4 shrink-0 text-text-tertiary" />}
              open={flyout === "skills"}
              flyoutSide={flyoutSide}
              onOpen={openFlyout}
              onScheduleClose={scheduleCloseFlyout}
            >
              <SkillsFlyout skills={skills} onAddSkill={handleAddSkill} />
            </FlyoutRow>
          )}

          {/* Voice flyout */}
          {showVoice && onToggleMic && (
            <FlyoutRow
              id="voice"
              label="Add Voice"
              icon={<AudioLines className="h-4 w-4 shrink-0 text-text-tertiary" />}
              open={flyout === "voice"}
              flyoutSide={flyoutSide}
              onOpen={openFlyout}
              onScheduleClose={scheduleCloseFlyout}
            >
              <div className="flex w-[240px] flex-col p-1">
                <button
                  type="button"
                  className={menuItemClass}
                  disabled={!voiceReady}
                  onClick={() => {
                    if (!voiceReady) return;
                    onToggleMic();
                  }}
                >
                  <span className="flex-1 text-left">
                    {isRecording ? "Stop voice input" : "Voice input"}
                  </span>
                </button>
                <Link
                  href={settingsPath("voice")}
                  className={menuItemClass}
                  onClick={() => setOpen(false)}
                >
                  <Settings2 className="h-4 w-4 shrink-0 text-text-tertiary" />
                  <span className="flex-1 text-left">Voice settings</span>
                </Link>
              </div>
            </FlyoutRow>
          )}

          <div className="my-1 h-px bg-separator-border" />

          <button type="button" className={menuItemClass} disabled title="Coming soon">
            <Blend className="h-4 w-4 shrink-0 text-text-tertiary" />
            <span className="flex-1 text-left">Add Design System</span>
            <span className="text-[11px] text-text-tertiary">Coming soon</span>
          </button>
          <button type="button" className={menuItemClass} disabled title="Coming soon">
            <FolderDown className="h-4 w-4 shrink-0 text-text-tertiary" />
            <span className="flex-1 text-left">Import existing project</span>
            <span className="text-[11px] text-text-tertiary">Coming soon</span>
          </button>
        </div>
      )}
    </div>
  );
}

/* ── FlyoutRow ───────────────────────────────────────────────────────── */

function FlyoutRow({
  id,
  label,
  icon,
  open,
  flyoutSide,
  onOpen,
  onScheduleClose,
  children,
}: {
  id: FlyoutId;
  label: string;
  icon: ReactNode;
  open: boolean;
  flyoutSide: "right" | "left";
  onOpen: (id: FlyoutId) => void;
  onScheduleClose: () => void;
  children: ReactNode;
}) {
  return (
    <div
      className="relative"
      onMouseEnter={() => onOpen(id)}
      onMouseLeave={onScheduleClose}
    >
      <button
        type="button"
        className={cx(menuItemClass, open && "bg-dropdown-item-hover-background")}
        aria-expanded={open}
        onClick={() => onOpen(id)}
      >
        {icon}
        <span className="flex-1 text-left">{label}</span>
        <ChevronRight className="h-4 w-4 shrink-0 text-text-tertiary" />
      </button>
      {open && (
        <div
          className={cx(
            "absolute top-0 z-[60]",
            flyoutSide === "right" ? "left-full" : "right-full",
          )}
        >
          <div className={cx(flyoutSide === "right" ? "pl-1.5" : "pr-1.5")}>
            <div className={cx(INPUT_MENU_SURFACE, "overflow-hidden")}>{children}</div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── SkillsFlyout ────────────────────────────────────────────────────── */

function SkillsFlyout({
  skills,
  onAddSkill,
}: {
  skills: AgentSkill[];
  onAddSkill: (skill: AgentSkill) => void;
}) {
  return (
    <div className="flex max-h-[280px] w-[252px] flex-col">
      <div className="custom-scrollbar min-h-0 flex-1 space-y-0.5 overflow-y-auto p-1">
        {skills.length ? (
          skills.map((skill) => (
            <button
              key={skill.skill_id}
              type="button"
              className={menuItemClass}
              onClick={() => onAddSkill(skill)}
            >
              <span className="min-w-0 flex-1 truncate text-left font-medium">
                /{skill.skill_id}
              </span>
            </button>
          ))
        ) : (
          <p className="px-2.5 py-4 text-[13px] text-text-tertiary">No skills enabled</p>
        )}
      </div>
      <div className="border-t border-separator-border p-1">
        <Link href={APP_SKILLS} className={menuItemClass}>
          <Zap className="h-4 w-4 shrink-0 text-text-tertiary" />
          <span className="flex-1 text-left">Manage skills</span>
        </Link>
      </div>
    </div>
  );
}
