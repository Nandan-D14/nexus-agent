"use client";

import { useAuth } from "@/lib/auth-context";
import { useRouter, usePathname } from "next/navigation";
import { motion } from "framer-motion";
import {
  LayoutDashboard,
  History,
  Settings,
  PlusCircle,
  Menu,
  LogOut,
  X
} from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, signOutUser, isLoading: isAuthLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navigation = [
    { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
    { name: "History", href: "/history", icon: History },
    { name: "Settings", href: "/settings/profile", icon: Settings },
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
            className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-all ${
              isActive
                ? "bg-black/5 dark:bg-white/10 text-cyan-600 dark:text-cyan-400 font-bold"
                : "text-muted dark:text-zinc-400 hover:bg-black/5 dark:hover:bg-white/5 hover:text-foreground font-medium"
            }`}
          >
            <item.icon className="w-5 h-5" />
            <span className="text-sm tracking-wide">{item.name}</span>
            {isActive && (
              <motion.div
                layoutId="activeNav"
                className="absolute left-0 w-1 h-8 bg-cyan-600 dark:bg-cyan-500 rounded-r-full"
              />
            )}
          </Link>
        );
      })}
    </>
  );

  return (
    <div className="flex h-screen bg-background overflow-hidden text-foreground selection:bg-cyan-500/30">
      {/* Mobile Header */}
      <div className="md:hidden fixed top-0 left-0 right-0 h-16 bg-background/80 backdrop-blur-xl border-b border-zinc-200 dark:border-white/5 z-50 flex items-center justify-between px-4">
        <Link href="/" className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-400 to-emerald-400 flex items-center justify-center">
            <span className="text-black font-black text-xl italic">N</span>
          </div>
          <span className="font-black tracking-tighter italic uppercase text-lg text-foreground">Nexus</span>
        </Link>
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="p-2 text-zinc-500 dark:text-zinc-400 hover:text-foreground"
        >
          {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
        </button>
      </div>

      {/* Sidebar */}
      <motion.aside
        className={`fixed md:sticky top-0 left-0 z-40 h-screen w-64 bg-card dark:bg-[#0a0a0a] border-r border-card-border dark:border-white/5 flex flex-col transition-transform duration-300 ease-in-out ${
          mobileMenuOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        }`}
      >
        <div className="p-6">
          <Link href="/" className="flex items-center gap-3 group">
            <div className="relative w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-400 to-emerald-400 flex items-center justify-center shadow-lg transform group-hover:rotate-6 transition-transform">
              <span className="text-black font-black text-2xl italic">N</span>
            </div>
            <span className="text-2xl font-black tracking-tighter italic uppercase group-hover:text-cyan-600 dark:group-hover:text-cyan-400 transition-colors text-foreground">Nexus</span>
          </Link>
        </div>

        <div className="px-4 py-2">
          <button
            type="button"
            onClick={handleNewSession}
            className="flex items-center gap-2 justify-center w-full px-4 py-3 bg-zinc-900 dark:bg-white text-white dark:text-black rounded-xl font-bold text-sm tracking-wider uppercase hover:bg-cyan-600 dark:hover:bg-cyan-400 transition-colors shadow-none dark:shadow-lg active:scale-95"
          >
            <PlusCircle className="w-5 h-5" />
            New Session
          </button>
        </div>

        <nav className="flex-1 px-3 py-6 flex flex-col gap-2 overflow-y-auto">
          <NavLinks />
        </nav>

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
      <main className="flex-1 h-screen overflow-y-auto w-full pt-16 md:pt-0">
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
