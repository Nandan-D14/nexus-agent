/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { SettingsPage } from "@/components/application/settings/settings-modal";
import { fetchBetaStatus, type BetaStatusResponse } from "./beta-access";
import { useAuth } from "./auth-context";

type SettingsContextType = {
  isSettingsOpen: boolean;
  setIsSettingsOpen: (open: boolean) => void;
  settingsDefaultPage: SettingsPage;
  openSettings: (page?: SettingsPage) => void;
  requiresByokSetup: boolean;
  refreshBetaStatus: () => Promise<void>;
  isLoadingBetaStatus: boolean;
};

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const { user, isLoading: isAuthLoading } = useAuth();
  const [isSettingsOpen, setIsSettingsOpenState] = useState(false);
  const [settingsDefaultPage, setSettingsDefaultPage] = useState<SettingsPage>("general");
  const [betaStatus, setBetaStatus] = useState<BetaStatusResponse | null>(null);
  const [isLoadingBetaStatus, setIsLoadingBetaStatus] = useState(false);

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

  const refreshBetaStatus = async () => {
    if (!user) return;
    setIsLoadingBetaStatus(true);
    try {
      const status = await fetchBetaStatus();
      setBetaStatus(status);
    } catch (error) {
      console.error("Failed to fetch beta status:", error);
    } finally {
      setIsLoadingBetaStatus(false);
    }
  };

  useEffect(() => {
    if (user && !isAuthLoading) {
      refreshBetaStatus();
    } else {
      setBetaStatus(null);
    }
  }, [user, isAuthLoading]);

  const value = {
    isSettingsOpen,
    setIsSettingsOpen,
    settingsDefaultPage,
    openSettings,
    requiresByokSetup: betaStatus?.requires_byok_setup ?? false,
    refreshBetaStatus,
    isLoadingBetaStatus,
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
