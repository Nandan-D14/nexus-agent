"use client";

import { useAuth } from "@/lib/auth-context";
import { Mail, Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { useTheme } from "next-themes";

export default function ProfileSettingsPage() {
  const { user } = useAuth();
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return null;

  return (
    <div className="space-y-8 max-w-2xl text-zinc-900 dark:text-zinc-100">
      <div>
        <h2 className="text-xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-100 mb-2">Account</h2>
        <p className="text-sm text-zinc-500">Manage your user profile and workspace preferences.</p>
      </div>

      <div className="space-y-6">
        <section className="p-6 rounded-3xl bg-white dark:bg-[#1a1a1c] border border-zinc-200 dark:border-[#2f2f35]">
          <h3 className="text-sm font-medium text-zinc-900 dark:text-zinc-100 mb-4 flex items-center gap-2">
            <Mail className="w-4 h-4 text-zinc-500" />
            Contact Email
          </h3>
          <div className="flex items-center gap-3 w-full bg-zinc-50 dark:bg-zinc-800/50 p-3 rounded-full border border-zinc-200 dark:border-zinc-800">
             <div className="text-sm text-zinc-500 font-mono px-2">{user?.email || "Not signed in"}</div>
          </div>
          <p className="text-xs text-zinc-500 mt-2 px-2">This email is used for authentication and communications.</p>
        </section>

        {/* Appearance Settings */}
        <section className="p-6 rounded-3xl bg-white dark:bg-[#1a1a1c] border border-zinc-200 dark:border-[#2f2f35]">
          <h3 className="text-sm font-medium text-zinc-900 dark:text-zinc-100 mb-4 flex items-center gap-2">
            <Monitor className="w-4 h-4 text-zinc-500" />
            Theme Preferences
          </h3>
          
          <div className="flex flex-col sm:flex-row gap-3">
            <button
              onClick={() => setTheme("light")}
              className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm transition-all ${
                theme === "light" 
                  ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900" 
                  : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-700"
              }`}
            >
              <Sun className="w-4 h-4" />
              Light
            </button>
            <button
              onClick={() => setTheme("dark")}
              className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm transition-all ${
                theme === "dark" 
                  ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900" 
                  : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-700"
              }`}
            >
              <Moon className="w-4 h-4" />
              Dark
            </button>
            <button
              onClick={() => setTheme("system")}
              className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm transition-all ${
                theme === "system" 
                  ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900" 
                  : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-700"
              }`}
            >
              <Monitor className="w-4 h-4" />
              System
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
