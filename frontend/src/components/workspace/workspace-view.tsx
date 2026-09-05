/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Bell,
  Search,
  ExternalLink,
  Sparkles,
  ArrowRight,
  X,
  Radio,
} from "lucide-react";

import { SearchModal } from "@/components/search-modal";
import {
  useCalendarEventsQuery,
  useIntegrationsConnectionsQuery,
  type CalendarEvent,
} from "@/lib/queries/integrations";
import { useDashboardSessionsQuery } from "@/lib/queries/dashboard";
import { sessionPath, APP_CONNECTORS, APP_DASHBOARD } from "@/lib/app-paths";
import { useSession } from "@/lib/use-session";

interface IntegrationApp {
  id: string;
  name: string;
  category: string;
  image: string;
  provider: string;
  connectorType: string;
  description: string;
  quickPrompts: string[];
}

const APPS: IntegrationApp[] = [
  {
    id: "calendar",
    name: "Calendar",
    category: "Google Calendar",
    image: "https://www.gstatic.com/images/branding/product/2x/calendar_2020q4_48dp.png",
    provider: "google_calendar",
    connectorType: "calendar",
    description: "Automate calendar bookings, find conflict-free meeting slots, and prepare daily agendas.",
    quickPrompts: [
      "What are my scheduled meetings today?",
      "Find free slots tomorrow afternoon for a design review",
      "Schedule a 30m sync with the team this Friday",
    ],
  },
  {
    id: "mail",
    name: "Mail",
    category: "Google Mail",
    image: "https://www.gstatic.com/images/branding/product/2x/gmail_2020q4_48dp.png",
    provider: "gmail",
    connectorType: "gmail",
    description: "Scan inbox for urgent action items, triage unread threads, and draft contextual replies.",
    quickPrompts: [
      "Summarize unread urgent emails from the last 24h",
      "Draft a follow-up response to the client proposal",
      "Find recent invoices sent to my inbox",
    ],
  },
  {
    id: "slack",
    name: "Slack",
    category: "Team Messaging",
    image: "/connectors/slack.svg",
    provider: "slack",
    connectorType: "slack",
    description: "Monitor active channels, triage mentions, and post automated progress updates.",
    quickPrompts: [
      "Check recent mentions and action items on #general",
      "Summarize yesterday's announcements in the dev channel",
      "Post a release note summary to Slack",
    ],
  },
  {
    id: "payments",
    name: "Payments",
    category: "Stripe Billing",
    image: "/connectors/stripe.svg",
    provider: "stripe",
    connectorType: "stripe",
    description: "Track MRR, inspect failed invoices, analyze checkout conversions, and alert on refunds.",
    quickPrompts: [
      "Show MRR growth and net revenue this month",
      "List failed recurring payments that need retry",
      "Summarize total transactions over the last 7 days",
    ],
  },
  {
    id: "tasks",
    name: "Tasks",
    category: "Linear Issues",
    image: "/connectors/linear.svg",
    provider: "linear",
    connectorType: "linear",
    description: "Sync with Linear and GitHub issues, auto-triage incoming bugs, and manage sprints.",
    quickPrompts: [
      "Show all high-priority tasks assigned to me in the current sprint",
      "Create a new Linear issue: 'Fix horizontal table scroll in chat'",
      "Summarize blocker issues across all active projects",
    ],
  },
  {
    id: "insights",
    name: "Insights",
    category: "Agent Telemetry",
    image: "/connectors/insights.svg",
    provider: "system",
    connectorType: "insights",
    description: "Monitor autonomous agent execution velocity, token budgets, and tool invocations.",
    quickPrompts: [
      "Show agent usage breakdown by task type this week",
      "What were the most frequent tool calls executed today?",
      "Analyze session completion rates and latency",
    ],
  },
];

