"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { AppShell } from "@/components/app-shell";
import { fetchBetaStatus } from "@/lib/beta-access";

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [isCheckingAccess, setIsCheckingAccess] = useState(true);

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
        setIsCheckingAccess(false);
        return;
      }

      try {
        const betaStatus = await fetchBetaStatus();
        if (cancelled) {
          return;
        }

        if (!betaStatus.can_access_app) {
          router.replace("/beta");
          return;
        }

        if (pathname.startsWith("/settings/api")) {
          setIsCheckingAccess(false);
          return;
        }

        if (betaStatus.requires_byok_setup) {
          router.replace("/settings/api?setup=1");
          return;
        }
      } catch {
        if (cancelled) {
          return;
        }
      }

      if (!cancelled) {
        setIsCheckingAccess(false);
      }
    }

    void enforceByokGate();

    return () => {
      cancelled = true;
    };
  }, [isLoading, pathname, router, user]);

  if (isLoading || (user && isCheckingAccess)) {
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
