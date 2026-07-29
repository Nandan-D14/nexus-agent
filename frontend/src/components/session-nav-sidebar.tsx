/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { memo, useCallback, useEffect, useState, type ReactNode } from "react";
import {
  ChevronDown,
  ChevronRight,
  LogOut,
  Menu,
  MoreVertical,
  Plus,
  Search,
  Settings,
  Trash2,
  X,
  type LucideIcon,
} from "lucide-react";
import { NAV_LINKS } from "@/lib/navigation";
import { useAuth } from "@/lib/auth-context";
import { authenticatedFetch } from "@/lib/api-client";
import { DEFAULT_PLAN_QUOTA, type PlanQuota, type RecentSession } from "@/lib/message-types";
import { useSettings } from "@/lib/settings-context";
import { useSession } from "@/lib/use-session";
import { useToast } from "./toast-provider";
import { useLiveDesktop } from "./live-desktop-provider";
import { SearchModal } from "./search-modal";
import { Badge } from "@/components/base/badges/badge";
import {
  Dropdown,
  DropdownDivider,
  DropdownGroup,
  DropdownItem,
  DropdownPopover,
  DropdownTrigger,
} from "@/components/base/dropdown/dropdown";
import { Kbd } from "@/components/base/kbd/kbd";
import { cx } from "@/utils/cx";

const NAV_ITEMS = NAV_LINKS as ReadonlyArray<{
  href: string;
  icon: LucideIcon;
  label?: string;
  name?: string;
}>;

function Collapsible({ collapsed, children }: { collapsed: boolean; children: ReactNode }) {
  return (
    <span
      className={cx(
        "flex min-w-0 items-center overflow-hidden transition-[max-width,opacity,filter] duration-300 ease-in-out",
        collapsed ? "max-w-0 opacity-0 blur-[3px]" : "max-w-48 opacity-100 blur-0",
      )}
    >
      {children}
    </span>
  );
}

