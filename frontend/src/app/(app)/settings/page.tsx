"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function SettingsPage() {
  const router = useRouter();

  useEffect(() => {
    // Redirect to dashboard and the AppShell will handle opening settings if needed,
    // though the link interception is the primary way.
    router.replace("/dashboard");
  }, [router]);

  return null;
}
