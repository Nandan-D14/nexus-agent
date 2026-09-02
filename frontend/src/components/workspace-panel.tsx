"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChevronLeft,
  ChevronRight,
  Plus,
  Search,
  Bell,
  Radio,
  ArrowRight,
  ExternalLink,
} from "lucide-react";

import { SearchModal } from "@/components/search-modal";
import {
  buildMonthCells,
  eventDateKey,
  formatEventWhen,
  formatTimeAgo,
  monthUtcBounds,
} from "@/components/workspace/calendar-helpers";
import { APP_CONNECTORS, APP_DASHBOARD, sessionPath } from "@/lib/app-paths";
import {
  useCalendarEventsQuery,
  useIntegrationsConnectionsQuery,
  type CalendarEvent,
} from "@/lib/queries/integrations";
import { useDashboardSessionsQuery } from "@/lib/queries/dashboard";

type AppName = "calendar" | "gmail" | "slack" | "payments" | "tasks" | "insights" | null;

interface AppConfig {
  id: Exclude<AppName, null>;
  name: string;
  image: string;
  description: string;
  provider: string;
  href?: string;
}

const APPS: AppConfig[] = [
  {
    id: "calendar",
    name: "Calendar",
    image: "https://www.gstatic.com/images/branding/product/2x/calendar_2020q4_48dp.png",
    description: "Manage events and daily agendas.",
    provider: "google_calendar",
    href: "https://calendar.google.com",
  },
  {
    id: "gmail",
    name: "Mail",
    image: "https://www.gstatic.com/images/branding/product/2x/gmail_2020q4_48dp.png",
    description: "Triage inbox, scan urgent threads, and draft replies.",
    provider: "gmail",
    href: "https://mail.google.com",
  },
  {
    id: "slack",
    name: "Slack",
    image: "/connectors/slack.svg",
    description: "Monitor channels, mentions, and automate updates.",
    provider: "slack",
    href: "https://app.slack.com",
  },
  {
    id: "payments",
    name: "Payments",
    image: "/connectors/stripe.svg",
    description: "Track revenue, transactions, and invoice status.",
    provider: "stripe",
    href: "https://dashboard.stripe.com",
  },
  {
    id: "tasks",
    name: "Tasks",
    image: "/connectors/linear.svg",
    description: "Manage Linear issues, sprint backlogs, and bug tickets.",
    provider: "linear",
    href: "https://linear.app",
  },
  {
    id: "insights",
    name: "Insights",
    image: "/connectors/insights.svg",
    description: "Monitor agent telemetry, execution metrics, and latency.",
    provider: "system",
  },
];

const CALENDAR_ICON =
  "https://www.gstatic.com/images/branding/product/2x/calendar_2020q4_48dp.png";
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function queryErrorMessage(error: unknown): string | null {
  return error instanceof Error ? error.message : null;
}