function relativeTime(dateStr: string | null) {
  if (!dateStr) return "";
  const delta = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(delta / 60_000);
  if (minutes < 1) return "Now";
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days}d`;
  return new Date(dateStr).toLocaleDateString([], { month: "short", day: "numeric" });
}

export const SessionNavSidebar = memo(function SessionNavSidebar() {
  const { user, signOutUser } = useAuth();
  const { isSettingsOpen, setIsSettingsOpen } = useSettings();
  const { listSessions, destroySession } = useSession();
  const { clearDesktop } = useLiveDesktop();
  const { toast } = useToast();
  const pathname = usePathname();
  const router = useRouter();
  const [quota, setQuota] = useState<PlanQuota | null>(null);
  const [isMobile, setIsMobile] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isProfileOpen, setIsProfileOpen] = useState(false);
  const [sessions, setSessions] = useState<RecentSession[]>([]);
  const [isSessionsLoading, setIsSessionsLoading] = useState(false);
  const [activeMenuSessionId, setActiveMenuSessionId] = useState<string | null>(null);

  useEffect(() => {
    const query = window.matchMedia("(max-width: 767px)");
    const update = () => {
      setIsMobile(query.matches);
      if (!query.matches) setIsSidebarOpen(false);
    };
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  const fetchSessions = useCallback(() => {
    setIsSessionsLoading(true);
    listSessions(15)
      .then(setSessions)
      .finally(() => setIsSessionsLoading(false));
  }, [listSessions]);

  useEffect(() => {
    if (!user) return;
    void authenticatedFetch("/api/v1/user/quota")
      .then(async (response) => (response.ok ? (response.json() as Promise<PlanQuota>) : DEFAULT_PLAN_QUOTA))
      .then(setQuota)
      .catch(() => setQuota(DEFAULT_PLAN_QUOTA));
    void fetchSessions();
  }, [fetchSessions, user]);

  useEffect(() => {
    const onShortcut = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== "l" || (!event.metaKey && !event.ctrlKey)) return;
      event.preventDefault();
      setIsSearchOpen(true);
      setIsSidebarOpen(false);
    };
    window.addEventListener("keydown", onShortcut);
    return () => window.removeEventListener("keydown", onShortcut);
  }, []);

  const closeMobile = () => {
    if (isMobile) setIsSidebarOpen(false);
  };

  const handleNewSession = () => {
    closeMobile();
    router.push(user ? "/session/new" : "/");
  };

  const handleDeleteSession = async (sessionId: string) => {
    if (!confirm("Delete this conversation?")) return;

    if (await destroySession(sessionId)) {
      clearDesktop(sessionId);
      setSessions((current) => current.filter((session) => session.session_id !== sessionId));
      toast("Conversation deleted", "success");
      if (pathname.includes(sessionId)) router.push("/dashboard");
      return;
    }
    toast("Failed to delete conversation", "error");
  };

  const handleSignOut = async () => {
    await signOutUser();
    router.push("/");
  };

  const collapsed = !isMobile && isCollapsed;
  const initial = user?.displayName?.[0]?.toUpperCase() ?? user?.email?.[0]?.toUpperCase() ?? "U";
  const usage = quota ? Math.min(100, Math.round((quota.used / quota.limit) * 100)) : null;

  return (
    <>
      <button
        type="button"
        aria-label={isSidebarOpen ? "Close navigation" : "Open navigation"}
        aria-expanded={isSidebarOpen}
        onClick={() => setIsSidebarOpen((open) => !open)}
        className="fixed top-4 left-4 z-[60] inline-flex size-10 items-center justify-center rounded-full border border-border-button-white bg-background-secondary-default text-foreground-icon-secondary shadow-sidebar md:hidden"
      >
        {isSidebarOpen ? <X className="size-5" /> : <Menu className="size-5" />}
      </button>

      {isMobile && isSidebarOpen && (
        <button
          type="button"
          aria-label="Close navigation overlay"
          onClick={() => setIsSidebarOpen(false)}
          className="fixed inset-0 z-40 bg-black/35 backdrop-blur-sm md:hidden"
        />
      )}

      <aside
        className={cx(
          "fixed top-3 bottom-3 left-3 z-50 flex h-[calc(100dvh-24px)] shrink-0 flex-col overflow-hidden rounded-3xl border border-border-button-white bg-background-secondary-default shadow-sidebar transition-[width,transform] duration-300 ease-in-out md:sticky md:top-3 md:bottom-auto md:z-20 md:m-3 md:h-[calc(100vh-24px)] md:translate-x-0",
          collapsed ? "w-[60px] px-[11px] py-3" : "w-[260px] p-3",
          isMobile && !isSidebarOpen && "-translate-x-[calc(100%+24px)]",
        )}
      >
        <div className="flex min-h-0 flex-1 flex-col gap-3">
          <div className={cx("flex items-center", collapsed ? "flex-col-reverse gap-2.5" : "justify-between") }>
            <Link href="/dashboard" className={cx("flex min-w-0 items-center gap-2", collapsed && "justify-center") } onClick={closeMobile}>
              <span className="flex size-6 shrink-0 items-center justify-center rounded-lg bg-blue-500 text-sm font-bold text-white">C</span>
              <Collapsible collapsed={collapsed}>
                <span className="truncate text-title-3-semibold text-text-primary">CoComputer</span>
              </Collapsible>
            </Link>
            {isMobile ? (
              <button type="button" aria-label="Close navigation" onClick={closeMobile} className="text-foreground-icon-secondary">
                <X className="size-5" />
              </button>
            ) : (
              <button
                type="button"
                aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                onClick={() => setIsCollapsed((value) => !value)}
                className="flex size-9 items-center justify-center rounded-full text-foreground-icon-secondary hover:bg-background-secondary-hover"
              >
                <ChevronRight className={cx("size-5 transition-transform", !collapsed && "rotate-180")} />
              </button>
            )}
          </div>

          <button
            type="button"
            onClick={() => {
              setIsSearchOpen(true);
              closeMobile();
            }}
            title={collapsed ? "Quick Search" : undefined}
            className={cx(
              "flex items-center gap-2 rounded-full bg-background-tertiary-default p-2 text-foreground-icon-secondary transition-colors hover:bg-background-tertiary-hover",
              collapsed ? "size-9 justify-center" : "w-full",
            )}
          >
            <Search className="size-5 shrink-0" />
            <Collapsible collapsed={collapsed}>
              <span className="flex flex-1 items-center justify-between gap-2 text-body-medium text-text-secondary">
                Quick Search <Kbd>⌘L</Kbd>
              </span>
            </Collapsible>
          </button>

          <button
            type="button"
            onClick={handleNewSession}
            title={collapsed ? "New task" : undefined}
            className={cx(
              "flex items-center gap-2 rounded-2lg bg-linear-to-b from-blue-500 to-blue-600 p-2 text-white shadow-nav-selected",
              collapsed ? "size-9 justify-center" : "w-full",
            )}
          >
            <Plus className="size-5 shrink-0" />
            <Collapsible collapsed={collapsed}><span className="text-body-medium whitespace-nowrap">New task</span></Collapsible>
          </button>

          <nav className="flex flex-col gap-1" aria-label="Application">
            {NAV_ITEMS.map(({ href, icon: Icon, label, name }) => {
              const title = label ?? name ?? "";
              const active = pathname.startsWith(href) || (href === "/dashboard" && pathname.startsWith("/session/"));
              const settings = href === "/settings";
              const content = <><Icon className="size-5 shrink-0" /><Collapsible collapsed={collapsed}><span className="text-body-medium whitespace-nowrap">{title}</span></Collapsible></>;
              const className = cx(
                "flex items-center gap-2 rounded-2lg p-2 transition-colors",
                collapsed ? "size-9 justify-center" : "w-full",
                active || (settings && isSettingsOpen)
                  ? "bg-linear-to-b from-blue-500 to-blue-600 text-white shadow-nav-selected"
                  : "text-text-secondary hover:bg-background-secondary-hover",
              );
              if (settings) {
                return <button key={href} type="button" onClick={() => { setIsSettingsOpen(true); closeMobile(); }} title={collapsed ? title : undefined} className={className}>{content}</button>;
              }
              return <Link key={href} href={href} onClick={closeMobile} title={collapsed ? title : undefined} className={className}>{content}</Link>;
            })}
          </nav>

          {!collapsed && (
            <section className="flex min-h-0 flex-1 flex-col pt-2" aria-label="Recent conversations">
              <div className="mb-2 flex items-center justify-between px-2">
                <span className="text-caption-1-semibold tracking-wide text-text-tertiary uppercase">Recent chats</span>
                <Badge color="neutral">{sessions.length}</Badge>
              </div>
              <div className="custom-scrollbar flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto pr-1">
                {isSessionsLoading && sessions.length === 0 ? (
                  [0, 1, 2].map((item) => <div key={item} className="h-10 animate-pulse rounded-2lg bg-background-tertiary-default" />)
                ) : sessions.length === 0 ? (
                  <p className="px-2 py-4 text-center text-body-regular text-text-tertiary">No conversations yet</p>
                ) : sessions.map((session) => {
                  const active = pathname.includes(session.session_id);
                  const menuOpen = activeMenuSessionId === session.session_id;
                  return (
                    <div key={session.session_id} className="group relative">
                      <Link
                        href={`/session/${session.session_id}`}
                        onClick={closeMobile}
                        className={cx(
                          "flex min-w-0 items-center gap-2 rounded-2lg p-2 pr-8 transition-colors",
                          active ? "bg-background-tertiary-default text-text-primary" : "text-text-secondary hover:bg-background-secondary-hover",
                        )}
                      >
                        <span className="min-w-0 flex-1 truncate text-body-medium">{session.title || "New chat"}</span>
                        <span className="shrink-0 text-caption-1-regular text-text-tertiary">{relativeTime(session.updated_at)}</span>
                      </Link>
                      <div className="absolute top-1/2 right-1 -translate-y-1/2">
                        <Dropdown
                          isOpen={menuOpen}
                          onOpenChange={(open) => setActiveMenuSessionId(open ? session.session_id : null)}
                        >
                          <DropdownTrigger
                            aria-label={`Options for ${session.title || "New chat"}`}
                            className={cx("rounded-md p-1 text-foreground-icon-secondary hover:bg-background-tertiary-hover", menuOpen ? "opacity-100" : "opacity-0 group-hover:opacity-100")}
                          >
                            <MoreVertical className="size-4" />
                          </DropdownTrigger>
                          <DropdownPopover aria-label="Conversation actions" placement="bottom end" className="w-[190px]">
                            <DropdownGroup label="Conversation">
                              <DropdownItem onSelect={() => { router.push(`/session/${session.session_id}`); setActiveMenuSessionId(null); }}>
                                <span className="text-body-medium">Open chat</span>
                              </DropdownItem>
                            </DropdownGroup>
                            <DropdownDivider />
                            <DropdownGroup>
                              <DropdownItem
                                onSelect={() => { setActiveMenuSessionId(null); void handleDeleteSession(session.session_id); }}
                                className="text-red-500 hover:bg-red-500/10 focus-visible:bg-red-500/10"
                              >
                                <Trash2 className="size-4" /> <span className="text-body-medium">Delete conversation</span>
                              </DropdownItem>
                            </DropdownGroup>
                          </DropdownPopover>
                        </Dropdown>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          )}
        </div>

        <div className="mt-3 flex flex-col gap-3 border-t border-separator-border pt-3">
          {!collapsed && usage !== null && (
            <div className="rounded-2lg bg-background-tertiary-default p-2.5">
              <div className="mb-2 flex items-center justify-between text-caption-1-semibold text-text-secondary"><span>Usage</span><span>{usage}%</span></div>
              <div className="h-1 overflow-hidden rounded-full bg-badge-neutral-background"><div className="h-full rounded-full bg-blue-500 transition-[width]" style={{ width: `${usage}%` }} /></div>
            </div>
          )}
          <Dropdown isOpen={isProfileOpen} onOpenChange={setIsProfileOpen}>
            <DropdownTrigger
              aria-label="Account menu"
              className={cx("flex w-full items-center gap-2 rounded-xl p-1 text-left hover:bg-background-secondary-hover", collapsed && "justify-center")}
            >
              <span className="flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-full bg-blue-100 text-body-medium font-semibold text-blue-700 dark:bg-blue-950 dark:text-blue-200">
                {user?.photoURL ? <img src={user.photoURL} alt="" className="size-full object-cover" /> : initial}
              </span>
              <Collapsible collapsed={collapsed}>
                <span className="flex min-w-0 flex-1 items-center gap-1"><span className="min-w-0 flex-1"><span className="block truncate text-body-medium text-text-primary">{user?.displayName || "User"}</span><span className="block truncate text-caption-1-regular text-text-tertiary">{user?.email}</span></span><ChevronDown className={cx("size-4 shrink-0 text-foreground-icon-tertiary transition-transform", isProfileOpen && "rotate-180")} /></span>
              </Collapsible>
            </DropdownTrigger>
            <DropdownPopover aria-label="Account menu" placement={isMobile ? "bottom start" : "right bottom"} className="w-[240px]">
              <div className="px-2 pt-1 pb-2"><p className="truncate text-body-medium text-text-primary">{user?.displayName || "User"}</p><p className="truncate text-caption-1-regular text-text-secondary">{user?.email}</p></div>
              <DropdownDivider />
              <DropdownGroup>
                <DropdownItem onSelect={() => { setIsProfileOpen(false); setIsSettingsOpen(true); }}><Settings className="size-4 text-foreground-icon-secondary" /><span className="text-body-medium">Settings</span></DropdownItem>
                <DropdownItem onSelect={() => void handleSignOut()} className="text-red-500 hover:bg-red-500/10 focus-visible:bg-red-500/10"><LogOut className="size-4" /><span className="text-body-medium">Sign out</span></DropdownItem>
              </DropdownGroup>
            </DropdownPopover>
          </Dropdown>
        </div>
      </aside>

      {isSearchOpen && <SearchModal isOpen onClose={() => setIsSearchOpen(false)} />}
    </>
  );
});
