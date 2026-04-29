"use client";

import { useState } from "react";
import { ChevronRight, Moon, Sun, Bell, Lock, LogOut, HelpCircle } from "lucide-react";

export default function SettingsPage() {
  const [darkMode, setDarkMode] = useState(true);
  const [notifications, setNotifications] = useState(true);

  const settingsSections = [
    {
      title: "Appearance",
      items: [
        {
          label: "Dark Mode",
          description: "Use dark theme for CoComputer",
          icon: darkMode ? Moon : Sun,
          action: () => setDarkMode(!darkMode),
          toggle: true,
          active: darkMode,
        },
      ],
    },
    {
      title: "Notifications",
      items: [
        {
          label: "Enable Notifications",
          description: "Receive alerts for task completions",
          icon: Bell,
          action: () => setNotifications(!notifications),
          toggle: true,
          active: notifications,
        },
      ],
    },
    {
      title: "Security",
      items: [
        {
          label: "Change Password",
          description: "Update your account password",
          icon: Lock,
          action: () => {},
          href: "/settings/password",
        },
      ],
    },
    {
      title: "Help & Support",
      items: [
        {
          label: "Documentation",
          description: "View usage guides and tutorials",
          icon: HelpCircle,
          action: () => window.open("https://docs.example.com", "_blank"),
        },
      ],
    },
    {
      title: "Account",
      items: [
        {
          label: "Sign Out",
          description: "Log out of CoComputer",
          icon: LogOut,
          action: () => {},
          danger: true,
        },
      ],
    },
  ];

  return (
    <div className="flex-1 overflow-y-auto bg-[#16181a]">
      <div className="max-w-2xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-zinc-100">Settings</h1>
          <p className="text-sm text-zinc-400 mt-1">Manage your CoComputer preferences</p>
        </div>

        {/* Settings Sections */}
        <div className="space-y-6">
          {settingsSections.map((section, idx) => (
            <div key={idx}>
              {/* Section Title */}
              <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-3 px-4">
                {section.title}
              </h2>

              {/* Section Items */}
              <div className="space-y-1 divide-y divide-zinc-800">
                {section.items.map((item, itemIdx) => {
                  const Icon = item.icon;
                  return (
                    <button
                      key={itemIdx}
                      onClick={item.action}
                      className={`w-full flex items-center justify-between px-4 py-3 rounded-lg transition-colors ${
                        item.danger
                          ? "hover:bg-red-950/30 text-red-400 hover:text-red-300"
                          : "hover:bg-zinc-800/50 text-zinc-300"
                      }`}
                    >
                      <div className="flex items-center gap-3 text-left">
                        <Icon className="w-5 h-5 text-zinc-500" />
                        <div>
                          <p className="text-sm font-medium text-zinc-200">{item.label}</p>
                          <p className="text-xs text-zinc-500 mt-0.5">{item.description}</p>
                        </div>
                      </div>

                      {/* Toggle or Chevron */}
                      {item.toggle ? (
                        <div
                          className={`w-10 h-6 rounded-full transition-colors relative ${
                            item.active ? "bg-indigo-500" : "bg-zinc-700"
                          }`}
                        >
                          <div
                            className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
                              item.active ? "translate-x-4.5" : "translate-x-0.5"
                            }`}
                          />
                        </div>
                      ) : (
                        <ChevronRight className="w-5 h-5 text-zinc-600" />
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        {/* Footer Info */}
        <div className="mt-12 pt-6 border-t border-zinc-800/50">
          <div className="text-xs text-zinc-500 space-y-1">
            <p>CoComputer v1.0.0</p>
            <p className="mt-2">
              © 2026 CoComputer. All rights reserved.{" "}
              <a href="#" className="text-indigo-400 hover:text-indigo-300">
                Privacy Policy
              </a>{" "}
              ·{" "}
              <a href="#" className="text-indigo-400 hover:text-indigo-300">
                Terms of Service
              </a>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
