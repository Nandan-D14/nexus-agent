"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Clock,
  Cpu,
  MessageSquare,
  PlayCircle,
  Power,
  Terminal,
} from "lucide-react";

import { UsageChart, type UsageChartPoint } from "@/components/usage-chart";
import { useAuth } from "@/lib/auth-context";
import { authenticatedFetch, parseApiError } from "@/lib/api-client";
import { DEFAULT_PLAN_QUOTA, type PlanQuota } from "@/lib/message-types";

type TokenTotals = {
  input: number;
  output: number;
  total: number;
  bySource?: Record<
    string,
    { input: number; output: number; total: number; model?: string }
  >;
};

type DashboardStats = {
  total_sessions: number;
  total_messages: number;
  active_sessions: number;
  sessions_this_week: number;
  avg_session_duration_mins: number;
  token_totals: TokenTotals;
  tracked_sources: string[];
  untracked_sources: string[];
};

type DashboardSessionUsage = {
  session_id: string;
  title: string;
  status: string;
  created_at: string | null;
  message_count: number;
  token_totals: TokenTotals;
  token_tracking_started_at: string | null;
  token_coverage: "tracked" | "no_data";
};

type ActiveSession = {
  session_id: string;
  title: string;
  status: string;
  created_at: string | null;
  last_active_at: string | null;
  stream_url: string | null;
  message_count: number;
  token_totals: TokenTotals;
  token_tracking_started_at: string | null;
  token_coverage: "tracked" | "no_data";
};

type ChartMetric = "total_tokens" | "sessions" | "messages";

const EMPTY_TOKEN_TOTALS: TokenTotals = {
  input: 0,
  output: 0,
  total: 0,
  bySource: {},
};

function formatNumber(value: number) {
  return new Intl.NumberFormat("en-US").format(value);
}

