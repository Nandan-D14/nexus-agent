/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { APP_DASHBOARD } from "@/lib/app-paths";

export default function SettingsPage() {
  const router = useRouter();

  useEffect(() => {
    // Redirect to dashboard and the AppShell will handle opening settings if needed,
    // though the link interception is the primary way.
    router.replace(APP_DASHBOARD);
  }, [router]);

  return null;
}
