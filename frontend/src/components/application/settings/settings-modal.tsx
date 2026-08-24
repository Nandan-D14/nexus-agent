"use client";

import { useEffect, useRef, useState, type ComponentType } from "react";
import { createPortal } from "react-dom";
import {
  RiBankCardLine,
  RiBookOpenLine,
  RiCheckboxCircleFill,
  RiCloseLine,
  RiDatabase2Line,
  RiKey2Line,
  RiMicLine,
  RiOrganizationChart,
  RiPaletteLine,
  RiSchoolLine,
  RiSettings6Line,
  RiToolsFill,
} from "@remixicon/react";
import { cx } from "@/utils/cx";
import { SettingsApi } from "./settings-api";
import { SettingsAppearance } from "./settings-appearance";
import { SettingsBilling } from "./settings-billing";
import { SettingsGeneral } from "./settings-general";
import { SettingsProfile } from "./settings-profile";
import { SettingsRules } from "./settings-rules";
import { SettingsSkills } from "./settings-skills";
import { SettingsStorage } from "./settings-storage";
import { SettingsTools } from "./settings-tools";
import { SettingsVoice } from "./settings-voice";

/**
 * App-wide settings modal. Rail and content pane are both opaque.
 */

export type SettingsPage =
  | "general"
  | "profile"
  | "api"
  | "voice"
  | "appearance"
  | "billing"
  | "rules"
  | "tools"
  | "storage"
  | "skills";

export interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  defaultPage?: SettingsPage;
  planArtSrc?: string;
}

type IconComponent = ComponentType<{
  className?: string;
  "aria-hidden"?: boolean | "true" | "false";
}>;

interface NavEntry {
  label: string;
  icon: IconComponent;
  page: SettingsPage;
}

const NAV_GROUPS: { label: string; items: NavEntry[] }[] = [
  {
    label: "Settings",
    items: [
      { label: "General", icon: RiSettings6Line, page: "general" },
      { label: "Profile", icon: RiSchoolLine, page: "profile" },
      { label: "API & Keys", icon: RiKey2Line, page: "api" },
      { label: "Voice", icon: RiMicLine, page: "voice" },
      { label: "Appearance", icon: RiPaletteLine, page: "appearance" },
      { label: "Billing", icon: RiBankCardLine, page: "billing" },
      { label: "Rules and Workflows", icon: RiOrganizationChart, page: "rules" },
      { label: "Tools", icon: RiToolsFill, page: "tools" },
      { label: "Storage", icon: RiDatabase2Line, page: "storage" },
      { label: "Skills", icon: RiBookOpenLine, page: "skills" },
    ],
  },
];

const PAGE_TITLES: Record<SettingsPage, string> = {
  general: "General",
  profile: "Profile",
  api: "API & Keys",
  voice: "Voice",
  appearance: "Appearance",
  billing: "Billing",
  rules: "Rules and Workflows",
  tools: "Tools",
  storage: "Storage",
  skills: "Skills",
};

