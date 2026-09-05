/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { APP_DASHBOARD, APP_SETTINGS } from "@/lib/app-paths";
import { useSettings } from "@/lib/settings-context";
import { stashPostSignInRedirect } from "@/components/auth/sign-in-gate";
import { AppShell } from "@/components/app-shell";
import { AppShellSkeleton } from "@/components/app-shell-skeleton";

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, isLoading } = useAuth();
  const { setIsSettingsOpen } = useSettings();
  const router = useRouter();
  const pathname = usePathname();
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    if (!isLoading && !user) {
      // Remember the deep link so sign-in returns here instead of the app root.
      stashPostSignInRedirect(pathname);
      router.push("/");
    }
  }, [user, isLoading, pathname, router]);

  useEffect(() => {
    if (isLoading) {
      return;
    }
    if (!user) {
      setIsReady(true);
      return;
    }
    if (pathname.startsWith(APP_SETTINGS)) {
      router.replace(APP_DASHBOARD);
      setIsSettingsOpen(true);
    }
    setIsReady(true);
  }, [isLoading, pathname, router, user, setIsSettingsOpen]);

  if (isLoading || (user && !isReady)) {
    return <AppShellSkeleton />;
  }

  if (!user) {
    return null;
  }

  return <AppShell>{children}</AppShell>;
}
