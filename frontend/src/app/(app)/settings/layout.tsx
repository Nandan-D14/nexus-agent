"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { User, Mic, Bell } from "lucide-react";
import { motion } from "framer-motion";

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  const tabs = [
    { name: "Profile", href: "/settings/profile", icon: User },
    { name: "Voice & AI", href: "/settings/voice", icon: Mic },
    { name: "Notifications", href: "/settings/notifications", icon: Bell },
  ];

  return (
    <div className="p-4 md:p-8 max-w-5xl mx-auto space-y-6 pb-20 h-full flex flex-col text-zinc-900 dark:text-zinc-100">
      <div className="shrink-0">
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
          Settings
        </h1>
        <p className="text-sm text-zinc-500 mt-2">
          Manage your account and preferences.
        </p>
      </div>

      <div className="flex flex-col md:flex-row gap-8 flex-1 mt-6">
        <nav className="flex md:flex-col gap-2 overflow-x-auto md:w-64 shrink-0 pb-4 md:pb-0 hide-scrollbar relative">
          {tabs.map((tab) => {
            const isActive = pathname === tab.href;
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={`relative flex items-center gap-3 px-4 py-2.5 rounded-full transition-all whitespace-nowrap ${
                  isActive
                    ? "bg-[#f4f4f5] dark:bg-[#212126] text-zinc-900 dark:text-zinc-100 font-medium"
                    : "text-zinc-500 hover:bg-[#f4f4f5] dark:hover:bg-[#212126] hover:text-zinc-900 dark:hover:text-zinc-100 font-medium"
                }`}
              >
                <tab.icon className="w-4 h-4" />
                <span className="text-sm">{tab.name}</span>
                {isActive && (
                  <motion.div
                    layoutId="activeSettingsTab"
                    className="absolute left-2 w-1 h-5 bg-zinc-900 dark:bg-zinc-100 rounded-full hidden md:block"
                  />
                )}
                {isActive && (
                  <motion.div
                    layoutId="activeSettingsTabBottom"
                    className="absolute bottom-0 inset-x-6 h-1 bg-zinc-900 dark:bg-zinc-100 rounded-t-full md:hidden"
                  />
                )}
              </Link>
            );
          })}
        </nav>

        <div className="flex-1 bg-white dark:bg-[#111114] border border-zinc-200 dark:border-[#2f2f35] rounded-3xl p-6 md:p-8 relative overflow-hidden h-fit shadow-sm">
          <div className="relative z-10 w-full">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}
