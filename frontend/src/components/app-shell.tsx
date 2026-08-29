/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import Image from "next/image";
import { usePathname } from "next/navigation";
import { SettingsModal } from "@/components/application/settings/settings-modal";
import { isSessionWorkspacePath } from "@/lib/app-paths";
import { useSettings } from "@/lib/settings-context";
import { useLandingChrome } from "@/lib/landing-chrome-context";
import { cx } from "@/utils/cx";
import { SessionNavSidebar } from "./session-nav-sidebar";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { isSettingsOpen, setIsSettingsOpen, settingsDefaultPage } = useSettings();
  const { isLandingChrome } = useLandingChrome();
  const pathname = usePathname();
  const isSessionPage = isSessionWorkspacePath(pathname);

  return (
    <div
      className={cx(
        "relative flex h-screen min-h-screen overflow-hidden text-foreground supports-[height:100dvh]:h-[100dvh]",
        isLandingChrome ? "bg-transparent" : "bg-white dark:bg-[#0d0d0d]",
      )}
    >
      {isLandingChrome ? (
        <Image
          src="/session-new-bg.png"
          alt=""
          fill
          priority
          quality={100}
          sizes="100vw"
          className="pointer-events-none select-none object-cover object-center"
        />
      ) : null}

      <div className="relative z-10 flex h-full min-w-0 flex-1">
        <SessionNavSidebar />

        <div className="relative flex h-full min-w-0 flex-1 flex-col overflow-hidden">
          <main
            className={cx(
              "flex-1 min-h-0 pt-16 transition-all duration-300 md:pt-0",
              !isSessionPage ? "overflow-y-auto custom-scrollbar" : "flex min-h-0 flex-col",
            )}
          >
            {children}
          </main>
        </div>
      </div>

      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        defaultPage={settingsDefaultPage}
      />
    </div>
  );
}
