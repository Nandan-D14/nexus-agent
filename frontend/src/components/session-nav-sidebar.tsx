"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LayoutDashboard, History, Settings, PlusCircle, LogOut } from "lucide-react";
import { useAuth } from "@/lib/auth-context";

/* ------------------------------------------------------------------ */
/*  Nav items                                                          */
/* ------------------------------------------------------------------ */

const NAV_ITEMS = [
  { href: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { href: "/history",   icon: History,         label: "History"   },
  { href: "/settings/profile", icon: Settings, label: "Settings"  },
] as const;

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function SessionNavSidebar() {
  const { user, signOutUser } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  const handleSignOut = async () => {
    await signOutUser();
    router.push("/");
  };

  const initial = user?.displayName?.[0] ?? user?.email?.[0] ?? "U";

  return (
    <aside className="flex flex-col shrink-0 w-14 h-full bg-[#0a0a0a] border-r border-white/5 z-20">
      {/* Logo */}
      <div className="flex items-center justify-center h-14 border-b border-white/5 shrink-0">
        <Link
          href="/"
          className="w-9 h-9 rounded-xl bg-gradient-to-br from-cyan-400 to-emerald-400 flex items-center justify-center shadow-lg hover:scale-105 transition-transform"
          title="NEXUS — New Session"
        >
          <span className="text-black font-black text-xl italic">N</span>
        </Link>
      </div>

      {/* New session */}
      <div className="flex items-center justify-center py-3 border-b border-white/5 shrink-0">
        <Link
          href="/"
          title="New Session"
          className="w-9 h-9 rounded-xl bg-white/10 hover:bg-cyan-500/20 hover:text-cyan-400 text-zinc-400 flex items-center justify-center transition-colors"
        >
          <PlusCircle className="w-5 h-5" />
        </Link>
      </div>

      {/* Nav items */}
      <nav className="flex flex-col items-center gap-1 py-3 flex-1">
        {NAV_ITEMS.map(({ href, icon: Icon, label }) => {
          const active = pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              title={label}
              className={`relative w-9 h-9 rounded-xl flex items-center justify-center transition-colors ${
                active
                  ? "bg-white/10 text-cyan-400"
                  : "text-zinc-500 hover:bg-white/5 hover:text-white"
              }`}
            >
              {active && (
                <span className="absolute left-0 -translate-x-full top-1/2 -translate-y-1/2 w-1 h-5 bg-cyan-500 rounded-r-full" />
              )}
              <Icon className="w-5 h-5" />
            </Link>
          );
        })}
      </nav>

      {/* User avatar + sign out */}
      <div className="flex flex-col items-center gap-2 py-3 border-t border-white/5 shrink-0">
        <div
          className="w-9 h-9 rounded-full overflow-hidden border border-white/10 shrink-0"
          title={user?.email ?? ""}
        >
          {user?.photoURL ? (
            <img src={user.photoURL} alt={user.displayName ?? "User"} className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full bg-zinc-800 flex items-center justify-center">
              <span className="text-zinc-300 font-bold text-sm uppercase">{initial}</span>
            </div>
          )}
        </div>
        <button
          onClick={handleSignOut}
          title="Sign Out"
          className="w-9 h-9 rounded-xl text-zinc-500 hover:text-red-400 hover:bg-red-500/10 flex items-center justify-center transition-colors"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
    </aside>
  );
}
