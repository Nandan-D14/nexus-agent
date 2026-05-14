/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useAuth } from "@/lib/auth-context";
import { useRouter, usePathname } from "next/navigation";
import { AnimatePresence } from "framer-motion";
import { SearchModal } from "./search-modal";
import { SettingsModal } from "./settings-modal";
import { useSettings } from "@/lib/settings-context";
import { SessionNavSidebar } from "./session-nav-sidebar";
import { useState } from "react";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const { isSettingsOpen, setIsSettingsOpen } = useSettings();
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const pathname = usePathname();

  const isMobileViewport = () => typeof window !== "undefined" && window.innerWidth < 768;
  const isSessionPage = pathname.includes("/session/");

  return (
    <div className="flex h-screen bg-background overflow-hidden text-foreground">
      {/* Unified Sidebar */}
      <SessionNavSidebar />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 relative h-full overflow-hidden">
        <main 
          className={`flex-1 transition-all duration-300 ${isMobileViewport() ? "pt-14" : ""} ${
            !isSessionPage ? "overflow-y-auto" : "flex flex-col min-h-0"
          }`}
        >
          {children}
        </main>
      </div>

      <AnimatePresence>
        {isSearchOpen && (
          <SearchModal isOpen={true} onClose={() => setIsSearchOpen(false)} />
        )}
        {isSettingsOpen && (
          <SettingsModal isOpen={true} onClose={() => setIsSettingsOpen(false)} />
        )}
      </AnimatePresence>
    </div>
  );
}
