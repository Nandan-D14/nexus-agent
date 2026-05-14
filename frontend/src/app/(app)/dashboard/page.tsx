/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

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
      className="rounded-[28px] border border-zinc-200 bg-white p-6 shadow-sm dark:border-white/5 dark:bg-white/[0.02] dark:shadow-none"
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
    if (!user) return;
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

      if (!statsRes.ok) throw new Error(await parseApiError(statsRes));
      if (!usageRes.ok) throw new Error(await parseApiError(usageRes));
      if (!sessionUsageRes.ok) throw new Error(await parseApiError(sessionUsageRes));
      if (!activeSessionsRes.ok) throw new Error(await parseApiError(activeSessionsRes));

      const statsBody = await statsRes.json();
      const usageBody = await usageRes.json();
      const sessionUsageBody = await sessionUsageRes.json();
      const activeBody = await activeSessionsRes.json();

      if (quotaRes.ok) {
        setQuota(await quotaRes.json());
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
      setError(fetchError instanceof Error ? fetchError.message : "Failed to fetch data");
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    void refreshDashboard();
  }, [refreshDashboard]);

  const handleEndSession = async (sessionId: string) => {
    if (!window.confirm("End this active session?")) return;
    setEndingSessionId(sessionId);
    try {
      const res = await authenticatedFetch(`/api/v1/sessions/${sessionId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await parseApiError(res));
      await refreshDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to end session");
    } finally {
      setEndingSessionId(null);
    }
  };

  const handleStartSession = () => {
    if (user) router.push("/session/new");
  };

  const sourceSummary = useMemo(() => {
    const tracked = stats?.tracked_sources || [];
    const untracked = stats?.untracked_sources || [];
    return {
      tracked: tracked.length ? tracked.join(", ") : "None yet",
      untracked: untracked.length ? untracked.join(", ") : "None",
    };
  }, [stats]);

  const tokenTotals = stats?.token_totals || EMPTY_TOKEN_TOTALS;
  const usageRatio = quota ? (quota.used / quota.limit) : 0;
  const usagePercent = Math.min(100, Math.round(usageRatio * 100));

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-cyan-600 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-8 px-4 pb-20 pt-4 text-foreground md:px-8">
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-zinc-950 dark:text-white md:text-5xl">      
            Dashboard
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-zinc-500 dark:text-zinc-400">
            Session health and token telemetry for {user?.displayName || "your workspace"}.
          </p>
        </div>
        <button
          onClick={handleStartSession}
          className="inline-flex items-center justify-center rounded-full bg-zinc-950 px-5 py-3 text-sm font-medium text-white hover:bg-cyan-700 dark:bg-white dark:text-zinc-950 transition-colors"
        >
          Start New Session
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-3 rounded-2xl border border-red-500/20 bg-red-500/10 p-4 text-red-600 dark:text-red-400">
          <AlertTriangle className="h-5 w-5" />
          <p>{error}</p>
        </div>
      )}

      {/* Quota Banner */}
      {quota && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className={`rounded-[28px] border p-6 backdrop-blur-sm ${
            quota.remaining <= 0 ? "border-red-500 bg-red-50 dark:bg-red-950" : 
            usageRatio >= 0.8 ? "border-amber-500 bg-amber-50 dark:bg-amber-950" : 
            "border-zinc-200 bg-white dark:border-white"
          }`}
        >
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-zinc-500">
                {quota.plan_name || "Usage Credits"}
              </p>
              <p className="mt-1 text-2xl font-semibold tracking-tight">
                {formatCompactNumber(quota.used)} / {formatCompactNumber(quota.limit)}
              </p>
            </div>
            <div className="text-right text-sm text-zinc-500">
              {usagePercent}% used
            </div>
          </div>
          <div className="mt-4 h-2 w-full rounded-full bg-zinc-200 dark:bg-zinc-800 overflow-hidden">
            <div
              className={`h-full transition-all duration-700 ${
                quota.remaining <= 0 ? "bg-red-500" : usageRatio >= 0.8 ? "bg-amber-500" : "bg-cyan-500"
              }`}
              style={{ width: `${usagePercent}%` }}
            ></div>
          </div>
        </motion.div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard title="Total Sessions" value={formatNumber(stats?.total_sessions || 0)} icon={Terminal} />
        <StatCard title="Total Messages" value={formatNumber(stats?.total_messages || 0)} icon={MessageSquare} />
        <StatCard title="Avg Duration" value={`${stats?.avg_session_duration_mins || 0}m`} icon={Clock} />
        <StatCard title="Active" value={formatNumber(stats?.active_sessions || 0)} icon={Activity} />
      </div>

      {/* Token Grid */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard title="Total Tokens" value={formatCompactNumber(tokenTotals.total)} icon={Cpu} />
        <StatCard title="Input" value={formatCompactNumber(tokenTotals.input)} icon={BarChart3} />
        <StatCard title="Output" value={formatCompactNumber(tokenTotals.output)} icon={PlayCircle} />
        <div className="rounded-[28px] border border-zinc-200 bg-white p-6 dark:border-white/5 dark:bg-white/[0.02]">
          <div className="flex items-center justify-between text-zinc-500">
            <span className="text-[11px] font-semibold uppercase tracking-[0.22em]">Source Coverage</span>
            <Power className="h-5 w-5" />
          </div>
          <div className="mt-5 space-y-3 text-sm">
            <div>
              <p className="font-medium">Tracked</p>
              <p className="text-xs text-zinc-500 truncate">{sourceSummary.tracked}</p>
            </div>
            <div className="border-t border-zinc-100 dark:border-white/5 pt-3">
              <p className="font-medium">Untracked</p>
              <p className="text-xs text-zinc-500 truncate">{sourceSummary.untracked}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Charts & History Grid */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2 space-y-6">
          <section className="rounded-3xl border border-zinc-200 bg-white p-6 dark:border-white/5 dark:bg-white/[0.02]">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-semibold">Usage Trend</h2>
              <div className="flex gap-2">
                {["total_tokens", "sessions", "messages"].map((m) => (
                  <button
                    key={m}
                    onClick={() => setChartMetric(m as ChartMetric)}
                    className={`px-3 py-1 text-xs rounded-full transition-colors ${chartMetric === m ? "bg-indigo-600 text-white" : "bg-zinc-100 dark:bg-white/5 text-zinc-500"}`}
                  >
                    {m.replace("_", " ")}
                  </button>
                ))}
              </div>
            </div>
            <div className="h-[300px]">
              <UsageChart data={usage} metric={chartMetric} />
            </div>
          </section>

          <section className="rounded-3xl border border-zinc-200 bg-white p-6 dark:border-white/5 dark:bg-white/[0.02]">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-semibold">Recent Sessions</h2>
              <Link href="/history" className="text-sm text-cyan-600">View all</Link>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead>
                  <tr className="text-[10px] uppercase tracking-widest text-zinc-500 border-b border-zinc-100 dark:border-white/5">
                    <th className="pb-3 px-2">Session</th>
                    <th className="pb-3 px-2">Status</th>
                    <th className="pb-3 px-2 text-right">Total Tokens</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-50 dark:divide-white/5">
                  {recentSessions.map((s) => (
                    <tr key={s.session_id}>
                      <td className="py-3 px-2">
                        <Link href={`/history/${s.session_id}`} className="font-medium hover:text-cyan-600">{s.title}</Link>
                        <p className="text-[10px] text-zinc-500">{formatDate(s.created_at)}</p>
                      </td>
                      <td className="py-3 px-2">
                        <span className="px-2 py-0.5 rounded-full bg-zinc-100 dark:bg-white/5 text-[10px]">{s.status}</span>
                      </td>
                      <td className="py-3 px-2 text-right font-mono font-medium">
                        {formatNumber(s.token_totals?.total || 0)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>

        {/* Active Side column */}
        <div className="space-y-6">
          <section className="rounded-3xl border border-zinc-200 bg-white p-6 dark:border-white/5 dark:bg-white/[0.02]">
            <h2 className="text-xl font-semibold mb-6">Live Desktops</h2>
            <div className="space-y-4">
              {activeSessions.map((s) => (
                <div key={s.session_id} className="p-4 rounded-2xl bg-zinc-50 dark:bg-white/5 border border-zinc-100 dark:border-white/5">
                  <p className="font-medium truncate">{s.title}</p>
                  <p className="text-[10px] text-zinc-500 mt-1 uppercase tracking-wider">{s.status} • {formatRelativeTime(s.last_active_at)}</p>
                  <div className="flex gap-2 mt-4">
                    <Link href={`/session/${s.session_id}`} className="flex-1 text-center py-2 bg-zinc-950 text-white dark:bg-white dark:text-black rounded-full text-xs font-medium">Resume</Link>
                    <button onClick={() => void handleEndSession(s.session_id)} className="px-4 py-2 border border-red-500/20 text-red-500 rounded-full text-xs font-medium">End</button>
                  </div>
                </div>
              ))}
              {!activeSessions.length && <p className="text-sm text-zinc-500 italic text-center py-8">No active sessions.</p>}
            </div>
          </section>

          <section className="rounded-3xl border border-zinc-200 bg-white p-6 dark:border-white/5 dark:bg-white/[0.02]">
            <h2 className="text-xl font-semibold mb-4">System Status</h2>
            <div className="flex items-center gap-3 p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/10">
              <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-xs font-medium text-emerald-600">All systems operational</span>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