function formatTimeAgo(dateStr: string | null | undefined): string {
  if (!dateStr) return "recently";
  const date = new Date(dateStr);
  const now = new Date();
  const diffSec = Math.floor((now.getTime() - date.getTime()) / 1000);
  if (diffSec < 60) return "just now";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}h ago`;
  const diffDays = Math.floor(diffHour / 24);
  if (diffDays === 1) return "yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

function formatEventWhen(start: string | null | undefined): string {
  if (!start) return "No time set";
  const date = new Date(start);
  if (Number.isNaN(date.getTime())) return start;
  if (!start.includes("T")) {
    return date.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
  }
  return date.toLocaleString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

const CALENDAR_ICON =
  "https://www.gstatic.com/images/branding/product/2x/calendar_2020q4_48dp.png";

function CalendarEventRow({
  event,
  onOpen,
}: {
  event: CalendarEvent;
  onOpen?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={() => {
        if (event.htmlLink) {
          window.open(event.htmlLink, "_blank", "noopener,noreferrer");
          return;
        }
        onOpen?.();
      }}
      className="group flex w-full items-center justify-between rounded-xl border border-zinc-800/60 bg-[#101012] p-2.5 text-left transition-colors hover:border-zinc-700 hover:bg-zinc-800/40"
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={CALENDAR_ICON} alt="" className="size-4 object-contain" />
          <span className="truncate text-xs font-medium text-zinc-200">
            {event.summary || "Untitled event"}
          </span>
        </div>
        <p className="mt-1 text-[11.5px] text-zinc-400">{formatEventWhen(event.start)}</p>
      </div>
      <ArrowRight className="size-3.5 shrink-0 text-zinc-600 group-hover:text-zinc-300" />
    </button>
  );
}

export function WorkspaceView() {
  const router = useRouter();
  const { createSession } = useSession();
  const connectionsQuery = useIntegrationsConnectionsQuery();
  const sessionsQuery = useDashboardSessionsQuery(10);

  const [searchOpen, setSearchOpen] = useState(false);
  const [selectedApp, setSelectedApp] = useState<IntegrationApp | null>(null);
  const [notificationsOpen, setNotificationsOpen] = useState(false);

  const connections = useMemo(() => connectionsQuery.data ?? [], [connectionsQuery.data]);
  const recentSessions = useMemo(() => sessionsQuery.data ?? [], [sessionsQuery.data]);
  const calendarConnected = useMemo(
    () =>
      connections.some(
        (c) => c.provider === "google_calendar" && c.enabled && c.status === "connected",
      ),
    [connections],
  );
  const eventsQuery = useCalendarEventsQuery(calendarConnected);
  const upcomingEvents = useMemo(() => eventsQuery.data ?? [], [eventsQuery.data]);
  const eventsError =
    eventsQuery.error instanceof Error ? eventsQuery.error.message : null;

  const connectedCount = useMemo(
    () => connections.filter((c) => c.enabled && c.status === "connected").length,
    [connections],
  );

  const handleLaunchPrompt = async (prompt: string) => {
    try {
      const session = await createSession({ mode: "fresh" });
      if (session?.session_id) {
        router.push(sessionPath(session.session_id, { prompt }));
      }
    } catch {
      router.push(`/app?prompt=${encodeURIComponent(prompt)}`);
    }
  };

  return (
    <div className="relative min-h-screen w-full bg-[#08080a] text-zinc-100 selection:bg-indigo-500/30">
      {/* Main Container */}
      <div className="relative mx-auto flex min-h-screen max-w-5xl flex-col px-6 py-10 md:px-10 md:py-14">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <h1 className="font-serif text-4xl font-normal tracking-tight text-white md:text-[44px]">
              Workspace
            </h1>
            <div className="mt-2 flex items-center gap-2 text-[14px] text-zinc-400">
              <span className="relative flex size-2">
                {connectedCount > 0 ? (
                  <>
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
                  </>
                ) : (
                  <span className="relative inline-flex size-2 rounded-full bg-zinc-600" />
                )}
              </span>
              <span>
                {connectedCount > 0 ? (
                  <>
                    Your agent is monitoring{" "}
                    <span className="font-medium text-zinc-200">
                      {connectedCount} integration{connectedCount === 1 ? "" : "s"}
                    </span>
                  </>
                ) : (
                  "No integrations connected yet"
                )}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            {/* Search Pill */}
            <button
              type="button"
              aria-label="Search Workspace"
              onClick={() => setSearchOpen(true)}
              className="flex items-center gap-2 rounded-full border border-zinc-800/80 bg-[#121215] px-3.5 py-2 text-xs text-zinc-400 shadow-sm transition-all hover:border-zinc-700 hover:bg-zinc-800/60 hover:text-white"
            >
              <Search className="size-3.5" />
              <span className="hidden sm:inline">Search integrations</span>
              <kbd className="hidden rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[10px] text-zinc-400 sm:inline">
                ⌘K
              </kbd>
            </button>

            {/* Notification Bell */}
            <div className="relative">
              <button
                type="button"
                aria-label="Notifications"
                onClick={() => setNotificationsOpen((prev) => !prev)}
                className="relative flex size-9 items-center justify-center rounded-full border border-zinc-800/80 bg-[#121215] text-zinc-400 shadow-sm transition-all hover:border-zinc-700 hover:bg-zinc-800/60 hover:text-white"
              >
                <Bell className="size-4" />
                {upcomingEvents.length > 0 && (
                  <span className="absolute right-2 top-2 size-2 rounded-full bg-rose-500 ring-2 ring-[#121215]" />
                )}
              </button>

              {/* Notifications Dropdown */}
              <AnimatePresence>
                {notificationsOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: 8, scale: 0.96 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 6, scale: 0.96 }}
                    transition={{ duration: 0.15 }}
                    className="absolute right-0 top-11 z-50 w-80 overflow-hidden rounded-2xl border border-zinc-800 bg-[#151518] p-3 shadow-2xl backdrop-blur-xl"
                  >
                    <div className="flex items-center justify-between border-b border-zinc-800/80 px-2 pb-2">
                      <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
                        Upcoming events
                      </span>
                      {calendarConnected && (
                        <span className="flex items-center gap-1 font-mono text-[11px] font-medium text-emerald-400">
                          <Radio className="size-3 animate-pulse" /> Live
                        </span>
                      )}
                    </div>

                    <div className="mt-2 flex flex-col gap-2">
                      {!calendarConnected ? (
                        <p className="px-2 py-3 text-[12px] text-zinc-400">
                          Connect Google Calendar in Connectors to see upcoming events.
                        </p>
                      ) : eventsQuery.isLoading ? (
                        <p className="px-2 py-3 text-[12px] text-zinc-500">Loading events…</p>
                      ) : eventsError ? (
                        <p className="px-2 py-3 text-[12px] text-rose-300">{eventsError}</p>
                      ) : upcomingEvents.length > 0 ? (
                        upcomingEvents.slice(0, 5).map((event) => (
                          <CalendarEventRow key={event.id || event.summary} event={event} />
                        ))
                      ) : (
                        <p className="px-2 py-3 text-[12px] text-zinc-400">No upcoming events.</p>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>

        {/* Squircle Apps Launchpad with Real Product Images and Clean Neutral Borders */}
        <div className="mt-14 grid grid-cols-3 gap-8 sm:grid-cols-4 md:grid-cols-6 lg:gap-10">
          {APPS.map((app) => {
            const isConnected = connections.some(
              (c) => c.provider === app.provider && c.enabled && c.status === "connected",
            );

            return (
              <motion.button
                key={app.id}
                type="button"
                whileHover={{ scale: 1.05, y: -3 }}
                whileTap={{ scale: 0.96 }}
                onClick={() => setSelectedApp(app)}
                className="group relative flex flex-col items-center gap-2.5 outline-none"
              >
                {/* Clean Neutral Squircle Icon Frame */}
                <div className="relative flex size-20 items-center justify-center rounded-[22px] border border-zinc-800 bg-[#141417] p-3.5 shadow-sm transition-all duration-200 group-hover:border-zinc-700 group-hover:bg-[#1a1a1f] group-hover:shadow-md md:size-22">
                  {/* Real Product Image */}
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={app.image}
                    alt={app.name}
                    className="size-9 object-contain select-none transition-transform duration-200 group-hover:scale-105 md:size-10"
                  />

                  {/* Connected Status Beacon */}
                  <span
                    className="absolute -right-1 -top-1 flex size-3.5 items-center justify-center rounded-full bg-[#08080a] ring-2 ring-[#08080a]"
                    title={isConnected ? "Connected" : "Not connected"}
                  >
                    <span
                      className={`size-2 rounded-full ${isConnected ? "bg-emerald-400" : "bg-zinc-600"}`}
                    />
                  </span>
                </div>

                {/* App Name */}
                <span className="text-[13px] font-medium text-zinc-300 transition-colors group-hover:text-white">
                  {app.name}
                </span>
              </motion.button>
            );
          })}
        </div>

        {/* Spacer */}
        <div className="flex-1 min-h-[120px]" />

        {/* Bottom Section: RECENT AGENT ACTIVITY */}
        <div className="w-full rounded-2xl border border-zinc-800/80 bg-[#121215]/90 p-6 shadow-sm">
          <div className="flex items-center justify-between pb-4">
            <span className="text-[11px] font-semibold uppercase tracking-[0.2em] text-zinc-400">
              Recent Agent Activity
            </span>
            <button
              type="button"
              onClick={() => router.push(APP_DASHBOARD)}
              className="flex items-center gap-1 text-[11px] font-medium text-zinc-400 hover:text-zinc-200"
            >
              <span>View All</span>
              <ArrowRight className="size-3" />
            </button>
          </div>

          <div className="flex flex-col divide-y divide-zinc-800/60">
            {recentSessions.length > 0 ? (
              recentSessions.slice(0, 3).map((session, idx) => (
                <div
                  key={session.session_id || idx}
                  onClick={() => router.push(sessionPath(session.session_id))}
                  className="group flex cursor-pointer items-center justify-between py-3.5 transition-colors hover:bg-zinc-800/20"
                >
                  <div className="flex items-center gap-3.5">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-xl border border-zinc-800 bg-[#16161a] shadow-sm">
                      <Sparkles className="size-4 text-zinc-400" />
                    </span>
                    <div>
                      <h4 className="text-[13.5px] font-semibold text-zinc-100 group-hover:text-white">
                        {session.title || "Autonomous Task Execution"}
                      </h4>
                      <p className="text-[12px] text-zinc-400">
                        {session.status === "active" ? "Active agent session" : "Completed workflow"} • {session.message_count} messages
                      </p>
                    </div>
                  </div>
                  <span className="font-mono text-[11px] text-zinc-500">
                    {formatTimeAgo(session.created_at)}
                  </span>
                </div>
              ))
            ) : upcomingEvents.length > 0 ? (
              upcomingEvents.slice(0, 3).map((event) => (
                <div
                  key={event.id || event.summary}
                  onClick={() => {
                    if (event.htmlLink) {
                      window.open(event.htmlLink, "_blank", "noopener,noreferrer");
                    }
                  }}
                  className="group flex cursor-pointer items-center justify-between py-3.5 transition-colors hover:bg-zinc-800/20"
                >
                  <div className="flex items-center gap-3.5">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-xl border border-zinc-800 bg-[#16161a] p-1.5 shadow-sm">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={CALENDAR_ICON} alt="Calendar" className="size-5 object-contain" />
                    </span>
                    <div>
                      <h4 className="text-[13.5px] font-semibold text-zinc-100 group-hover:text-white">
                        {event.summary || "Untitled event"}
                      </h4>
                      <p className="text-[12px] text-zinc-400">{formatEventWhen(event.start)}</p>
                    </div>
                  </div>
                  <span className="font-mono text-[11px] text-zinc-500">Upcoming</span>
                </div>
              ))
            ) : (
              <p className="py-6 text-center text-[13px] text-zinc-500">No recent activity.</p>
            )}
          </div>
        </div>
      </div>

      {/* Integration Detail Modal */}
      <AnimatePresence>
        {selectedApp && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-md">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative w-full max-w-lg overflow-hidden rounded-3xl border border-zinc-800 bg-[#141418] p-6 shadow-2xl"
            >
              {/* Close Button */}
              <button
                type="button"
                onClick={() => setSelectedApp(null)}
                className="absolute right-5 top-5 flex size-8 items-center justify-center rounded-full bg-zinc-800/80 text-zinc-400 hover:bg-zinc-700 hover:text-white"
              >
                <X className="size-4" />
              </button>

              {/* Modal Header */}
              <div className="flex items-center gap-4">
                <div className="flex size-14 items-center justify-center rounded-2xl border border-zinc-800 bg-[#1a1a1f] p-3 shadow-sm">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={selectedApp.image} alt={selectedApp.name} className="size-8 object-contain" />
                </div>
                <div>
                  <h3 className="text-xl font-bold text-white">{selectedApp.name}</h3>
                  <span className="text-xs font-medium text-zinc-400">{selectedApp.category}</span>
                </div>
              </div>

              <p className="mt-4 text-[13.5px] leading-relaxed text-zinc-300">
                {selectedApp.description}
              </p>

              {selectedApp.id === "calendar" && (
                <div className="mt-5">
                  <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
                    Upcoming events
                  </span>
                  <div className="mt-2.5 flex flex-col gap-2">
                    {!calendarConnected ? (
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedApp(null);
                          router.push(APP_CONNECTORS);
                        }}
                        className="rounded-xl border border-zinc-800 bg-[#0e0e11] p-3 text-left text-xs font-medium text-zinc-300 hover:border-zinc-700 hover:text-white"
                      >
                        Connect Google Calendar in Connectors
                      </button>
                    ) : eventsQuery.isLoading ? (
                      <p className="text-[12px] text-zinc-500">Loading events…</p>
                    ) : eventsError ? (
                      <p className="text-[12px] text-rose-300">{eventsError}</p>
                    ) : upcomingEvents.length > 0 ? (
                      upcomingEvents.slice(0, 5).map((event) => (
                        <CalendarEventRow key={event.id || event.summary} event={event} />
                      ))
                    ) : (
                      <p className="text-[12px] text-zinc-400">No upcoming events.</p>
                    )}
                  </div>
                </div>
              )}

              {/* Quick Actions / Prompts */}
              <div className="mt-5">
                <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
                  Quick Agent Actions
                </span>
                <div className="mt-2.5 flex flex-col gap-2">
                  {selectedApp.quickPrompts.map((prompt, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => handleLaunchPrompt(prompt)}
                      className="group/btn flex items-center justify-between rounded-xl border border-zinc-800/70 bg-[#0e0e11] p-3 text-left transition-colors hover:border-zinc-700 hover:bg-zinc-800/50"
                    >
                      <span className="text-xs font-medium text-zinc-300 group-hover/btn:text-white">
                        {prompt}
                      </span>
                      <ArrowRight className="size-3.5 text-zinc-500 group-hover/btn:translate-x-0.5 group-hover/btn:text-zinc-200 transition-all" />
                    </button>
                  ))}
                </div>
              </div>

              {/* Footer Actions */}
              <div className="mt-6 flex items-center justify-between border-t border-zinc-800/80 pt-4">
                <button
                  type="button"
                  onClick={() => {
                    setSelectedApp(null);
                    router.push(APP_CONNECTORS);
                  }}
                  className="flex items-center gap-1.5 text-xs font-medium text-zinc-400 hover:text-zinc-200"
                >
                  <ExternalLink className="size-3.5" />
                  <span>
                    {selectedApp.id === "calendar" && !calendarConnected
                      ? "Connect Google Calendar"
                      : "Configure Integration"}
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    const prompt = `Open ${selectedApp.name} and check my active status.`;
                    setSelectedApp(null);
                    handleLaunchPrompt(prompt);
                  }}
                  className="flex items-center gap-1.5 rounded-xl bg-zinc-800 border border-zinc-700 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-zinc-700 transition-colors"
                >
                  <Sparkles className="size-3.5" />
                  <span>Ask Agent</span>
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Global Search Modal */}
      <SearchModal isOpen={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  );
}
