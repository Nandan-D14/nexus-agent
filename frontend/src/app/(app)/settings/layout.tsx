"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { User, Mic, Terminal, Bell } from "lucide-react";
import { motion } from "framer-motion";

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  const tabs = [
    { name: "Profile", href: "/settings/profile", icon: User },
    { name: "Voice & AI", href: "/settings/voice", icon: Mic },
    { name: "API & Dev", href: "/settings/api", icon: Terminal },
    { name: "Notifications", href: "/settings/notifications", icon: Bell },
  ];

  return (
    <div className="p-4 md:p-8 max-w-5xl mx-auto space-y-8 pb-20 h-full flex flex-col">
      <div className="shrink-0">
        <h1 className="text-3xl md:text-5xl font-black italic uppercase tracking-tighter text-white">
          Settings
        </h1>
        <p className="text-zinc-400 mt-2">Manage your account and preferences.</p>
      </div>

      <div className="flex flex-col md:flex-row gap-8 flex-1">
        <nav className="flex md:flex-col gap-2 overflow-x-auto md:w-64 shrink-0 pb-4 md:pb-0 hide-scrollbar">
          {tabs.map((tab) => {
            const isActive = pathname === tab.href;
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-all whitespace-nowrap ${
                  isActive
                    ? "bg-white/10 text-cyan-400 font-bold"
                    : "text-zinc-400 hover:bg-white/5 hover:text-white font-medium"
                }`}
              >
                <tab.icon className="w-5 h-5" />
                <span>{tab.name}</span>
                {isActive && (
                  <motion.div
                    layoutId="activeSettingsTab"
                    className="absolute left-0 w-1 h-8 bg-cyan-500 rounded-r-full hidden md:block"
                  />
                )}
                {isActive && (
                  <motion.div
                    layoutId="activeSettingsTabBottom"
                    className="absolute bottom-0 inset-x-4 h-1 bg-cyan-500 rounded-t-full md:hidden"
                  />
                )}
              </Link>
            );
          })}
        </nav>

        <div className="flex-1 bg-white/[0.02] border border-white/5 rounded-3xl p-6 md:p-10 relative overflow-hidden h-fit">
          <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/5 via-transparent to-transparent opacity-50 pointer-events-none" />
          <div className="relative z-10">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}
