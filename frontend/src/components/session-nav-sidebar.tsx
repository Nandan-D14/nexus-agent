"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  Cable,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  PlusCircle,
  Settings,
  X,
} from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { authenticatedFetch } from "@/lib/api-client";

/* ------------------------------------------------------------------ */
/*  Nav items                                                          */
/* ------------------------------------------------------------------ */

const NAV_ITEMS = [
  { href: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { href: "/history", icon: History, label: "History" },
  { href: "/connectors", icon: Cable, label: "Connectors" },
  { href: "/settings/api", icon: Settings, label: "Settings" },
] as const;

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function SessionNavSidebar() {
  const { user, signOutUser } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [quota, setQuota] = useState<{ limit: number; used: number; remaining: number } | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  const isMobileViewport = () => typeof window !== "undefined" && window.innerWidth < 768;

  useEffect(() => {
    if (!user) return;
    authenticatedFetch("/api/v1/user/quota")
      .then(async (res) => {
        if (res.ok) setQuota(await res.json());
      })
      .catch(() => {});
  }, [user]);

  const handleSignOut = async () => {
    await signOutUser();
    router.push("/");
  };

  const handleNewSession = useCallback(() => {
    if (!user) {
      if (isMobileViewport()) setIsSidebarOpen(false);
      router.push("/");
      return;
    }
    if (isMobileViewport()) setIsSidebarOpen(false);
    router.push("/session/new");
  }, [router, user]);

  const initial = user?.displayName?.[0]?.toUpperCase() ?? user?.email?.[0]?.toUpperCase() ?? "U";

  return (
    <>
      {/* Sidebar toggle - Mobile */}
      <button
        type="button"
        onClick={() => setIsSidebarOpen((prev) => !prev)}
        className={`fixed top-3 z-60 p-2 rounded-lg bg-card/90 dark:bg-[#0a0a0a]/90 border border-card-border dark:border-white/10 text-muted dark:text-zinc-300 hover:text-foreground dark:hover:text-white transition-all md:hidden ${
          isSidebarOpen ? "left-58" : "left-3"
        }`}
        title={isSidebarOpen ? "Close sidebar" : "Open sidebar"}
      >
        {isSidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
      </button>

      {/* Sidebar toggle - Desktop */}
      <button
        type="button"
        onClick={() => setIsSidebarOpen((prev) => !prev)}
        className={`hidden md:block fixed top-3 z-60 p-2 rounded-lg bg-white/90 dark:bg-[#0a0a0a]/90 border border-zinc-200 dark:border-white/10 text-zinc-600 dark:text-zinc-300 hover:text-zinc-900 dark:hover:text-white hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-all shadow-sm ${
          isSidebarOpen ? "left-[252px]" : "left-3"
        }`}
        title={isSidebarOpen ? "Close sidebar" : "Open sidebar"}
      >
        {isSidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
      </button>

      <aside
        className={`fixed top-0 left-0 z-40 h-screen w-64 bg-white dark:bg-[#111114] border-r border-zinc-200 dark:border-[#1c1c1e] flex flex-col transition-transform duration-300 ease-in-out ${
          isSidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
      <div className="p-4 md:p-6 pb-2">
        <div className="flex items-center justify-between">
          <Link href="/" className="flex items-center gap-3 px-2 group" title="NEXUS — New Session">
            <span className="text-xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
              Nexus
            </span>
          </Link>
          <button
            type="button"
            onClick={() => setIsSidebarOpen(false)}
            className="p-2 rounded-lg text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 hover:bg-zinc-100 dark:hover:bg-zinc-800"
            title="Close sidebar"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      <div className="px-4 py-2 mt-2">
        <button
          type="button"
          title="New Session"
          onClick={handleNewSession}
          className="flex items-center gap-2 justify-center w-full px-4 py-2 bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 rounded-full font-medium text-sm transition-colors hover:bg-zinc-800 dark:hover:bg-white"
        >
          <PlusCircle className="w-4 h-4" />
          New Chat
        </button>
      </div>

      <nav className="flex-1 px-3 py-4 flex flex-col gap-1 overflow-y-auto">
        {NAV_ITEMS.map(({ href, icon: Icon, label }) => {
          const active = pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              title={label}
              onClick={() => {
                if (isMobileViewport()) setIsSidebarOpen(false);
              }}
              className={`relative flex items-center gap-3 px-4 py-2.5 rounded-full transition-all ${
                active
                  ? "bg-[#f4f4f5] dark:bg-[#212126] text-zinc-900 dark:text-zinc-100 font-medium"
                  : "text-zinc-500 dark:text-zinc-400 hover:bg-[#f4f4f5] dark:hover:bg-[#212126] hover:text-zinc-900 dark:hover:text-zinc-100 font-medium"
              }`}
            >
              <Icon className="w-4 h-4" />
              <span className="text-sm">{label}</span>
              {active && (
                <span className="absolute left-2 w-1 h-5 bg-zinc-900 dark:bg-zinc-100 rounded-full" />
              )}
            </Link>
          );
        })}
      </nav>

      {quota && (
        <div className="px-4 pb-2">
          <div className="rounded-xl bg-background dark:bg-white/5 border border-card-border dark:border-white/10 px-3 py-2.5">
            <div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.15em] text-muted dark:text-zinc-500 mb-1.5">
              <span>Free Tier</span>
              <span
                className={
                  quota.remaining <= 0
                    ? "text-red-500"
                    : quota.used / quota.limit >= 0.8
                      ? "text-amber-500"
                      : "text-zinc-500 dark:text-zinc-400"
                }
              >
                {Math.min(100, Math.round((quota.used / quota.limit) * 100))}%
              </span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-zinc-200 dark:bg-zinc-800 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  quota.remaining <= 0
                    ? "bg-red-500"
                    : quota.used / quota.limit >= 0.8
                      ? "bg-amber-500"
                      : "bg-cyan-500"
                }`}
                style={{ width: `${Math.min(100, (quota.used / quota.limit) * 100)}%` }}
              />
            </div>
            <p className="text-[10px] text-muted dark:text-zinc-500 mt-1">
              {new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(
                quota.used
              )}{" "}
              /{" "}
              {new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(
                quota.limit
              )}{" "}
              tokens
            </p>
          </div>
        </div>
      )}

      <div className="p-4 border-t border-card-border dark:border-white/5">
        <div className="flex items-center gap-3 p-3 rounded-xl bg-background dark:bg-white/5 border border-card-border dark:border-white/10 shadow-sm dark:shadow-none">
          {user?.photoURL ? (
            <img src={user.photoURL} alt={user.displayName || "User"} className="w-10 h-10 rounded-full" />
          ) : (
            <div className="w-10 h-10 rounded-full bg-zinc-200 dark:bg-zinc-800 flex items-center justify-center">
              <span className="text-muted dark:text-zinc-400 font-bold text-lg">{initial}</span>
            </div>
          )}
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold text-foreground dark:text-zinc-200 truncate">
              {user?.displayName || "User"}
            </p>
            <p className="text-xs text-muted dark:text-zinc-500 truncate">{user?.email}</p>
          </div>
          <button
            suppressHydrationWarning
            onClick={handleSignOut}
            title="Sign Out"
            className="p-2 text-muted dark:text-zinc-400 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-500/10 dark:hover:bg-red-500/10 rounded-lg transition-colors"
          >
            <LogOut className="w-5 h-5" />
          </button>
        </div>
      </div>
      </aside>

      <div
        aria-hidden="true"
        className={`hidden md:block shrink-0 transition-[width] duration-300 ${
          isSidebarOpen ? "w-64" : "w-0"
        }`}
      />

      {isSidebarOpen && (
        <div
          className="md:hidden fixed inset-0 z-30 bg-black/50 backdrop-blur-sm"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}
    </>
  );
}
