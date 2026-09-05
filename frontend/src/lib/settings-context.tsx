/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { SettingsPage } from "@/components/application/settings/settings-modal";
import { useToast } from "@/components/toast-provider";
import { isQuotaExceededError } from "./api-client";
import { useAuth } from "./auth-context";
import {
  fetchUserSettings,
  formatByokMissingMessage,
  requiresByokSetup as settingsNeedByok,
  type UserSettingsResponse,
} from "./user-settings";

type SettingsContextType = {
  isSettingsOpen: boolean;
  setIsSettingsOpen: (open: boolean) => void;
  settingsDefaultPage: SettingsPage;
  openSettings: (page?: SettingsPage) => void;
  requiresByokSetup: boolean;
  byokMissing: string[];
  refreshByokStatus: () => Promise<UserSettingsResponse | null>;
  applyByokFromSettings: (data: UserSettingsResponse) => void;
  ensureByokReady: () => Promise<{ ok: boolean; message: string }>;
};

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const { user, isLoading: isAuthLoading } = useAuth();
  const { toast } = useToast();
  const [isSettingsOpen, setIsSettingsOpenState] = useState(false);
  const [settingsDefaultPage, setSettingsDefaultPage] = useState<SettingsPage>("general");
  const [byokState, setByokState] = useState<{
    blocked: boolean;
    missing: string[];
  } | null>(null);

  const setIsSettingsOpen = useCallback((open: boolean) => {
    if (open) {
      setSettingsDefaultPage("general");
    }
    setIsSettingsOpenState(open);
  }, []);

  const openSettings = useCallback((page: SettingsPage = "general") => {
    setSettingsDefaultPage(page);
    setIsSettingsOpenState(true);
  }, []);

  const applyByokFromSettings = useCallback((data: UserSettingsResponse) => {
    setByokState({
      blocked: settingsNeedByok(data),
      missing: data.byok.missing ?? [],
    });
  }, []);

  const refreshByokStatus = useCallback(async (): Promise<UserSettingsResponse | null> => {
    if (!user) return null;
    try {
      const data = await fetchUserSettings();
      applyByokFromSettings(data);
      return data;
    } catch (error) {
      if (isQuotaExceededError(error)) {
        toast(
          error instanceof Error ? error.message : "Firestore quota exceeded. Try again shortly.",
          "warning",
          { id: "firestore-quota" },
        );
      }
      return null;
    }
  }, [applyByokFromSettings, toast, user]);

  const requiresByokSetup = Boolean(byokState?.blocked);
  const byokMissing = byokState?.missing ?? [];

  const ensureByokReady = useCallback(async (): Promise<{ ok: boolean; message: string }> => {
    try {
      const data = await fetchUserSettings();
      applyByokFromSettings(data);
      if (!settingsNeedByok(data)) {
        return { ok: true, message: "" };
      }
      openSettings("api");
      return { ok: false, message: formatByokMissingMessage(data.byok.missing) };
    } catch (error) {
      if (isQuotaExceededError(error)) {
        toast(
          error instanceof Error ? error.message : "Firestore quota exceeded. Try again shortly.",
          "warning",
          { id: "firestore-quota" },
        );
        return { ok: false, message: "Firestore quota exceeded. Try again shortly." };
      }
      return { ok: true, message: "" };
    }
  }, [applyByokFromSettings, openSettings, toast]);

  useEffect(() => {
    if (user && !isAuthLoading) {
      void refreshByokStatus();
    } else {
      setByokState(null);
    }
  }, [user, isAuthLoading, refreshByokStatus]);

  const value = {
    isSettingsOpen,
    setIsSettingsOpen,
    settingsDefaultPage,
    openSettings,
    requiresByokSetup,
    byokMissing,
    refreshByokStatus,
    applyByokFromSettings,
    ensureByokReady,
  };

  return (
    <SettingsContext.Provider value={value}>
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings() {
  const context = useContext(SettingsContext);
  if (context === undefined) {
    throw new Error("useSettings must be used within a SettingsProvider");
  }
  return context;
}
