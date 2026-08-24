/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import type { ReactNode } from "react";
import { useAuth } from "@/lib/auth-context";
import { SiteNav } from "@/components/marketing/site-nav";
import { SiteFooter } from "@/components/marketing/site-footer";

type MarketingShellProps = {
  children: ReactNode;
  showStatus?: boolean;
};

export function MarketingShell({
  children,
  showStatus = false,
}: MarketingShellProps) {
  const { user, signInWithGoogle } = useAuth();

  return (
    <div className="min-h-screen bg-background text-foreground selection:bg-blue-500/30 overflow-x-hidden font-sans">
      <SiteNav
        variant="marketing"
        user={user}
        onSignIn={() => {
          void signInWithGoogle().catch(() => {});
        }}
      />
      {children}
      <SiteFooter showStatus={showStatus} />
    </div>
  );
}
