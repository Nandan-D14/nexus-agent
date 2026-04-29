"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { LogOut, Menu, X, PlusCircle, LayoutDashboard, Settings, History, ChevronLeft, ChevronRight, Plus, PanelLeft, Cpu, Search } from "lucide-react";
import { SIDEBAR_ACTIONS, NAV_LINKS } from "@/lib/navigation";
import { useAuth } from "@/lib/auth-context";
import { authenticatedFetch } from "@/lib/api-client";
import { DEFAULT_PLAN_QUOTA, type PlanQuota } from "@/lib/message-types";
import { motion, AnimatePresence } from "framer-motion";
import { SearchModal } from "./search-modal";

/* ------------------------------------------------------------------ */
/*  Nav items                                                          */
/* ------------------------------------------------------------------ */

const NAV_ITEMS = NAV_LINKS as unknown as ReadonlyArray<{ href: string; icon: any; label?: string; name?: string }>;

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function SessionNavSidebar() {
  const { user, signOutUser } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [quota, setQuota] = useState<PlanQuota | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true); // For mobile
  const [isCollapsed, setIsCollapsed] = useState(false); // For desktop
  const [isSearchOpen, setIsSearchOpen] = useState(false);

  const isMobileViewport = () => typeof window !== "undefined" && window.innerWidth < 768;

  useEffect(() => {
    if (!user) return;
    authenticatedFetch("/api/v1/user/quota")
      .then(async (res) => {
        if (res.ok) {
          setQuota((await res.json()) as PlanQuota);
          return;
        }
        setQuota(DEFAULT_PLAN_QUOTA);
      })
      .catch(() => {
        setQuota(DEFAULT_PLAN_QUOTA);
      });
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
      {/* Mobile Menu Toggle */}
      <button
        type="button"
        onClick={() => setIsSidebarOpen((prev) => !prev)}
        className={`fixed top-4 left-4 z-50 p-2 rounded-xl bg-white/80 dark:bg-[#161618]/80 backdrop-blur-xl border border-zinc-200 dark:border-zinc-800/50 text-zinc-600 dark:text-zinc-300 md:hidden shadow-lg`}
      >
        {isSidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
      </button>

      {/* Sidebar Container */}
      <aside
        className={`fixed top-0 left-0 z-40 h-screen bg-[#fafafa] dark:bg-[#161618] border-r border-zinc-200 dark:border-zinc-800/50 flex flex-col transition-all duration-300 ease-in-out shadow-2xl md:shadow-none ${
          isMobileViewport() 
            ? (isSidebarOpen ? "w-[260px] translate-x-0" : "w-[260px] -translate-x-full")
            : (isCollapsed ? "w-[72px]" : "w-[260px]")
        }`}
      >
        {/* Top Header / Toggle */}
        <div className={`p-4 flex items-center ${isCollapsed ? "justify-center" : "justify-between"} mt-1`}>
          {!isCollapsed && (
            <Link href="/" className="flex items-center gap-2 px-1">
              <span className="text-[15px] font-bold tracking-wide text-zinc-900 dark:text-zinc-100 flex items-center gap-2">
                <div className="w-5 h-5 text-indigo-500 dark:text-indigo-400">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-full h-full"><rect width="16" height="16" x="4" y="4" rx="2"/><rect width="6" height="6" x="9" y="9" rx="1"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/></svg>
                </div>
                CoComputer
              </span>
            </Link>
          )}
          <button
            type="button"
            onClick={() => isMobileViewport() ? setIsSidebarOpen(false) : setIsCollapsed(!isCollapsed)}
            className="p-1.5 rounded-lg text-zinc-500 hover:bg-zinc-200/50 dark:hover:bg-zinc-800/50 transition-colors"
          >
            {isMobileViewport() ? <X className="w-4 h-4" /> : isCollapsed ? <ChevronRight className="w-4 h-4" /> : <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/></svg>}
          </button>
        </div>

        {/* Actions (New Task) */}
        <div className="px-3 mt-2 space-y-1">
          <button
            onClick={handleNewSession}
            className={`w-full flex items-center gap-3 transition-all duration-200 rounded-lg ${
              isCollapsed 
                ? "justify-center p-2.5 bg-zinc-900 dark:bg-zinc-800/50 text-white dark:text-zinc-200" 
                : "px-3 py-2 bg-zinc-900 dark:bg-zinc-800/50 text-white dark:text-zinc-200 border border-zinc-800/50 shadow-sm"
            }`}
          >
            <Plus className="w-4 h-4" strokeWidth={2.5} />
            {!isCollapsed && <span className="text-[13px] font-medium tracking-tight">New task</span>}
          </button>

          <button
            onClick={() => {
              setIsSearchOpen(true);
              if (isMobileViewport()) setIsSidebarOpen(false);
            }}
            className={`w-full flex items-center gap-3 transition-all duration-200 rounded-lg text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200/50 dark:hover:bg-zinc-800/50 hover:text-zinc-900 dark:hover:text-zinc-200 ${
              isCollapsed ? "justify-center p-2.5" : "px-3 py-2"
            }`}
            title={isCollapsed ? "Search" : ""}
          >
            <Search className="w-4 h-4" />
            {!isCollapsed && <span className="text-[13px] font-medium tracking-tight">Search</span>}
          </button>
        </div>

        {/* Navigation Links */}
        <nav className="flex-1 px-3 mt-4 space-y-0.5 overflow-y-auto custom-scrollbar">
          {NAV_ITEMS.map(({ href, icon: Icon, label, name }) => {
            const active = pathname.startsWith(href);
            const displayName = label || name;

            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-3 rounded-lg transition-all duration-200 ${
                  isCollapsed ? "justify-center p-2.5" : "px-3 py-2"
                } ${
                  active
                    ? "bg-zinc-200/50 dark:bg-zinc-800/50 text-zinc-900 dark:text-zinc-100 font-medium"
                    : "text-zinc-500 dark:text-zinc-400 hover:bg-zinc-200/30 dark:hover:bg-zinc-800/50 hover:text-zinc-900 dark:hover:text-zinc-200"
                }`}
                title={isCollapsed ? displayName : ""}
                onClick={() => isMobileViewport() && setIsSidebarOpen(false)}
              >
                <Icon className={`w-4 h-4 ${active ? "text-indigo-500 dark:text-indigo-400" : ""}`} />
                {!isCollapsed && <span className="text-[13px] tracking-tight">{displayName}</span>}
              </Link>
            );
          })}
        </nav>

        {/* User Profile & Quota */}
        <div className="mt-auto p-3 border-t border-zinc-200 dark:border-zinc-800/50">
          {!isCollapsed && quota && (
             <div className="mb-4 px-3 py-2 rounded-lg bg-zinc-200/30 dark:bg-zinc-800/30 border border-black/5 dark:border-zinc-800/50">
                <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-2">
                  <span>Usage</span>
                  <span>{Math.min(100, Math.round((quota.used / quota.limit) * 100))}%</span>
                </div>
                <div className="h-1 w-full rounded-full bg-zinc-300 dark:bg-zinc-800 overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(100, (quota.used / quota.limit) * 100)}%` }}
                    className="h-full bg-zinc-600 dark:bg-indigo-500"
                  />
                </div>
             </div>
          )}

          <div className={`flex items-center gap-3 ${isCollapsed ? "justify-center" : "p-2 rounded-lg"}`}>
            <div className="w-8 h-8 rounded-full bg-zinc-900 dark:bg-zinc-800 flex items-center justify-center shrink-0 overflow-hidden border border-zinc-200 dark:border-zinc-700">
               {user?.photoURL ? (
                 <img src={user.photoURL} alt={user.displayName || "U"} className="w-full h-full object-cover" />
               ) : (
                 <span className="text-zinc-100 dark:text-zinc-400 font-bold text-xs">{initial}</span>
               )}
            </div>
            {!isCollapsed && (
              <div className="flex-1 min-w-0">
                <p className="text-[12px] font-semibold text-zinc-900 dark:text-zinc-200 truncate leading-none">
                  {user?.displayName || "User"}
                </p>
                <p className="text-[10px] text-zinc-500 truncate mt-1">{user?.email}</p>
              </div>
            )}
            {!isCollapsed && (
              <button
                onClick={handleSignOut}
                className="p-1.5 text-zinc-500 hover:text-red-500 transition-colors"
                title="Sign Out"
              >
                <LogOut className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </aside>

      {/* Spacer for desktop */}
      <div
        className={`hidden md:block shrink-0 transition-all duration-300 ease-in-out ${
          isCollapsed ? "w-[72px]" : "w-[260px]"
        }`}
      />

      {/* Mobile Overlay */}
      {isMobileViewport() && isSidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/40 backdrop-blur-sm transition-opacity"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      <AnimatePresence>
        {isSearchOpen && (
          <SearchModal isOpen={true} onClose={() => setIsSearchOpen(false)} />
        )}
      </AnimatePresence>
    </>
  );
}
