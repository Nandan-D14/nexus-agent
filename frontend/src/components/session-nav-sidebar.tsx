/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState, memo } from "react";
import { LogOut, Menu, X, ChevronRight, Plus, Search, MessageSquare, Trash2, MoreVertical, type LucideIcon } from "lucide-react";
import { NAV_LINKS } from "@/lib/navigation";
import { useAuth } from "@/lib/auth-context";
import { authenticatedFetch } from "@/lib/api-client";
import { DEFAULT_PLAN_QUOTA, type PlanQuota, type RecentSession } from "@/lib/message-types";
import { motion, AnimatePresence } from "framer-motion";
import { SearchModal } from "./search-modal";
import { SettingsModal } from "./settings-modal";
import { useSettings } from "@/lib/settings-context";
import { useSession } from "@/lib/use-session";
import { useToast } from "./toast-provider";

/* ------------------------------------------------------------------ */
/*  Nav items                                                          */
/* ------------------------------------------------------------------ */

const NAV_ITEMS = NAV_LINKS as ReadonlyArray<{ href: string; icon: LucideIcon; label?: string; name?: string }>;

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export const SessionNavSidebar = memo(function SessionNavSidebar() {
  const { user, signOutUser } = useAuth();
  const { isSettingsOpen, setIsSettingsOpen } = useSettings();
  const { listSessions, destroySession } = useSession();
  const { toast } = useToast();
  const pathname = usePathname();
  const router = useRouter();
  const [quota, setQuota] = useState<PlanQuota | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true); // For mobile
  const [isCollapsed, setIsCollapsed] = useState(false); // For desktop
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [sessions, setSessions] = useState<RecentSession[]>([]);
  const [isSessionsLoading, setIsSessionsLoading] = useState(false);
  const [activeMenuSessionId, setActiveMenuSessionId] = useState<string | null>(null);

  const isMobileViewport = () => typeof window !== "undefined" && window.innerWidth < 768;

  useEffect(() => {
    const handleClickOutside = () => setActiveMenuSessionId(null);
    window.addEventListener("click", handleClickOutside);
    return () => window.removeEventListener("click", handleClickOutside);
  }, []);

  const fetchSessions = useCallback(() => {
    setIsSessionsLoading(true);
    listSessions(15).then(data => {
      setSessions(data);
      setIsSessionsLoading(false);
    });
  }, [listSessions]);

  useEffect(() => {
    if (!user) return;
    
    // Fetch Quota
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

    // Fetch Recent Sessions
    fetchSessions();
  }, [user, fetchSessions]);

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

  const handleDeleteSession = async (e: React.MouseEvent, sid: string) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (!confirm("Are you sure you want to delete this conversation?")) return;

    const success = await destroySession(sid);
    if (success) {
      setSessions(prev => prev.filter(s => s.session_id !== sid));
      toast("Conversation deleted", "success");
      if (pathname.includes(sid)) {
        router.push("/dashboard");
      }
    } else {
      toast("Failed to delete conversation", "error");
    }
  };

  const initial = user?.displayName?.[0]?.toUpperCase() ?? user?.email?.[0]?.toUpperCase() ?? "U";

  const formatRelativeTime = (dateStr: string | null) => {
    if (!dateStr) return "";
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString([], { month: "short", day: "numeric" });
  };

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
        className={`fixed top-0 left-0 z-40 h-screen bg-sidebar-bg border-r border-sidebar-border flex flex-col transition-all duration-300 ease-in-out shadow-2xl md:shadow-none ${
          isMobileViewport() 
            ? (isSidebarOpen ? "w-[260px] translate-x-0" : "w-[260px] -translate-x-full")
            : (isCollapsed ? "w-[72px]" : "w-[260px]")
        }`}
      >
        {/* Top Header / Toggle */}
        <div className={`p-4 flex items-center ${isCollapsed ? "justify-center" : "justify-between"} mt-1`}>
          {!isCollapsed && (
            <Link href="/" className="flex items-center gap-2 px-1">
              <span className="text-[15px] font-bold tracking-wide text-foreground flex items-center gap-2">
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
            className="p-1.5 rounded-lg text-muted-foreground hover:bg-zinc-200/50 dark:hover:bg-zinc-800/50 transition-colors"
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
                ? "justify-center p-2.5 bg-zinc-900 dark:bg-zinc-800/50 text-white dark:text-foreground" 
                : "px-3 py-2 bg-zinc-900 dark:bg-zinc-800/50 text-white dark:text-foreground border border-zinc-800/50 shadow-sm"
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
            className={`w-full flex items-center gap-3 transition-all duration-200 rounded-lg text-muted-foreground hover:bg-zinc-200/50 dark:hover:bg-zinc-800/50 hover:text-foreground ${
              isCollapsed ? "justify-center p-2.5" : "px-3 py-2"
            }`}
            title={isCollapsed ? "Search" : ""}
          >
            <Search className="w-4 h-4" />
            {!isCollapsed && <span className="text-[13px] font-medium tracking-tight">Search</span>}
          </button>
        </div>

        {/* Navigation Links */}
        <nav className="px-3 mt-4 space-y-0.5 shrink-0">
          {NAV_ITEMS.map(({ href, icon: Icon, label, name }) => {
            const active = pathname.startsWith(href);
            const displayName = label || name;
            const isSettings = href === "/settings";

            if (isSettings) {
              return (
                <button
                  key={href}
                  type="button"
                  onClick={() => {
                    setIsSettingsOpen(true);
                    if (isMobileViewport()) setIsSidebarOpen(false);
                  }}
                  className={`w-full flex items-center gap-3 rounded-lg transition-all duration-200 ${
                    isCollapsed ? "justify-center p-2.5" : "px-3 py-2"
                  } ${
                    isSettingsOpen
                      ? "bg-zinc-200/50 dark:bg-zinc-800/50 text-foreground font-medium"
                      : "text-muted-foreground hover:bg-zinc-200/30 dark:hover:bg-zinc-800/50 hover:text-foreground"
                  }`}
                  title={isCollapsed ? displayName : ""}
                >
                  <Icon className={`w-4 h-4 ${isSettingsOpen ? "text-indigo-500 dark:text-indigo-400" : ""}`} />
                  {!isCollapsed && <span className="text-[13px] tracking-tight">{displayName}</span>}
                </button>
              );
            }

            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-3 rounded-lg transition-all duration-200 ${
                  isCollapsed ? "justify-center p-2.5" : "px-3 py-2"
                } ${
                  active
                    ? "bg-zinc-200/50 dark:bg-zinc-800/50 text-foreground font-medium"
                    : "text-muted-foreground hover:bg-zinc-200/30 dark:hover:bg-zinc-800/50 hover:text-foreground"
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

        {/* Recent Sessions History */}
        {!isCollapsed && (
          <div className="flex-1 flex flex-col min-h-0 mt-6 px-3 mb-2 overflow-hidden">
            <h3 className="px-3 mb-2 text-[10px] font-bold uppercase tracking-[0.15em] text-zinc-500 dark:text-zinc-500">
              Recent Conversations
            </h3>
            <div className="flex-1 overflow-y-auto custom-scrollbar space-y-0.5 pr-1">
              {isSessionsLoading && sessions.length === 0 ? (
                <div className="px-3 py-4 space-y-3">
                  {[1, 2, 3].map(i => (
                    <div key={i} className="h-3 w-full bg-zinc-200 dark:bg-zinc-800/50 rounded-full animate-pulse" />
                  ))}
                </div>
              ) : sessions.length === 0 ? (
                <div className="px-3 py-6 text-center">
                  <p className="text-[11px] text-zinc-500 dark:text-zinc-600 font-medium italic">No recent chat history</p>
                </div>
              ) : (
                sessions.map((s) => {
                  const active = pathname.includes(s.session_id);
                  const menuOpen = activeMenuSessionId === s.session_id;

                  return (
                    <div key={s.session_id} className="relative group">
                      <Link
                        href={`/session/${s.session_id}`}
                        className={`flex items-center gap-3 rounded-xl px-3 py-2.5 transition-all duration-200 border ${
                          active
                            ? "bg-white dark:bg-white/[0.05] border-zinc-200 dark:border-white/10 text-indigo-500 dark:text-indigo-400 shadow-sm"
                            : "border-transparent text-muted-foreground hover:bg-zinc-200/50 dark:hover:bg-white/5 hover:text-foreground"
                        }`}
                        onClick={() => isMobileViewport() && setIsSidebarOpen(false)}
                      >
                        <div className="flex-1 min-w-0 flex flex-col gap-0.5">
                          <span className="text-[12.5px] font-medium truncate leading-tight">
                            {s.title || "New Chat"}
                          </span>
                          <span className="text-[9px] uppercase tracking-wider text-zinc-400 dark:text-zinc-600 font-bold">
                            {formatRelativeTime(s.updated_at)}
                          </span>
                        </div>
                      </Link>

                      {/* Hover/Menu Actions */}
                      <div className={`flex items-center absolute right-2 top-1/2 -translate-y-1/2 transition-opacity ${menuOpen ? "opacity-100" : "opacity-0 group-hover:opacity-100"}`}>
                        <button
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            setActiveMenuSessionId(menuOpen ? null : s.session_id);
                          }}
                          className={`p-1 rounded-md transition-colors ${menuOpen ? "bg-zinc-200 dark:bg-zinc-800 text-zinc-300" : "hover:bg-zinc-500/10 hover:text-zinc-300"}`}
                          title="More options"
                        >
                          <MoreVertical className="w-3.5 h-3.5" />
                        </button>
                      </div>

                      {/* Dropdown Menu */}
                      <AnimatePresence>
                        {menuOpen && (
                          <motion.div
                            initial={{ opacity: 0, scale: 0.95, y: -10 }}
                            animate={{ opacity: 1, scale: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.95, y: -10 }}
                            className="absolute right-0 top-full mt-1 z-50 w-36 rounded-xl border border-zinc-200 dark:border-white/10 bg-white dark:bg-zinc-900 shadow-xl overflow-hidden py-1"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <button
                              onClick={(e) => {
                                handleDeleteSession(e, s.session_id);
                                setActiveMenuSessionId(null);
                              }}
                              className="w-full flex items-center gap-2 px-3 py-2 text-[12px] text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                              <span>Delete chat</span>
                            </button>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        )}

        {/* User Profile & Quota */}
        <div className="mt-auto p-3 border-t border-sidebar-border">
          {!isCollapsed && quota && (
             <div className="mb-4 px-3 py-2 rounded-lg bg-zinc-200/30 dark:bg-zinc-800/30 border border-black/5 dark:border-card-border">
                <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">
                  <span>Usage</span>
                  <span>{Math.min(100, Math.round((quota.used / quota.limit) * 100))}%</span>
                </div>
                <div className="h-1 w-full rounded-full bg-zinc-300 dark:bg-muted overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(100, (quota.used / quota.limit) * 100)}%` }}
                    className="h-full bg-zinc-600 dark:bg-indigo-500"
                  />
                </div>
             </div>
          )}

          <div className={`flex items-center gap-3 ${isCollapsed ? "justify-center" : "p-2 rounded-lg"}`}>
            <div className="w-8 h-8 rounded-full bg-zinc-900 dark:bg-muted flex items-center justify-center shrink-0 overflow-hidden border border-zinc-200 dark:border-zinc-700">
               {user?.photoURL ? (
                 <img src={user.photoURL} alt={user.displayName || "U"} className="w-full h-full object-cover" />
               ) : (
                 <span className="text-zinc-100 dark:text-muted-foreground font-bold text-xs">{initial}</span>
               )}
            </div>
            {!isCollapsed && (
              <div className="flex-1 min-w-0">
                <p className="text-[12px] font-semibold text-foreground truncate leading-none">
                  {user?.displayName || "User"}
                </p>
                <p className="text-[10px] text-muted-foreground truncate mt-1">{user?.email}</p>
              </div>
            )}
            {!isCollapsed && (
              <button
                onClick={handleSignOut}
                className="p-1.5 text-muted-foreground hover:text-red-500 transition-colors"
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
        {isSettingsOpen && (
          <SettingsModal isOpen={true} onClose={() => setIsSettingsOpen(false)} />
        )}
      </AnimatePresence>
    </>
  );
});