function formatCompactNumber(value: number) {
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

function formatDate(value: string | null) {
  if (!value) {
    return "Unknown";
  }
  return new Date(value).toLocaleDateString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatDateTime(value: string | null) {
  if (!value) {
    return "Unknown";
  }
  return new Date(value).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatRelativeTime(value: string | null) {
  if (!value) {
    return "No recent activity";
  }

  const diffMs = Date.now() - new Date(value).getTime();
  const diffMins = Math.max(Math.round(diffMs / 60000), 0);
  if (diffMins < 1) {
    return "Just now";
  }
  if (diffMins < 60) {
    return `${diffMins}m ago`;
  }

  const diffHours = Math.round(diffMins / 60);
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }

  const diffDays = Math.round(diffHours / 24);
  return `${diffDays}d ago`;
}

function StatCard({
  title,
  value,
  icon: Icon,
  subtitle,
}: {
  title: string;
  value: string;
  icon: React.ComponentType<{ className?: string }>;
  subtitle?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-[28px] border border-zinc-200/80 bg-white/80 p-6 shadow-[0_18px_50px_rgba(15,23,42,0.06)] backdrop-blur-sm dark:border-white/8 dark:bg-white/[0.04] dark:shadow-none"
    >
      <div className="flex items-center justify-between text-zinc-500 dark:text-zinc-400">
        <span className="text-[11px] font-semibold uppercase tracking-[0.22em]">
          {title}
        </span>
        <Icon className="h-5 w-5 text-cyan-600 dark:text-cyan-400" />
      </div>
      <div className="mt-5">
        <p className="text-3xl font-semibold tracking-tight text-zinc-950 dark:text-white">
          {value}
        </p>
        {subtitle ? (
          <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
            {subtitle}
          </p>
        ) : null}
      </div>
    </motion.div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [usage, setUsage] = useState<UsageChartPoint[]>([]);
  const [recentSessions, setRecentSessions] = useState<DashboardSessionUsage[]>(
    [],
  );
  const [activeSessions, setActiveSessions] = useState<ActiveSession[]>([]);
  const [chartMetric, setChartMetric] = useState<ChartMetric>("total_tokens");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [endingSessionId, setEndingSessionId] = useState<string | null>(null);
  const [quota, setQuota] = useState<PlanQuota | null>(null);

  const refreshDashboard = useCallback(async () => {
    if (!user) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const [statsRes, usageRes, sessionUsageRes, activeSessionsRes, quotaRes] =
        await Promise.all([
          authenticatedFetch("/api/v1/dashboard/stats"),
          authenticatedFetch("/api/v1/dashboard/usage?days=30"),
          authenticatedFetch("/api/v1/dashboard/sessions?limit=12"),
          authenticatedFetch("/api/v1/sessions/active"),
          authenticatedFetch("/api/v1/user/quota"),
        ]);

      if (!statsRes.ok) {
        throw new Error(await parseApiError(statsRes));
      }
      if (!usageRes.ok) {
        throw new Error(await parseApiError(usageRes));
      }
      if (!sessionUsageRes.ok) {
        throw new Error(await parseApiError(sessionUsageRes));
      }
      if (!activeSessionsRes.ok) {
        throw new Error(await parseApiError(activeSessionsRes));
      }

      const statsBody = (await statsRes.json()) as DashboardStats;
      const usageBody = (await usageRes.json()) as { chart: UsageChartPoint[] };
      const sessionUsageBody = (await sessionUsageRes.json()) as {
        sessions: DashboardSessionUsage[];
      };
      const activeBody = (await activeSessionsRes.json()) as {
        sessions: ActiveSession[];
      };

      if (quotaRes.ok) {
        const quotaBody = (await quotaRes.json()) as PlanQuota;
        setQuota(quotaBody);
      } else {
        setQuota(DEFAULT_PLAN_QUOTA);
      }

      setStats({
        ...statsBody,
        token_totals: statsBody.token_totals || EMPTY_TOKEN_TOTALS,
      });
      setUsage(usageBody.chart || []);
      setRecentSessions(sessionUsageBody.sessions || []);
      setActiveSessions(activeBody.sessions || []);
    } catch (fetchError) {
      setError(
        fetchError instanceof Error
          ? fetchError.message
          : "Failed to fetch dashboard data",
      );
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    void refreshDashboard();
  }, [refreshDashboard]);

  const handleEndSession = useCallback(
    async (sessionId: string) => {
      const shouldEnd = window.confirm(
        "End this active session and close its desktop?",
      );
      if (!shouldEnd) {
        return;
      }

      setEndingSessionId(sessionId);
      try {
        const response = await authenticatedFetch(`/api/v1/sessions/${sessionId}`, {
          method: "DELETE",
        });        if (!response.ok) {
          throw new Error(await parseApiError(response));
        }
        await refreshDashboard();
      } catch (requestError) {
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Failed to end session",
        );
      } finally {
        setEndingSessionId(null);
      }
    },
    [refreshDashboard],
  );

  const handleStartSession = useCallback(() => {
    if (!user) {
      return;
    }
    router.push("/session/new");
  }, [router, user]);

  const sourceSummary = useMemo(() => {
    const tracked = stats?.tracked_sources || [];
    const untracked = stats?.untracked_sources || [];
    return {
      trackedLabel: tracked.length ? tracked.join(", ") : "None yet",
      untrackedLabel: untracked.length ? untracked.join(", ") : "None",
    };
  }, [stats?.tracked_sources, stats?.untracked_sources]);

  const tokenTotals = stats?.token_totals || EMPTY_TOKEN_TOTALS;

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-cyan-600 border-t-transparent dark:border-cyan-500" />
      </div>
    );
  }

  if (error && !stats) {
    return (
      <div className="p-8">
        <div className="flex items-center gap-3 rounded-2xl border border-red-500/20 bg-red-500/10 p-4 text-red-600 dark:text-red-400">
          <AlertTriangle className="h-5 w-5" />
          <p>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-8 px-4 pb-20 pt-4 text-foreground md:px-8">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-zinc-950 dark:text-white md:text-5xl">
            Dashboard
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-zinc-500 dark:text-zinc-400 md:text-base">
            Session health, token telemetry, and live session controls for{" "}
            {user?.displayName || "your workspace"}.
          </p>
        </div>
        <button
          type="button"
          onClick={handleStartSession}
          disabled={!user}
          className="inline-flex items-center justify-center rounded-full bg-zinc-950 px-5 py-3 text-sm font-medium text-white transition-colors hover:bg-cyan-700 dark:bg-white dark:text-zinc-950 dark:hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-60"
        >
          Start New Session
        </button>
      </div>

      {error ? (
        <div className="flex items-center gap-3 rounded-2xl border border-red-500/20 bg-red-500/10 p-4 text-red-600 dark:text-red-400">
          <AlertTriangle className="h-5 w-5" />
          <p>{error}</p>
        </div>
      ) : null}

      {/* Starter Plan Banner */}
      {quota && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className={`rounded-[28px] border p-6 shadow-[0_18px_50px_rgba(15,23,42,0.06)] backdrop-blur-sm ${
            quota.remaining <= 0
              ? "border-red-500/30 bg-red-50/80 dark:border-red-500/20 dark:bg-red-950/20"
              : quota.used / quota.limit >= 0.8
                ? "border-amber-500/30 bg-amber-50/80 dark:border-amber-500/20 dark:bg-amber-950/20"
                : "border-zinc-200/80 bg-white/80 dark:border-white/8 dark:bg-white/[0.04]"
          }`}
        >
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-zinc-500 dark:text-zinc-400">
                {quota.plan_name || "$5 Starter"}
              </p>
              <p className="mt-1 text-2xl font-semibold tracking-tight text-zinc-950 dark:text-white">
                {formatCompactNumber(quota.used)}{" "}
                <span className="text-base font-normal text-zinc-500 dark:text-zinc-400">
                  / {formatCompactNumber(quota.limit)} {quota.unit || "credits"}
                </span>
              </p>
              {quota.remaining <= 0 ? (
                <p className="mt-1 text-sm text-red-600 dark:text-red-400 font-medium">
                  Starter plan balance exhausted for this development entitlement.
                </p>
              ) : quota.used / quota.limit >= 0.8 ? (
                <p className="mt-1 text-sm text-amber-600 dark:text-amber-400">
                  {formatNumber(quota.remaining)} {quota.unit || "credits"} remaining
                </p>
              ) : (
                <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                  {formatNumber(quota.remaining)} {quota.unit || "credits"} remaining
                </p>
              )}
            </div>
            <div className="text-right text-sm text-zinc-500 dark:text-zinc-400">
              {Math.min(100, Math.round((quota.used / quota.limit) * 100))}% used
            </div>
          </div>
          <div className="mt-4 h-2 w-full rounded-full bg-zinc-200 dark:bg-zinc-800 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-700 ${
                quota.remaining <= 0
                  ? "bg-red-500"
                  : quota.used / quota.limit >= 0.8
                    ? "bg-amber-500"
                    : "bg-cyan-500"
              }`}
              style={{ width: `${Math.min(100, (quota.used / quota.limit) * 100)}%` }}
            />
          </div>
        </motion.div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          title="Total Sessions"
          value={formatNumber(stats?.total_sessions || 0)}
          icon={Terminal}
          subtitle={`${stats?.sessions_this_week || 0} started this week`}
        />
        <StatCard
          title="Total Messages"
          value={formatNumber(stats?.total_messages || 0)}
          icon={MessageSquare}
        />
        <StatCard
          title="Average Duration"
          value={`${stats?.avg_session_duration_mins || 0}m`}
          icon={Clock}
        />
        <StatCard
          title="Active Sessions"
          value={formatNumber(stats?.active_sessions || 0)}
          icon={Activity}
          subtitle="Live desktops in this backend"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          title="Total Tokens"
          value={formatCompactNumber(tokenTotals.total)}
          icon={Cpu}
          subtitle={`${formatNumber(tokenTotals.total)} exact tokens tracked`}
        />
        <StatCard
          title="Input Tokens"
          value={formatCompactNumber(tokenTotals.input)}
          icon={BarChart3}
          subtitle="Prompt and input-side usage"
        />
        <StatCard
          title="Output Tokens"
          value={formatCompactNumber(tokenTotals.output)}
          icon={PlayCircle}
          subtitle="Model output and completion usage"
        />
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-[28px] border border-zinc-200/80 bg-white/80 p-6 shadow-[0_18px_50px_rgba(15,23,42,0.06)] backdrop-blur-sm dark:border-white/8 dark:bg-white/[0.04] dark:shadow-none"
        >
          <div className="flex items-center justify-between text-zinc-500 dark:text-zinc-400">
            <span className="text-[11px] font-semibold uppercase tracking-[0.22em]">
              Source Coverage
            </span>
            <Power className="h-5 w-5 text-cyan-600 dark:text-cyan-400" />
          </div>
          <div className="mt-5 space-y-4 text-sm">
            <div>
              <p className="font-medium text-zinc-950 dark:text-white">Tracked</p>
              <p className="mt-1 text-zinc-500 dark:text-zinc-400">
                {sourceSummary.trackedLabel}
              </p>
            </div>
            <div className="border-t border-zinc-200/80 pt-4 dark:border-white/8">
              <p className="font-medium text-zinc-950 dark:text-white">
                Waiting for exact metadata
              </p>
              <p className="mt-1 text-zinc-500 dark:text-zinc-400">
                {sourceSummary.untrackedLabel}
              </p>
            </div>
          </div>
        </motion.div>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.7fr)_minmax(320px,1fr)]">
        <div className="space-y-6">
          <section className="rounded-3xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-[#2f2f35] dark:bg-[#1a1a1c]">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-zinc-500 dark:text-zinc-400">
                  30 Day Usage
                </p>
                <h2 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-950 dark:text-white">
                  Usage trend
                </h2>
              </div>
              <div className="flex flex-wrap gap-2">
                {[
                  { key: "total_tokens", label: "Tokens" },
                  { key: "sessions", label: "Sessions" },
                  { key: "messages", label: "Messages" },
                ].map((option) => (
                  <button
                    key={option.key}
                    onClick={() => setChartMetric(option.key as ChartMetric)}
                    className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                      chartMetric === option.key
                        ? "bg-zinc-950 text-white dark:bg-white dark:text-zinc-950"
                        : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-white/8 dark:text-zinc-300 dark:hover:bg-white/14"
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-6 h-[320px]">
              <UsageChart data={usage} metric={chartMetric} />
            </div>

            <p className="mt-4 text-sm text-zinc-500 dark:text-zinc-400">
              Exact token tracking starts from this rollout. Older sessions remain
              visible but show no token telemetry.
            </p>
          </section>

          <section className="rounded-[32px] border border-zinc-200/80 bg-white/85 p-6 shadow-[0_24px_60px_rgba(15,23,42,0.06)] backdrop-blur-sm dark:border-white/8 dark:bg-white/[0.04] dark:shadow-none">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-zinc-500 dark:text-zinc-400">
                  Session Token Breakdown
                </p>
                <h2 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-950 dark:text-white">
                  Recent session usage
                </h2>
              </div>
              <Link
                href="/history"
                className="text-sm font-medium text-cyan-700 hover:text-cyan-600 dark:text-cyan-300 dark:hover:text-cyan-200"
              >
                View history
              </Link>
            </div>

            <div className="mt-6 overflow-x-auto">
              <table className="min-w-full divide-y divide-zinc-200/80 text-sm dark:divide-white/8">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-[0.2em] text-zinc-500 dark:text-zinc-400">
                    <th className="pb-3 font-medium">Session</th>
                    <th className="pb-3 font-medium">Status</th>
                    <th className="pb-3 font-medium">Created</th>
                    <th className="pb-3 font-medium text-right">Input</th>
                    <th className="pb-3 font-medium text-right">Output</th>
                    <th className="pb-3 font-medium text-right">Total</th>
                    <th className="pb-3 font-medium text-right">Coverage</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-200/60 dark:divide-white/6">
                  {recentSessions.length ? (
                    recentSessions.map((session) => (
                      <tr key={session.session_id} className="align-top">
                        <td className="py-4 pr-6">
                          <Link
                            href={`/history/${session.session_id}`}
                            className="font-medium text-zinc-950 hover:text-cyan-700 dark:text-white dark:hover:text-cyan-300"
                          >
                            {session.title}
                          </Link>
                          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                            {session.message_count} messages
                          </p>
                        </td>
                        <td className="py-4 pr-6">
                          <span className="rounded-full bg-zinc-100 px-2.5 py-1 text-[11px] font-medium capitalize text-zinc-700 dark:bg-white/8 dark:text-zinc-200">
                            {session.status}
                          </span>
                        </td>
                        <td className="py-4 pr-6 text-zinc-600 dark:text-zinc-300">
                          {formatDate(session.created_at)}
                        </td>
                        <td className="py-4 pr-6 text-right font-medium text-zinc-800 dark:text-zinc-200">
                          {formatNumber(session.token_totals?.input || 0)}
                        </td>
                        <td className="py-4 pr-6 text-right font-medium text-zinc-800 dark:text-zinc-200">
                          {formatNumber(session.token_totals?.output || 0)}
                        </td>
                        <td className="py-4 pr-6 text-right font-semibold text-zinc-950 dark:text-white">
                          {formatNumber(session.token_totals?.total || 0)}
                        </td>
                        <td className="py-4 text-right">
                          <span
                            className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${
                              session.token_coverage === "tracked"
                                ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/12 dark:text-emerald-300"
                                : "bg-zinc-100 text-zinc-600 dark:bg-white/8 dark:text-zinc-400"
                            }`}
                          >
                            {session.token_coverage === "tracked"
                              ? "Tracked"
                              : "No data"}
                          </span>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td
                        colSpan={7}
                        className="py-10 text-center text-sm text-zinc-500 dark:text-zinc-400"
                      >
                        No sessions available yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>

        <div className="space-y-6">
          <section className="rounded-[32px] border border-zinc-200/80 bg-white/85 p-6 shadow-[0_24px_60px_rgba(15,23,42,0.06)] backdrop-blur-sm dark:border-white/8 dark:bg-white/[0.04] dark:shadow-none">
            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-zinc-500 dark:text-zinc-400">
              Active Session Management
            </p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-950 dark:text-white">
              Live desktops
            </h2>

            <div className="mt-6 space-y-4">
              {activeSessions.length ? (
                activeSessions.map((session) => (
                  <div
                    key={session.session_id}
                    className="rounded-[24px] border border-zinc-200/80 bg-zinc-50/90 p-4 dark:border-white/8 dark:bg-white/[0.03]"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-base font-medium text-zinc-950 dark:text-white">
                          {session.title}
                        </p>
                        <p className="mt-1 text-xs uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
                          {session.status} • {formatRelativeTime(session.last_active_at)}
                        </p>
                      </div>
                      <span className="inline-flex items-center gap-2 rounded-full bg-emerald-100 px-3 py-1 text-[11px] font-medium text-emerald-700 dark:bg-emerald-500/12 dark:text-emerald-300">
                        <span className="h-2 w-2 rounded-full bg-emerald-500" />
                        Live
                      </span>
                    </div>

                    <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                      <div className="rounded-2xl bg-white/80 p-3 dark:bg-white/[0.03]">
                        <p className="text-zinc-500 dark:text-zinc-400">Last active</p>
                        <p className="mt-1 font-medium text-zinc-950 dark:text-white">
                          {formatDateTime(session.last_active_at)}
                        </p>
                      </div>
                      <div className="rounded-2xl bg-white/80 p-3 dark:bg-white/[0.03]">
                        <p className="text-zinc-500 dark:text-zinc-400">Tracked tokens</p>
                        <p className="mt-1 font-medium text-zinc-950 dark:text-white">
                          {formatNumber(session.token_totals?.total || 0)}
                        </p>
                      </div>
                    </div>

                    <div className="mt-4 flex items-center justify-between gap-3 text-sm text-zinc-500 dark:text-zinc-400">
                      <span>
                        {session.token_coverage === "tracked"
                          ? "Exact token data available"
                          : "No token data yet"}
                      </span>
                      <span>{session.message_count} msgs</span>
                    </div>

                    <div className="mt-4 flex gap-3">
                      <Link
                        href={`/session/${session.session_id}`}
                        className="flex-1 rounded-full bg-zinc-950 px-4 py-2.5 text-center text-sm font-medium text-white transition-colors hover:bg-cyan-700 dark:bg-white dark:text-zinc-950 dark:hover:bg-cyan-200"
                      >
                        Resume
                      </Link>
                      <button
                        onClick={() => void handleEndSession(session.session_id)}
                        disabled={endingSessionId === session.session_id}
                        className="rounded-full border border-red-500/20 px-4 py-2.5 text-sm font-medium text-red-600 transition-colors hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-50 dark:text-red-300"
                      >
                        {endingSessionId === session.session_id ? "Ending..." : "End"}
                      </button>
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-[24px] border border-dashed border-zinc-300 bg-zinc-50/60 p-6 text-sm text-zinc-500 dark:border-white/10 dark:bg-white/[0.03] dark:text-zinc-400">
                  No active sessions right now.
                </div>
              )}
            </div>
          </section>

          <section className="rounded-[32px] border border-zinc-200/80 bg-white/85 p-6 shadow-[0_24px_60px_rgba(15,23,42,0.06)] backdrop-blur-sm dark:border-white/8 dark:bg-white/[0.04] dark:shadow-none">
            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-zinc-500 dark:text-zinc-400">
              Runtime
            </p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-950 dark:text-white">
              System status
            </h2>

            <div className="mt-6 flex items-center gap-4 rounded-[24px] bg-zinc-50/80 p-4 dark:bg-white/[0.03]">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-100 dark:bg-cyan-500/10">
                <div className="h-3 w-3 animate-pulse rounded-full bg-cyan-500" />
              </div>
              <div>
                <p className="text-lg font-medium text-zinc-950 dark:text-white">
                  Services online
                </p>
                <p className="text-sm text-emerald-600 dark:text-emerald-400">
                  API, session manager, and desktop backend responding
                </p>
              </div>
            </div>

            <div className="mt-6 space-y-4 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-zinc-500 dark:text-zinc-400">Tracked models</span>
                <span className="font-medium text-zinc-950 dark:text-white">
                  {stats?.tracked_sources.length || 0}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-zinc-500 dark:text-zinc-400">Untracked models</span>
                <span className="font-medium text-zinc-950 dark:text-white">
                  {stats?.untracked_sources.length || 0}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-zinc-500 dark:text-zinc-400">Token telemetry</span>
                <span className="font-medium text-zinc-950 dark:text-white">
                  Future-only exact capture
                </span>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
