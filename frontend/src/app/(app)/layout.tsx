"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { AppShell } from "@/components/app-shell";
import { fetchUserSettings, requiresByokSetup } from "@/lib/user-settings";

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [isCheckingByok, setIsCheckingByok] = useState(true);

  useEffect(() => {
    if (!isLoading && !user) {
      router.push("/");
    }
  }, [user, isLoading, router]);

  useEffect(() => {
    let cancelled = false;

    async function enforceByokGate() {
      if (isLoading) {
        return;
      }

      if (!user) {
        setIsCheckingByok(false);
        return;
      }

      if (pathname.startsWith("/settings/api")) {
        setIsCheckingByok(false);
        return;
      }

      try {
        const userSettings = await fetchUserSettings();
        if (cancelled) {
          return;
        }

        if (requiresByokSetup(userSettings)) {
          router.replace("/settings/api?setup=1");
          return;
        }
      } catch {
        if (cancelled) {
          return;
        }
      }

      if (!cancelled) {
        setIsCheckingByok(false);
      }
    }

    void enforceByokGate();

    return () => {
      cancelled = true;
    };
  }, [isLoading, pathname, router, user]);

  if (isLoading || (user && !pathname.startsWith("/settings/api") && isCheckingByok)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background text-foreground">
        <div className="w-8 h-8 border-4 border-cyan-600 dark:border-cyan-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!user) {
    return null; // Will redirect in useEffect
  }

  return <AppShell>{children}</AppShell>;
}
