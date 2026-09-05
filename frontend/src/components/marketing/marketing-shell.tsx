/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import type { ReactNode } from "react";
import { useAuth } from "@/lib/auth-context";
import { useSignInGate } from "@/components/auth/sign-in-gate";
import { APP_HOME } from "@/lib/app-paths";
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
  const { user } = useAuth();
  const { requestSignIn } = useSignInGate();

  return (
    <div className="min-h-screen bg-background text-foreground selection:bg-blue-500/30 overflow-x-hidden font-sans">
      <SiteNav
        variant="marketing"
        user={user}
        onSignIn={() => {
          requestSignIn({ redirectTo: APP_HOME });
        }}
      />
      {children}
      <SiteFooter showStatus={showStatus} />
    </div>
  );
}
