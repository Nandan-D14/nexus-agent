"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { fetchBetaStatus, type BetaStatusResponse } from "./beta-access";
import { useAuth } from "./auth-context";

type SettingsContextType = {
  isSettingsOpen: boolean;
  setIsSettingsOpen: (open: boolean) => void;
  requiresByokSetup: boolean;
  refreshBetaStatus: () => Promise<void>;
  isLoadingBetaStatus: boolean;
};

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const { user, isLoading: isAuthLoading } = useAuth();
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [betaStatus, setBetaStatus] = useState<BetaStatusResponse | null>(null);
  const [isLoadingBetaStatus, setIsLoadingBetaStatus] = useState(false);

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
