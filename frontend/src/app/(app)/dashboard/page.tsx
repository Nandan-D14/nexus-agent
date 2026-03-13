"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { Activity, Clock, MessageSquare, Terminal, AlertTriangle } from "lucide-react";
import { getAuth } from "firebase/auth";
import { UsageChart } from "@/components/usage-chart";
import Link from "next/link";
import { motion } from "framer-motion";

interface DashboardStats {
  total_sessions: number;
  total_messages: number;
  active_sessions: number;
  sessions_this_week: number;
  avg_session_duration_mins: number;
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [usage, setUsage] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchDashboardData() {
      if (!user) return;
      try {
        const token = await getAuth().currentUser?.getIdToken();
        const headers = { Authorization: `Bearer ${token}` };

        const [statsRes, usageRes] = await Promise.all([
          fetch("http://localhost:8000/api/v1/dashboard/stats", { headers }),
          fetch("http://localhost:8000/api/v1/dashboard/usage?days=30", { headers })
        ]);

        if (!statsRes.ok || !usageRes.ok) throw new Error("Failed to fetch dashboard data");

        const s = await statsRes.json();
        const u = await usageRes.json();

        setStats(s);
        setUsage(u.chart);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    void fetchDashboardData();
  }, [user]);

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center h-full">
        <div className="w-8 h-8 border-4 border-cyan-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl flex items-center gap-3 text-red-400">
          <AlertTriangle className="w-5 h-5" />
          <p>{error}</p>
        </div>
      </div>
    );
  }

  const StatCard = ({ title, value, icon: Icon, subtitle }: any) => (
    <motion.div 
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="p-6 rounded-2xl bg-white/5 border border-white/10 flex flex-col gap-4"
    >
      <div className="flex items-center justify-between text-zinc-400">
        <span className="text-sm font-bold tracking-wider uppercase">{title}</span>
        <Icon className="w-5 h-5 text-cyan-500" />
      </div>
      <div>
        <span className="text-4xl font-black">{value}</span>
        {subtitle && <p className="text-xs text-zinc-500 mt-2">{subtitle}</p>}
      </div>
    </motion.div>
  );

  return (
    <div className="p-4 md:p-8 max-w-7xl mx-auto space-y-8 pb-20">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl md:text-5xl font-black italic uppercase tracking-tighter text-white">
            Dashboard
          </h1>
          <p className="text-zinc-400 mt-2">Welcome back, {user?.displayName || "Agent"}.</p>
        </div>
        <Link 
          href="/"
          className="px-6 py-3 rounded-xl bg-white text-black font-black text-sm uppercase tracking-widest hover:bg-cyan-400 transition-all shadow-lg active:scale-95 inline-block text-center"
        >
          Initialize Mission
        </Link>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard 
          title="Total Sessions" 
          value={stats?.total_sessions || 0} 
          icon={Terminal} 
          subtitle={`${stats?.sessions_this_week || 0} this week`}
        />
        <StatCard 
          title="Total Messages" 
          value={stats?.total_messages || 0} 
          icon={MessageSquare} 
        />
        <StatCard 
          title="Avg Duration" 
          value={`${stats?.avg_session_duration_mins || 0}m`} 
          icon={Clock} 
        />
        <StatCard 
          title="Active Runs" 
          value={stats?.active_sessions || 0} 
          icon={Activity} 
          subtitle="Sandboxes currently active"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold tracking-widest uppercase text-zinc-400">Activity (30 Days)</h2>
          </div>
          <div className="h-[300px] p-6 rounded-2xl bg-white/5 border border-white/10">
            <UsageChart data={usage} />
          </div>
        </div>
        
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold tracking-widest uppercase text-zinc-400">Agent Status</h2>
          </div>
          <div className="p-6 rounded-2xl bg-white/5 border border-white/10 space-y-6">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-cyan-500/20 flex items-center justify-center border border-cyan-500/30">
                <div className="w-3 h-3 rounded-full bg-cyan-500 shadow-[0_0_10px_rgba(34,211,238,1)] animate-pulse" />
              </div>
              <div>
                <p className="font-bold text-lg text-white">System Online</p>
                <p className="text-xs text-emerald-400 uppercase tracking-widest">All services operational</p>
              </div>
            </div>
            
            <div className="space-y-4 pt-4 border-t border-white/5">
              <div className="flex justify-between items-center text-sm">
                <span className="text-zinc-500">API Latency</span>
                <span className="text-zinc-300 font-mono">18ms</span>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span className="text-zinc-500">Sandbox Backend</span>
                <span className="text-zinc-300 font-mono">E2B Desktop</span>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span className="text-zinc-500">Language Model</span>
                <span className="text-zinc-300 font-mono text-xs">MiniMax Kilo / Gemini Flash</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
