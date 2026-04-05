"use client";

import { useAuth } from "@/lib/auth-context";
import { useRouter, usePathname } from "next/navigation";
import { motion } from "framer-motion";
import {
  Cable,
  LayoutDashboard,
  History,
  Settings,
  PlusCircle,
  Menu,
  LogOut,
  Workflow,
  X
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { authenticatedFetch } from "@/lib/api-client";
import { DEFAULT_PLAN_QUOTA, type PlanQuota } from "@/lib/message-types";

const NAVIGATION = [
  { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { name: "History", href: "/history", icon: History },
  { name: "Templates", href: "/templates", icon: Workflow },
  { name: "Connectors", href: "/connectors", icon: Cable },
  { name: "Settings", href: "/settings/api", icon: Settings },
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, signOutUser, isLoading: isAuthLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [quota, setQuota] = useState<PlanQuota | null>(null);

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
      router.push("/");
      return;
    }
    router.push("/session/new");
  }, [router, user]);

  return (
    <div className="flex h-screen bg-background overflow-hidden text-foreground">
      {/* Mobile Header */}
      <div className="md:hidden fixed top-0 left-0 right-0 h-14 bg-background/80 backdrop-blur-xl border-b border-card-border z-50 flex items-center justify-between px-4">
        <Link href="/" className="flex items-center gap-2">
          <span className="font-semibold tracking-tight text-lg">Nexus</span>
        </Link>
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="p-2 text-muted-foreground hover:text-foreground"
        >
          {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
        </button>
      </div>

      {/* Sidebar */}
      <motion.aside
        className={`fixed md:sticky top-0 left-0 z-40 h-screen w-64 bg-card border-r border-card-border flex flex-col transition-transform duration-300 ease-in-out ${
          mobileMenuOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        }`}
      >
        <div className="p-4 md:p-6 pb-2">
          <Link href="/" className="flex items-center gap-3 px-2 group">
            <span className="text-xl font-semibold tracking-tight">
              Nexus
            </span>
          </Link>
        </div>

        <div className="px-4 py-2 mt-2">
          <button
            type="button"
            onClick={handleNewSession}
            className="flex items-center gap-2 justify-center w-full px-4 py-2 bg-foreground text-background rounded-full font-medium text-sm transition-colors hover:bg-foreground/90"
          >
            <PlusCircle className="w-4 h-4" />
            New Chat
          </button>
        </div>

        <nav className="flex-1 px-3 py-4 flex flex-col gap-1 overflow-y-auto">
          {NAVIGATION.map((item) => {
            const isActive = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileMenuOpen(false)}
                className={`relative flex items-center gap-3 px-4 py-2.5 rounded-full transition-all ${
                  isActive
                    ? "bg-muted text-foreground font-medium"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground font-medium"
                }`}
              >
                <item.icon className="w-4 h-4" />
                <span className="text-sm">{item.name}</span>
                {isActive && (
                  <motion.div
                    layoutId="activeNav"
                    className="absolute left-2 w-1 h-5 bg-foreground rounded-full"
                  />
                )}
              </Link>
            );
          })}
        </nav>

        {/* Starter Plan */}
        {quota && (
          <div className="px-4 pb-2">
            <div className="rounded-xl bg-muted/50 border border-card-border px-3 py-2.5">
              <div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.15em] text-muted-foreground mb-1.5">
                <span>{quota.plan_name || "$5 Starter"}</span>
                <span className={`${
                  quota.remaining <= 0
                    ? "text-error"
                    : quota.used / quota.limit >= 0.8
                      ? "text-warning"
                      : "text-muted-foreground"
                }`}>
                  {Math.min(100, Math.round((quota.used / quota.limit) * 100))}%
                </span>
              </div>
              <div className="h-1.5 w-full rounded-full bg-zinc-200 dark:bg-zinc-800 overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    quota.remaining <= 0
                      ? "bg-error"
                      : quota.used / quota.limit >= 0.8
                        ? "bg-warning"
                        : "bg-accent"
                  }`}
                  style={{ width: `${Math.min(100, (quota.used / quota.limit) * 100)}%` }}
                />
              </div>
              <p className="text-[10px] text-muted-foreground mt-1">
                <span className="block font-semibold text-foreground/70">
                  {new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(quota.used)} / {new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(quota.limit)} {quota.unit || "credits"}
                </span>
              </p>
            </div>
          </div>
        )}

        <div className="p-4 border-t border-card-border">
          <div className="flex items-center gap-3 p-3 rounded-xl bg-muted/50 border border-card-border shadow-sm dark:shadow-none">
            {user?.photoURL ? (
              <img
                src={user.photoURL}
                alt={user.displayName || "User"}
                className="w-10 h-10 rounded-full"
              />
            ) : (
              <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center">
                <span className="text-muted-foreground font-bold text-lg">
                  {user?.email?.[0].toUpperCase() || "U"}
                </span>
              </div>
            )}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-bold text-foreground truncate">
                {user?.displayName || "User"}
              </p>
              <p className="text-xs text-muted-foreground truncate">
                {user?.email}
              </p>
            </div>
            <button
              onClick={handleSignOut}
              disabled={isAuthLoading}
              className="p-2 text-muted-foreground hover:text-error hover:bg-error/10 rounded-lg transition-colors"
              title="Sign Out"
            >
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </div>
      </motion.aside>

      {/* Main Content */}
      <main className="flex-1 h-screen overflow-y-auto w-full pt-14 md:pt-0">
        {children}
      </main>

      {/* Mobile overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black/50 backdrop-blur-sm z-30 md:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}
    </div>
  );
}