function LiveCalendar({
  connected,
  events,
  loading,
  error,
  year,
  month,
  onPrevMonth,
  onNextMonth,
  onToday,
  onConnect,
}: {
  connected: boolean;
  events: CalendarEvent[];
  loading: boolean;
  error: string | null;
  year: number;
  month: number;
  onPrevMonth: () => void;
  onNextMonth: () => void;
  onToday: () => void;
  onConnect: () => void;
}) {
  const cells = useMemo(() => buildMonthCells(year, month), [year, month]);
  const eventsByDay = useMemo(() => {
    const grouped = new Map<string, CalendarEvent[]>();
    for (const event of events) {
      const key = eventDateKey(event.start);
      if (!key) continue;
      const list = grouped.get(key) ?? [];
      list.push(event);
      grouped.set(key, list);
    }
    return grouped;
  }, [events]);
  const monthLabel = new Date(year, month, 1).toLocaleDateString([], {
    month: "long",
    year: "numeric",
  });

  return (
    <div className="flex h-full flex-col bg-[#09090b]">
      <div className="flex items-center justify-between border-b border-zinc-800/80 bg-[#121215]/80 p-4 backdrop-blur-xl">
        <div className="flex items-center gap-4">
          <h2 className="text-lg font-semibold tracking-tight text-zinc-100">{monthLabel}</h2>
          <div className="flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-900/80 p-1">
            <button
              type="button"
              onClick={onPrevMonth}
              className="rounded-md p-1 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
            >
              <ChevronLeft className="size-4" />
            </button>
            <button
              type="button"
              onClick={onToday}
              className="px-2.5 py-1 text-xs font-medium text-zinc-300 transition-colors hover:text-zinc-100"
            >
              Today
            </button>
            <button
              type="button"
              onClick={onNextMonth}
              className="rounded-md p-1 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
            >
              <ChevronRight className="size-4" />
            </button>
          </div>
        </div>
        <button
          type="button"
          onClick={() => {
            if (!connected) {
              onConnect();
              return;
            }
            window.open(
              "https://calendar.google.com/calendar/u/0/r/eventedit",
              "_blank",
              "noopener,noreferrer",
            );
          }}
          className="flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition-all hover:bg-zinc-700"
        >
          <Plus className="size-3.5" /> Add Event
        </button>
      </div>
      <div className="flex-1 overflow-auto bg-[#09090b] p-4">
        {!connected ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 rounded-2xl border border-zinc-800/80 bg-[#121215] px-6 text-center">
            <p className="text-sm font-medium text-zinc-200">Google Calendar is not connected</p>
            <p className="max-w-sm text-xs text-zinc-400">
              Connect Google in Connectors and grant Calendar access to see your real events here.
            </p>
            <button
              type="button"
              onClick={onConnect}
              className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-700"
            >
              Open Connectors
            </button>
          </div>
        ) : (
          <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-zinc-800/80 bg-[#121215] shadow-sm">
            {error ? (
              <div className="border-b border-rose-500/20 bg-rose-500/10 px-4 py-2 text-xs text-rose-300">
                {error}
              </div>
            ) : null}
            {loading ? (
              <div className="border-b border-zinc-800 px-4 py-2 text-[11px] text-zinc-500">
                Loading events…
              </div>
            ) : null}
            <div className="grid grid-cols-7 border-b border-zinc-800/80 bg-[#16161a]">
              {WEEKDAYS.map((day) => (
                <div
                  key={day}
                  className="p-2.5 text-center text-[10px] font-bold uppercase tracking-widest text-zinc-500"
                >
                  {day}
                </div>
              ))}
            </div>
            <div className="grid flex-1 grid-cols-7 grid-rows-6 gap-px bg-zinc-800/40">
              {cells.map((cell) => {
                const dayEvents = eventsByDay.get(cell.key) ?? [];
                return (
                  <div
                    key={cell.key}
                    className={`relative bg-[#121215] p-2 transition-colors hover:bg-[#16161a] ${
                      cell.inMonth ? "" : "opacity-40"
                    }`}
                  >
                    <div
                      className={`mb-1 flex size-6 items-center justify-center rounded-full text-xs font-semibold ${
                        cell.isToday
                          ? "bg-blue-600 text-white shadow-sm"
                          : "text-zinc-500 group-hover:text-zinc-300"
                      }`}
                    >
                      {cell.date.getDate()}
                    </div>
                    <div className="space-y-1">
                      {dayEvents.slice(0, 2).map((event) => (
                        <button
                          key={event.id || `${cell.key}-${event.summary}`}
                          type="button"
                          title={event.summary || "Untitled event"}
                          onClick={() => {
                            if (event.htmlLink) {
                              window.open(event.htmlLink, "_blank", "noopener,noreferrer");
                            }
                          }}
                          className="flex w-full cursor-pointer items-center gap-1 truncate rounded border border-blue-500/20 bg-blue-500/10 px-1.5 py-0.5 text-left text-[9px] font-medium text-blue-400"
                        >
                          <span className="size-1 shrink-0 rounded-full bg-blue-500" />
                          <span className="truncate">{event.summary || "Untitled event"}</span>
                        </button>
                      ))}
                      {dayEvents.length > 2 ? (
                        <div className="px-1 text-[9px] text-zinc-500">+{dayEvents.length - 2} more</div>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function AppDetail({
  app,
  connected,
  onConnect,
}: {
  app: AppConfig;
  connected: boolean;
  onConnect: () => void;
}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center bg-[#09090b] p-8">
      <div className="space-y-5 text-center">
        <div className="mx-auto flex size-20 items-center justify-center rounded-2xl border border-zinc-800 bg-[#141417] p-4 shadow-lg">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={app.image} alt={app.name} className="size-12 object-contain" />
        </div>
        <div>
          <h2 className="mb-1.5 text-xl font-semibold text-white">{app.name}</h2>
          <p className="mx-auto max-w-xs text-xs leading-relaxed text-zinc-400">{app.description}</p>
        </div>
        <p className="text-xs font-medium text-zinc-300">
          {connected ? "Connected" : "Not connected"}
        </p>
        <div className="flex items-center justify-center gap-2">
          <button
            type="button"
            onClick={onConnect}
            className="flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-700"
          >
            <ExternalLink className="size-3.5" />
            {connected ? "Manage in Connectors" : "Connect in Connectors"}
          </button>
          {connected && app.href ? (
            <button
              type="button"
              onClick={() => window.open(app.href, "_blank", "noopener,noreferrer")}
              className="rounded-lg border border-zinc-800 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:border-zinc-700 hover:text-white"
            >
              Open {app.name}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function WorkspacePanel() {
  const router = useRouter();
  const [activeApp, setActiveApp] = useState<AppName>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const now = new Date();
  const [visibleMonth, setVisibleMonth] = useState({ year: now.getFullYear(), month: now.getMonth() });

  const connectionsQuery = useIntegrationsConnectionsQuery();
  const sessionsQuery = useDashboardSessionsQuery(10);
  const connections = useMemo(() => connectionsQuery.data ?? [], [connectionsQuery.data]);
  const recentSessions = useMemo(() => sessionsQuery.data ?? [], [sessionsQuery.data]);

  const isConnected = (provider: string) =>
    provider === "system" ||
    connections.some((c) => c.provider === provider && c.enabled && c.status === "connected");

  const calendarConnected = isConnected("google_calendar");
  const connectedCount = connections.filter((c) => c.enabled && c.status === "connected").length;
  const monthRange = monthUtcBounds(visibleMonth.year, visibleMonth.month);

  const upcomingQuery = useCalendarEventsQuery(calendarConnected, { maxResults: 10 });
  const monthQuery = useCalendarEventsQuery(calendarConnected && activeApp === "calendar", {
    maxResults: 50,
    timeMin: monthRange.timeMin,
    timeMax: monthRange.timeMax,
  });

  const upcomingEvents = upcomingQuery.data ?? [];
  const monthEvents = monthQuery.data ?? [];
  const upcomingError = queryErrorMessage(upcomingQuery.error);
  const monthError = queryErrorMessage(monthQuery.error);

  const goConnectors = () => router.push(APP_CONNECTORS);

  const renderAppContent = () => {
    if (activeApp === "calendar") {
      return (
        <LiveCalendar
          connected={calendarConnected}
          events={monthEvents}
          loading={monthQuery.isLoading}
          error={monthError}
          year={visibleMonth.year}
          month={visibleMonth.month}
          onPrevMonth={() =>
            setVisibleMonth((current) => {
              const date = new Date(current.year, current.month - 1, 1);
              return { year: date.getFullYear(), month: date.getMonth() };
            })
          }
          onNextMonth={() =>
            setVisibleMonth((current) => {
              const date = new Date(current.year, current.month + 1, 1);
              return { year: date.getFullYear(), month: date.getMonth() };
            })
          }
          onToday={() => {
            const today = new Date();
            setVisibleMonth({ year: today.getFullYear(), month: today.getMonth() });
          }}
          onConnect={goConnectors}
        />
      );
    }
    const app = APPS.find((item) => item.id === activeApp);
    return app ? (
      <AppDetail app={app} connected={isConnected(app.provider)} onConnect={goConnectors} />
    ) : null;
  };

  return (
    <div className="relative flex h-full flex-col overflow-hidden bg-[#09090b] font-sans text-zinc-100">
      <AnimatePresence mode="wait">
        {!activeApp ? (
          <motion.div
            key="home"
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 1.02 }}
            transition={{ duration: 0.2, ease: "easeInOut" }}
            className="relative flex flex-1 flex-col p-6 md:p-8"
          >
            <div className="relative z-10 mb-10 flex items-start justify-between">
              <div>
                <h1 className="mb-1.5 font-serif text-[32px] leading-tight tracking-tight text-white">
                  Workspace
                </h1>
                <div className="flex items-center gap-2 text-[13px] text-zinc-400">
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

              <div className="flex gap-2">
                <button
                  type="button"
                  aria-label="Search integrations"
                  onClick={() => setSearchOpen(true)}
                  className="flex items-center gap-2 rounded-full border border-zinc-800 bg-[#121215] px-3 py-1.5 text-xs text-zinc-400 shadow-sm transition-colors hover:border-zinc-700 hover:text-white"
                >
                  <Search className="size-3.5" />
                  <span className="hidden sm:inline">Search...</span>
                  <kbd className="hidden rounded bg-zinc-800 px-1 font-mono text-[10px] text-zinc-500 sm:inline">
                    ⌘K
                  </kbd>
                </button>
                <div className="relative">
                  <button
                    type="button"
                    aria-label="Notifications"
                    onClick={() => setNotificationsOpen((open) => !open)}
                    className="relative flex size-8 items-center justify-center rounded-full border border-zinc-800 bg-[#121215] text-zinc-400 shadow-sm transition-colors hover:border-zinc-700 hover:text-white"
                  >
                    <Bell className="size-3.5" />
                    {upcomingEvents.length > 0 ? (
                      <span className="absolute right-1.5 top-1.5 size-1.5 rounded-full bg-rose-500 ring-2 ring-[#121215]" />
                    ) : null}
                  </button>
                  <AnimatePresence>
                    {notificationsOpen ? (
                      <motion.div
                        initial={{ opacity: 0, y: 8, scale: 0.96 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: 6, scale: 0.96 }}
                        transition={{ duration: 0.15 }}
                        className="absolute right-0 top-10 z-50 w-80 overflow-hidden rounded-2xl border border-zinc-800 bg-[#151518] p-3 shadow-2xl"
                      >
                        <div className="flex items-center justify-between border-b border-zinc-800/80 px-2 pb-2">
                          <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
                            Upcoming events
                          </span>
                          {calendarConnected ? (
                            <span className="flex items-center gap-1 font-mono text-[11px] font-medium text-emerald-400">
                              <Radio className="size-3 animate-pulse" /> Live
                            </span>
                          ) : null}
                        </div>
                        <div className="mt-2 flex flex-col gap-2">
                          {!calendarConnected ? (
                            <button
                              type="button"
                              onClick={goConnectors}
                              className="px-2 py-3 text-left text-[12px] text-zinc-400 hover:text-zinc-200"
                            >
                              Connect Google Calendar in Connectors to see upcoming events.
                            </button>
                          ) : upcomingQuery.isLoading ? (
                            <p className="px-2 py-3 text-[12px] text-zinc-500">Loading events…</p>
                          ) : upcomingError ? (
                            <p className="px-2 py-3 text-[12px] text-rose-300">{upcomingError}</p>
                          ) : upcomingEvents.length > 0 ? (
                            upcomingEvents.slice(0, 5).map((event) => (
                              <button
                                key={event.id || event.summary}
                                type="button"
                                onClick={() => {
                                  if (event.htmlLink) {
                                    window.open(event.htmlLink, "_blank", "noopener,noreferrer");
                                  }
                                }}
                                className="rounded-xl border border-zinc-800/60 bg-[#101012] p-2.5 text-left hover:border-zinc-700"
                              >
                                <p className="truncate text-xs font-medium text-zinc-200">
                                  {event.summary || "Untitled event"}
                                </p>
                                <p className="mt-1 text-[11.5px] text-zinc-400">
                                  {formatEventWhen(event.start)}
                                </p>
                              </button>
                            ))
                          ) : (
                            <p className="px-2 py-3 text-[12px] text-zinc-400">No upcoming events.</p>
                          )}
                        </div>
                      </motion.div>
                    ) : null}
                  </AnimatePresence>
                </div>
              </div>
            </div>

            <div className="relative z-10 grid grid-cols-3 gap-x-5 gap-y-7 sm:grid-cols-4 md:grid-cols-6">
              {APPS.map((app) => {
                const connected = isConnected(app.provider);
                return (
                  <button
                    key={app.id}
                    type="button"
                    onClick={() => setActiveApp(app.id)}
                    className="group relative flex flex-col items-center gap-2 outline-none"
                  >
                    <div className="relative flex size-[68px] items-center justify-center rounded-[20px] border border-zinc-800 bg-[#141417] p-3.5 shadow-sm transition-all duration-200 group-hover:scale-105 group-hover:border-zinc-700 group-hover:bg-[#1a1a1f] group-hover:shadow-md">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={app.image}
                        alt={app.name}
                        className="size-8 object-contain select-none transition-transform duration-200 group-hover:scale-105"
                      />
                      <span
                        className="absolute -right-0.5 -top-0.5 flex size-3 items-center justify-center rounded-full bg-[#09090b] ring-2 ring-[#09090b]"
                        title={connected ? "Connected" : "Not connected"}
                      >
                        <span
                          className={`size-1.5 rounded-full ${connected ? "bg-emerald-500" : "bg-zinc-600"}`}
                        />
                      </span>
                    </div>
                    <span className="text-[12px] font-medium tracking-tight text-zinc-400 transition-colors group-hover:text-zinc-200">
                      {app.name}
                    </span>
                  </button>
                );
              })}
            </div>

            <div className="relative z-10 mt-auto pt-8">
              <div className="rounded-2xl border border-zinc-800/80 bg-[#121215]/90 p-5 shadow-sm">
                <div className="mb-3.5 flex items-center justify-between">
                  <span className="text-[10px] font-semibold uppercase tracking-widest text-zinc-400">
                    Recent Agent Activity
                  </span>
                  {calendarConnected ? (
                    <span className="flex items-center gap-1 font-mono text-[10px] font-medium text-emerald-400">
                      <Radio className="size-3 animate-pulse" /> Live
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => router.push(APP_DASHBOARD)}
                      className="flex items-center gap-1 text-[10px] font-medium text-zinc-400 hover:text-zinc-200"
                    >
                      View All <ArrowRight className="size-3" />
                    </button>
                  )}
                </div>

                <div className="space-y-1">
                  {recentSessions.length > 0 ? (
                    recentSessions.slice(0, 3).map((session) => (
                      <button
                        key={session.session_id}
                        type="button"
                        onClick={() => router.push(sessionPath(session.session_id))}
                        className="flex w-full cursor-pointer items-center gap-3.5 rounded-xl border border-transparent p-2.5 text-left transition-colors hover:bg-zinc-800/40"
                      >
                        <span className="flex size-9 shrink-0 items-center justify-center rounded-xl border border-zinc-800 bg-[#16161a] p-1.5 shadow-sm">
                          <Radio className="size-4 text-zinc-400" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-[13px] font-medium text-zinc-200">
                            {session.title || "Agent session"}
                          </p>
                          <p className="mt-0.5 text-[11.5px] text-zinc-400">
                            {session.status === "active" ? "Active" : "Completed"} •{" "}
                            {session.message_count} messages
                          </p>
                        </div>
                        <span className="font-mono text-[11px] text-zinc-500">
                          {formatTimeAgo(session.created_at)}
                        </span>
                      </button>
                    ))
                  ) : upcomingEvents.length > 0 ? (
                    upcomingEvents.slice(0, 3).map((event) => (
                      <button
                        key={event.id || event.summary}
                        type="button"
                        onClick={() => {
                          if (event.htmlLink) {
                            window.open(event.htmlLink, "_blank", "noopener,noreferrer");
                          } else {
                            setActiveApp("calendar");
                          }
                        }}
                        className="flex w-full cursor-pointer items-center gap-3.5 rounded-xl border border-transparent p-2.5 text-left transition-colors hover:bg-zinc-800/40"
                      >
                        <span className="flex size-9 shrink-0 items-center justify-center rounded-xl border border-zinc-800 bg-[#16161a] p-1.5 shadow-sm">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={CALENDAR_ICON} alt="Calendar" className="size-5 object-contain" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-[13px] font-medium text-zinc-200">
                            {event.summary || "Untitled event"}
                          </p>
                          <p className="mt-0.5 text-[11.5px] text-zinc-400">
                            {formatEventWhen(event.start)}
                          </p>
                        </div>
                        <span className="font-mono text-[11px] text-zinc-500">Upcoming</span>
                      </button>
                    ))
                  ) : upcomingError ? (
                    <p className="px-2 py-3 text-[12px] text-rose-300">{upcomingError}</p>
                  ) : (
                    <p className="px-2 py-3 text-center text-[13px] text-zinc-500">
                      No recent activity.
                    </p>
                  )}
                </div>
              </div>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="app"
            initial={{ opacity: 0, scale: 0.98, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: 8 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="z-20 flex flex-1 flex-col bg-[#09090b]"
          >
            <div className="relative z-30 flex items-center justify-between border-b border-zinc-800/80 bg-[#121215]/80 p-4 backdrop-blur-xl">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setActiveApp(null)}
                  className="rounded-xl border border-zinc-700 bg-zinc-800/80 p-1.5 text-zinc-400 shadow-sm transition-colors hover:bg-zinc-700 hover:text-zinc-100"
                >
                  <ChevronLeft className="size-5" />
                </button>
                <div className="flex items-center gap-2.5">
                  {(() => {
                    const app = APPS.find((item) => item.id === activeApp);
                    if (!app) return null;
                    return (
                      <div className="flex size-8 items-center justify-center rounded-xl border border-zinc-800 bg-[#16161a] p-1.5 shadow-sm">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={app.image} alt={app.name} className="size-5 object-contain" />
                      </div>
                    );
                  })()}
                  <span className="font-semibold text-zinc-100">
                    {APPS.find((item) => item.id === activeApp)?.name}
                  </span>
                </div>
              </div>
            </div>
            <div className="relative z-20 flex-1 overflow-hidden">{renderAppContent()}</div>
          </motion.div>
        )}
      </AnimatePresence>
      <SearchModal isOpen={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  );
}
