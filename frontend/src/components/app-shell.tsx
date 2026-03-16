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
  X
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { authenticatedFetch } from "@/lib/api-client";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, signOutUser, isLoading: isAuthLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [quota, setQuota] = useState<{ limit: number; used: number; remaining: number } | null>(null);

  useEffect(() => {
    if (!user) return;
    authenticatedFetch("/api/v1/user/quota")
      .then(async (res) => {
        if (res.ok) setQuota(await res.json());
      })
      .catch(() => {});
  }, [user]);

  const navigation = [
    { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
    { name: "History", href: "/history", icon: History },
    { name: "Connectors", href: "/connectors", icon: Cable },
    { name: "Settings", href: "/settings/api", icon: Settings },
  ];

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

  const NavLinks = () => (
    <>
      {navigation.map((item) => {
        const isActive = pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={() => setMobileMenuOpen(false)}
            className={`relative flex items-center gap-3 px-4 py-2.5 rounded-full transition-all ${
              isActive
                ? "bg-[#f4f4f5] dark:bg-[#212126] text-zinc-900 dark:text-zinc-100 font-medium"
                : "text-zinc-500 dark:text-zinc-400 hover:bg-[#f4f4f5] dark:hover:bg-[#212126] hover:text-zinc-900 dark:hover:text-zinc-100 font-medium"
            }`}
          >
            <item.icon className="w-4 h-4" />
            <span className="text-sm">{item.name}</span>
            {isActive && (
              <motion.div
                layoutId="activeNav"
                className="absolute left-2 w-1 h-5 bg-zinc-900 dark:bg-zinc-100 rounded-full"
              />
            )}
          </Link>
        );
      })}
    </>
  );

  return (
    <div className="flex h-screen bg-white dark:bg-[#09090b] overflow-hidden text-zinc-900 dark:text-zinc-100">
      {/* Mobile Header */}
      <div className="md:hidden fixed top-0 left-0 right-0 h-14 bg-white/80 dark:bg-[#09090b]/80 backdrop-blur-xl border-b border-zinc-200 dark:border-[#1c1c1e] z-50 flex items-center justify-between px-4">
        <Link href="/" className="flex items-center gap-2">
          <span className="font-semibold tracking-tight text-lg text-zinc-900 dark:text-zinc-100">Nexus</span>
        </Link>
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="p-2 text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100"
        >
          {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
        </button>
      </div>

      {/* Sidebar */}
      <motion.aside
        className={`fixed md:sticky top-0 left-0 z-40 h-screen w-64 bg-white dark:bg-[#111114] border-r border-zinc-200 dark:border-[#1c1c1e] flex flex-col transition-transform duration-300 ease-in-out ${
          mobileMenuOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        }`}
      >
        <div className="p-4 md:p-6 pb-2">
          <Link href="/" className="flex items-center gap-3 px-2 group">
            <span className="text-xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
              Nexus
            </span>
          </Link>
        </div>

        <div className="px-4 py-2 mt-2">
          <button
            type="button"
            onClick={handleNewSession}
            className="flex items-center gap-2 justify-center w-full px-4 py-2 bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 rounded-full font-medium text-sm transition-colors hover:bg-zinc-800 dark:hover:bg-white"
          >
            <PlusCircle className="w-4 h-4" />
            New Chat
          </button>
        </div>

        <nav className="flex-1 px-3 py-4 flex flex-col gap-1 overflow-y-auto">
          <NavLinks />
        </nav>

        {/* Token Quota */}
        {quota && (
          <div className="px-4 pb-2">
            <div className="rounded-xl bg-background dark:bg-white/5 border border-card-border dark:border-white/10 px-3 py-2.5">
              <div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.15em] text-muted dark:text-zinc-500 mb-1.5">
                <span>Free Tier</span>
                <span className={`${
                  quota.remaining <= 0
                    ? "text-red-500"
                    : quota.used / quota.limit >= 0.8
                      ? "text-amber-500"
                      : "text-zinc-500 dark:text-zinc-400"
                }`}>
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
                {new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(quota.used)} / {new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(quota.limit)} tokens
              </p>
            </div>
          </div>
        )}

        <div className="p-4 border-t border-card-border dark:border-white/5">
          <div className="flex items-center gap-3 p-3 rounded-xl bg-background dark:bg-white/5 border border-card-border dark:border-white/10 shadow-sm dark:shadow-none">
            {user?.photoURL ? (
              <img
                src={user.photoURL}
                alt={user.displayName || "User"}
                className="w-10 h-10 rounded-full"
              />
            ) : (
              <div className="w-10 h-10 rounded-full bg-zinc-200 dark:bg-zinc-800 flex items-center justify-center">
                <span className="text-muted dark:text-zinc-400 font-bold text-lg">
                  {user?.email?.[0].toUpperCase() || "U"}
                </span>
              </div>
            )}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-bold text-foreground dark:text-zinc-200 truncate">
                {user?.displayName || "User"}
              </p>
              <p className="text-xs text-muted dark:text-zinc-500 truncate">
                {user?.email}
              </p>
            </div>
            <button
              onClick={handleSignOut}
              disabled={isAuthLoading}
              className="p-2 text-muted dark:text-zinc-400 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-500/10 dark:hover:bg-red-500/10 rounded-lg transition-colors"
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
