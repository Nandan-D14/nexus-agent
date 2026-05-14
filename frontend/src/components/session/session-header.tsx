/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { ChevronDown, Signal, Monitor, Settings, User } from "lucide-react";

type Props = {
  viewMode: string;
  isConnected: boolean;
  isNewSession: boolean;
  isDesktopVisible: boolean;
  isDesktopFullscreen: boolean;
  onToggleDesktopFullscreen: () => void;
  onShowDesktop: () => void;
  onHideDesktop: () => void;
  onOpenSaveTemplate: () => void;
  onOpenSettings: () => void;
  onEndSession: () => void;
};

export function SessionHeader({
  viewMode,
  isConnected,
  isNewSession,
  isDesktopVisible,
  isDesktopFullscreen,
  onToggleDesktopFullscreen,
  onShowDesktop,
  onHideDesktop,
  onOpenSaveTemplate,
  onOpenSettings,
  onEndSession,
}: Props) {
  return (
    <header className="h-14 shrink-0 flex items-center justify-between px-6 border-b border-transparent bg-transparent backdrop-blur-md z-10">
      <div className="flex items-center gap-4">
        <button className="flex items-center gap-2 text-[14px] font-medium text-zinc-200 hover:text-zinc-100 transition-colors">
          CoComputer{" "}
          <span className="text-[10px] uppercase font-bold text-zinc-400 border border-zinc-700/80 rounded px-1.5 py-0.5 bg-zinc-800/30">
            Beta
          </span>{" "}
          <ChevronDown className="w-4 h-4 text-zinc-500 ml-1" />
        </button>

        {viewMode === "live" && isConnected && (
          <div className="flex items-center gap-2 text-emerald-400 text-[13px] font-medium">
            <Signal className="w-4 h-4" /> Connected
          </div>
        )}
      </div>

      <div className="flex items-center gap-4 text-[13px] font-medium">
        {!isNewSession && (
          <button
            suppressHydrationWarning
            onClick={
              viewMode === "live"
                ? onToggleDesktopFullscreen
                : onShowDesktop
            }
            className="flex items-center gap-2 text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            <Monitor className="w-4 h-4" />
            {viewMode !== "live"
              ? "Open Desktop"
              : isDesktopFullscreen
              ? "Exit Fullscreen"
              : isDesktopVisible
              ? "Fullscreen"
              : "Open Desktop"}
          </button>
        )}

        {viewMode === "live" && isDesktopVisible && !isDesktopFullscreen && (
          <button
            suppressHydrationWarning
            onClick={onHideDesktop}
            className="text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            Hide
          </button>
        )}

        {!isNewSession && (
          <button
            suppressHydrationWarning
            onClick={onOpenSaveTemplate}
            className="text-zinc-400 hover:text-zinc-200 transition-colors ml-1"
          >
            Save Template
          </button>
        )}

        <button
          className="text-zinc-400 hover:text-zinc-300 ml-2"
          onClick={onOpenSettings}
        >
          <Settings className="w-4 h-4" />
        </button>
        <button className="text-zinc-400 hover:text-zinc-300">
          <User className="w-4 h-4" />
        </button>

        <button
          suppressHydrationWarning
          onClick={onEndSession}
          className="text-red-400 hover:text-red-300 transition-colors ml-2"
        >
          {viewMode === "live" ? "End" : "Exit"}
        </button>
      </div>
    </header>
  );
}