export function SettingsModal({
  isOpen,
  onClose,
  defaultPage = "general",
  planArtSrc,
}: SettingsModalProps) {
  const [page, setPage] = useState<SettingsPage>(defaultPage);
  const [mounted, setMounted] = useState(false);
  const [visible, setVisible] = useState(false);
  const unmountTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [savedPhase, setSavedPhase] = useState<"hidden" | "shown" | "leaving">("hidden");
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showSavedToast = () => {
    if (savedTimer.current) clearTimeout(savedTimer.current);
    setSavedPhase("shown");
    savedTimer.current = setTimeout(() => {
      setSavedPhase("leaving");
      savedTimer.current = setTimeout(() => setSavedPhase("hidden"), 220);
    }, 2000);
  };
  const [contentScrolled, setContentScrolled] = useState(false);

  useEffect(() => {
    if (isOpen) {
      if (unmountTimer.current) clearTimeout(unmountTimer.current);
      setPage(defaultPage);
      setMounted(true);
      requestAnimationFrame(() => requestAnimationFrame(() => setVisible(true)));
    } else {
      setVisible(false);
      setSavedPhase("hidden");
      unmountTimer.current = setTimeout(() => setMounted(false), 320);
    }
    return () => {
      if (unmountTimer.current) clearTimeout(unmountTimer.current);
      if (savedTimer.current) clearTimeout(savedTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- defaultPage only matters at the open transition
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    panelRef.current?.focus();
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  if (!mounted || typeof document === "undefined") return null;

  return createPortal(
    <div className="fixed inset-0 z-100 flex items-center justify-center p-4" role="presentation">
      <button
        type="button"
        aria-label="Close settings"
        tabIndex={-1}
        onClick={onClose}
        className={cx(
          "absolute inset-0 cursor-default bg-black/10 transition-opacity duration-300 ease-out",
          visible ? "opacity-100" : "opacity-0",
        )}
      />

      <div
        className={cx(
          "relative",
          "transform-gpu transition-[opacity,transform,filter] duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] will-change-[opacity,transform,filter]",
          visible ? "scale-100 opacity-100 blur-0" : "scale-[0.85] opacity-0 blur-[4px]",
        )}
      >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Settings"
        tabIndex={-1}
        className={cx(
          "relative flex h-[614px] max-h-[calc(100dvh-32px)] w-[871px] max-w-[calc(100vw-32px)]",
          "overflow-clip rounded-3xl bg-background-full shadow-xs outline-none ring-1 ring-border-button-default",
        )}
      >
        <nav
          aria-label="Settings sections"
          className="flex w-[274px] shrink-0 flex-col gap-5 overflow-y-auto rounded-l-3xl border-r border-separator-border bg-background-secondary-default p-2.5"
        >
          {NAV_GROUPS.map((group) => (
            <div key={group.label} className="flex w-full flex-col gap-1.5 pt-1">
              <span className="pl-2 text-body-medium text-text-secondary">{group.label}</span>
              <div className="flex w-full flex-col gap-1">
                {group.items.map((item) => {
                  const selected = item.page === page;
                  return (
                    <button
                      key={`${group.label}:${item.label}`}
                      type="button"
                      aria-current={selected ? "page" : undefined}
                      onClick={() => {
                        setPage(item.page);
                        setContentScrolled(false);
                      }}
                      className={cx(
                        "flex w-full cursor-pointer items-center gap-2 rounded-2lg p-2 text-left",
                        "outline-none transition-colors duration-150 ease focus-visible:ring-2 focus-visible:ring-border-focus-ring",
                        selected
                          ? "bg-background-secondary-hover"
                          : "hover:bg-background-secondary-hover/60",
                      )}
                    >
                      <item.icon className="size-5 shrink-0 text-foreground-icon-secondary" aria-hidden />
                      <span
                        className={cx(
                          "truncate text-body-medium",
                          selected ? "text-text-primary" : "text-text-secondary",
                        )}
                      >
                        {item.label}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        <div className="flex min-w-0 flex-1 flex-col rounded-r-3xl bg-background-full">
          <div
            className={cx(
              "flex shrink-0 items-center justify-between px-8 pt-8",
              page === "storage" ? "pb-1.5" : "pb-3",
            )}
          >
            <h2 className="font-serif text-title-3-medium text-text-primary">{PAGE_TITLES[page]}</h2>
            <button
              type="button"
              aria-label="Close settings"
              onClick={onClose}
              className={cx(
                "flex size-6 shrink-0 cursor-pointer items-center justify-center rounded-full",
                "bg-background-tertiary-default text-foreground-icon-secondary",
                "transition-colors duration-150 ease hover:bg-background-tertiary-hover",
                "outline-none focus-visible:ring-2 focus-visible:ring-border-focus-ring",
              )}
            >
              <RiCloseLine className="size-4" aria-hidden />
            </button>
          </div>
          <div className="relative min-h-0 flex-1">
            <div
              className="h-full overflow-y-auto px-8 pb-8"
              onScroll={(e) => setContentScrolled(e.currentTarget.scrollTop > 0)}
            >
              {page === "profile" ? (
                <SettingsProfile onSaved={showSavedToast} />
              ) : page === "storage" ? (
                <SettingsStorage />
              ) : page === "tools" ? (
                <SettingsTools />
              ) : page === "api" ? (
                <SettingsApi onSaved={showSavedToast} />
              ) : page === "voice" ? (
                <SettingsVoice onSaved={showSavedToast} />
              ) : page === "appearance" ? (
                <SettingsAppearance />
              ) : page === "billing" ? (
                <SettingsBilling />
              ) : page === "rules" ? (
                <SettingsRules onSaved={showSavedToast} />
              ) : page === "skills" ? (
                <SettingsSkills />
              ) : (
                <SettingsGeneral
                  planArtSrc={planArtSrc}
                  onManageLimits={() => {
                    setPage("billing");
                    setContentScrolled(false);
                  }}
                  onSaved={showSavedToast}
                />
              )}
            </div>
            <div
              aria-hidden
              className={cx(
                "pointer-events-none absolute inset-x-0 top-0 h-10 bg-linear-to-b from-background-primary-default to-transparent",
                "transition-opacity duration-200 ease-out",
                contentScrolled ? "opacity-100" : "opacity-0",
              )}
            />
          </div>
        </div>
      </div>

      <div
        aria-live="polite"
        className={cx(
          "pointer-events-none absolute bottom-0 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1",
          "rounded-full border border-border-button-default bg-background-primary-default py-1 pr-2.5 pl-1.5 shadow-dropdown",
          "transition-[opacity,transform,filter] duration-200 ease-out",
          savedPhase === "shown" && "translate-y-1/2 opacity-100 scale-100 blur-0",
          savedPhase === "hidden" && "translate-y-[calc(50%+12px)] opacity-0 scale-90 blur-[2px]",
          savedPhase === "leaving" && "translate-y-[calc(50%-10px)] opacity-0 scale-90 blur-[2px]",
        )}
      >
        <RiCheckboxCircleFill className="size-4 shrink-0 text-lime-600" aria-hidden />
        <span className="text-body-2-medium whitespace-nowrap text-text-primary">Saved</span>
      </div>
      </div>
    </div>,
    document.body,
  );
}
