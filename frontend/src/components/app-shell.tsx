/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { usePathname } from "next/navigation";
import { AnimatePresence } from "framer-motion";
import { SettingsModal } from "./settings-modal";
import { useSettings } from "@/lib/settings-context";
import { SessionNavSidebar } from "./session-nav-sidebar";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { isSettingsOpen, setIsSettingsOpen } = useSettings();
  const pathname = usePathname();
  const isSessionPage = pathname.includes("/session/");

  return (
    <div className="flex h-screen bg-background overflow-hidden text-foreground">
      {/* Unified Sidebar */}
      <SessionNavSidebar />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 relative h-full overflow-hidden">
        <main 
          className={`flex-1 pt-16 transition-all duration-300 md:pt-0 ${
            !isSessionPage ? "overflow-y-auto" : "flex flex-col min-h-0"
          }`}
        >
          {children}
        </main>
      </div>

      <AnimatePresence>
        {isSettingsOpen && (
          <SettingsModal isOpen={true} onClose={() => setIsSettingsOpen(false)} />
        )}
      </AnimatePresence>
    </div>
  );
}
