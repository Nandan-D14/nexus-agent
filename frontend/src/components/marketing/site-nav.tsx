/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { AppUser } from "@/lib/auth-context";
import { APP_DASHBOARD } from "@/lib/app-paths";
import { CocomputerLogo } from "@/components/brand/cocomputer-logo";

type SiteNavProps = {
  variant: "home" | "pricing" | "marketing";
  user: AppUser | null;
  authLoading?: boolean;
  isLaunching?: boolean;
  resumableSession?: boolean;
  onSignIn?: () => void;
  onSignOut?: () => void;
  onStart?: () => void;
};

export function SiteNav({
  variant,
  user,
  authLoading = false,
  isLaunching = false,
  resumableSession = false,
  onSignIn,
  onSignOut,
  onStart,
}: SiteNavProps) {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 50);
    handleScroll();
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <div className="fixed top-4 left-4 right-4 z-50 pointer-events-none">
      <nav
        className="nav-glass-prism pointer-events-auto mx-auto max-w-6xl h-14 px-3 sm:px-5 flex items-center justify-between gap-3"
        data-scrolled={scrolled ? "true" : "false"}
        aria-label="Primary"
      >
        <div className="relative z-10 flex items-center gap-6 min-w-0">
          <Link href="/" className="flex items-center gap-2 group shrink-0">
            <CocomputerLogo size={32} wordmarkClassName="text-base sm:text-lg" priority />
          </Link>

          {variant === "home" ? (
            <div className="hidden md:flex items-center gap-5 text-sm font-medium text-muted-foreground">
              <a
                href="#features"
                className="hover:text-foreground transition-colors"
              >
                Features
              </a>
              <a
                href="#integrations"
                className="hover:text-foreground transition-colors"
              >
                Integrations
              </a>
              <a
                href="#how-it-works"
                className="hover:text-foreground transition-colors"
              >
                How it Works
              </a>
              <Link
                href="/pricing"
                className="hover:text-foreground transition-colors"
              >
                Pricing
              </Link>
            </div>
          ) : null}

          {variant === "marketing" ? (
            <div className="hidden md:flex items-center gap-5 text-sm font-medium text-muted-foreground">
              <Link
                href="/pricing"
                className="hover:text-foreground transition-colors"
              >
                Pricing
              </Link>
              <Link
                href="/about"
                className="hover:text-foreground transition-colors"
              >
                About
              </Link>
              <Link
                href="/security"
                className="hover:text-foreground transition-colors"
              >
                Security
              </Link>
            </div>
          ) : null}
        </div>

        <div className="relative z-10 flex items-center gap-2 sm:gap-3 shrink-0">
          {variant === "pricing" || variant === "marketing" ? (
            <Link
              href="/"
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors px-2"
            >
              Home
            </Link>
          ) : null}
          {variant === "home" ? (
            user ? (
              <>
                <Link
                  href={APP_DASHBOARD}
                  className="hidden sm:block text-sm font-medium text-muted-foreground hover:text-foreground transition-colors px-2"
                >
                  Dashboard
                </Link>
                <button
                  type="button"
                  onClick={onStart}
                  disabled={isLaunching}
                  className="px-4 py-2 rounded-full bg-zinc-900 dark:bg-white text-white dark:text-black text-sm font-medium hover:bg-zinc-800 dark:hover:bg-zinc-200 transition-all active:scale-95 disabled:opacity-50"
                >
                  {isLaunching
                    ? "Starting..."
                    : resumableSession
                      ? "Resume Workspace"
                      : "Launch Console"}
                </button>
                <button
                  type="button"
                  onClick={onSignOut}
                  className="p-2 rounded-full text-muted-foreground hover:bg-zinc-100/80 dark:hover:bg-white/10 transition-colors text-sm"
                >
                  Sign out
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={onSignIn}
                disabled={authLoading}
                className="px-4 py-2 rounded-full bg-zinc-900 dark:bg-white text-white dark:text-black text-sm font-medium hover:bg-blue-600 dark:hover:bg-blue-500 transition-all shadow-md disabled:opacity-50"
              >
                {authLoading ? "Loading..." : "Get Started"}
              </button>
            )
          ) : user ? (
            <Link
              href={APP_DASHBOARD}
              className="px-4 py-2 rounded-full bg-zinc-900 dark:bg-white text-white dark:text-black text-sm font-medium hover:bg-zinc-800 dark:hover:bg-zinc-200 transition-all active:scale-95"
            >
              Dashboard
            </Link>
          ) : (
            <button
              type="button"
              onClick={onSignIn}
              className="px-4 py-2 rounded-full bg-zinc-900 dark:bg-white text-white dark:text-black text-sm font-medium hover:bg-blue-600 dark:hover:bg-blue-500 transition-all shadow-md"
            >
              Get Started
            </button>
          )}
        </div>
      </nav>
    </div>
  );
}
