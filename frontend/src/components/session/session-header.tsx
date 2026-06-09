/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { Signal, Monitor, Settings, User, Maximize, Minimize, MonitorOff, Save } from "lucide-react";
import { Tooltip } from "@heroui/react";

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
    <header className="h-14 shrink-0 flex items-center justify-between px-6 border-b border-zinc-200 dark:border-zinc-800 bg-transparent shadow-sm z-10">
      <div className="flex items-center gap-4">
        <button className="flex items-center gap-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100 hover:opacity-80 transition-opacity">
          CoComputer
          <span className="text-[10px] uppercase font-bold text-zinc-500 dark:text-zinc-400 border border-zinc-300 dark:border-zinc-700 rounded-md px-1.5 py-0.5 bg-zinc-100 dark:bg-zinc-800/50">
            Beta
          </span>
        </button>

        {viewMode === "live" && isConnected && (
          <div className="flex items-center gap-2 text-emerald-400 text-[13px] font-medium">
            <Signal className="w-4 h-4" /> Connected
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 text-sm font-medium">
        {!isNewSession && (
          <Tooltip>
            <Tooltip.Trigger>
              <button
                suppressHydrationWarning
                onClick={
                  viewMode === "live"
                    ? onToggleDesktopFullscreen
                    : onShowDesktop
                }
                className="p-1.5 rounded-md text-zinc-500 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors"
              >
                {viewMode !== "live" || (!isDesktopFullscreen && !isDesktopVisible) ? (
                  <Monitor className="w-4 h-4" />
                ) : isDesktopFullscreen ? (
                  <Minimize className="w-4 h-4" />
                ) : (
                  <Maximize className="w-4 h-4" />
                )}
              </button>
            </Tooltip.Trigger>
            <Tooltip.Content className="px-2 py-1 text-xs font-medium rounded-md bg-zinc-900 text-zinc-100 dark:bg-zinc-800 dark:text-zinc-100 border border-zinc-800 dark:border-zinc-700 shadow-md">
              {viewMode !== "live"
                ? "Open Desktop"
                : isDesktopFullscreen
                ? "Exit Fullscreen"
                : isDesktopVisible
                ? "Fullscreen"
                : "Open Desktop"}
            </Tooltip.Content>
          </Tooltip>
        )}

        {viewMode === "live" && isDesktopVisible && !isDesktopFullscreen && (
          <Tooltip>
            <Tooltip.Trigger>
              <button
                suppressHydrationWarning
                onClick={onHideDesktop}
                className="p-1.5 rounded-md text-zinc-500 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors"
              >
                <MonitorOff className="w-4 h-4" />
              </button>
            </Tooltip.Trigger>
            <Tooltip.Content className="px-2 py-1 text-xs font-medium rounded-md bg-zinc-900 text-zinc-100 dark:bg-zinc-800 dark:text-zinc-100 border border-zinc-800 dark:border-zinc-700 shadow-md">
              Hide Desktop
            </Tooltip.Content>
          </Tooltip>
        )}

        {!isNewSession && (
          <Tooltip>
            <Tooltip.Trigger>
              <button
                suppressHydrationWarning
                onClick={onOpenSaveTemplate}
                className="p-1.5 rounded-md text-zinc-500 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors"
              >
                <Save className="w-4 h-4" />
              </button>
            </Tooltip.Trigger>
            <Tooltip.Content className="px-2 py-1 text-xs font-medium rounded-md bg-zinc-900 text-zinc-100 dark:bg-zinc-800 dark:text-zinc-100 border border-zinc-800 dark:border-zinc-700 shadow-md">
              Save Template
            </Tooltip.Content>
          </Tooltip>
        )}

        <Tooltip>
          <Tooltip.Trigger>
            <button
              className="p-1.5 rounded-md text-zinc-500 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors ml-1"
              onClick={onOpenSettings}
            >
              <Settings className="w-4 h-4" />
            </button>
          </Tooltip.Trigger>
          <Tooltip.Content className="px-2 py-1 text-xs font-medium rounded-md bg-zinc-900 text-zinc-100 dark:bg-zinc-800 dark:text-zinc-100 border border-zinc-800 dark:border-zinc-700 shadow-md">
            Settings
          </Tooltip.Content>
        </Tooltip>

        <Tooltip>
          <Tooltip.Trigger>
            <button className="p-1.5 rounded-md text-zinc-500 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors">
              <User className="w-4 h-4" />
            </button>
          </Tooltip.Trigger>
          <Tooltip.Content className="px-2 py-1 text-xs font-medium rounded-md bg-zinc-900 text-zinc-100 dark:bg-zinc-800 dark:text-zinc-100 border border-zinc-800 dark:border-zinc-700 shadow-md">
            User Profile
          </Tooltip.Content>
        </Tooltip>

        <button
          suppressHydrationWarning
          onClick={onEndSession}
          className="ml-2 px-4 py-1.5 rounded-md bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 font-semibold hover:bg-red-100 dark:hover:bg-red-500/20 transition-colors border border-red-200 dark:border-red-500/20"
        >
          {viewMode === "live" ? "End Session" : "Exit"}
        </button>
      </div>
    </header>
  );
}
