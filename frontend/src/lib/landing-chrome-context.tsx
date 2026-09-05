/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";

type LandingChromeContextValue = {
  isLandingChrome: boolean;
  setLandingChrome: (active: boolean) => void;
};

const LandingChromeContext = createContext<LandingChromeContextValue | null>(null);

export function LandingChromeProvider({ children }: { children: React.ReactNode }) {
  const [isLandingChrome, setIsLandingChrome] = useState(false);
  const setLandingChrome = useCallback((active: boolean) => {
    setIsLandingChrome(active);
  }, []);
  const value = useMemo(
    () => ({ isLandingChrome, setLandingChrome }),
    [isLandingChrome, setLandingChrome],
  );

  return (
    <LandingChromeContext.Provider value={value}>
      {children}
    </LandingChromeContext.Provider>
  );
}

export function useLandingChrome() {
  const context = useContext(LandingChromeContext);
  if (!context) {
    throw new Error("useLandingChrome must be used within a LandingChromeProvider");
  }
  return context;
}
