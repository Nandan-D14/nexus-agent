"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { getAuth } from "firebase/auth";
import Link from "next/link";
import { Search, Filter, Trash2, Clock, MessageSquare, AlertCircle } from "lucide-react";
import { motion } from "framer-motion";

interface HistorySession {
  session_id: string;
  title: string;
  status: string;
  created_at: string;
  ended_at: string | null;
  message_count: number;
}

export default function HistoryPage() {
  const { user } = useAuth();
  const [sessions, setSessions] = useState<HistorySession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const fetchHistory = async () => {
    if (!user) return;
    setLoading(true);
    try {
      const token = await getAuth().currentUser?.getIdToken();
      let url = "http://localhost:8000/api/v1/history?limit=50";
      if (searchQuery) url += `&q=${encodeURIComponent(searchQuery)}`;
      if (statusFilter !== "all") url += `&status=${statusFilter}`;
      
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!res.ok) throw new Error("Failed to fetch history");
      const data = await res.json();
      setSessions(data.sessions || []);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const delayDebounceFn = setTimeout(() => {
      void fetchHistory();
    }, 500);
    return () => clearTimeout(delayDebounceFn);
  }, [user, searchQuery, statusFilter]);

  const deleteSession = async (sessionId: string) => {
    if (!confirm("Are you sure you want to delete this session?")) return;
    try {
      const token = await getAuth().currentUser?.getIdToken();
      const res = await fetch(`http://localhost:8000/sessions/${sessionId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
      }
    } catch (e) {
      console.error(e);
      alert("Failed to delete session");
    }
  };

  return (
    <div className="p-4 md:p-8 max-w-7xl mx-auto space-y-8 pb-20 h-full flex flex-col text-foreground">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 shrink-0">
        <div>
          <h1 className="text-3xl md:text-5xl font-black italic uppercase tracking-tighter text-foreground">
            Mission History
          </h1>
          <p className="text-zinc-500 dark:text-zinc-400 mt-2">Review past operations and transcripts.</p>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row gap-4 shrink-0">
        <div className="relative flex-1">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-zinc-500" />
          <input 
            type="text" 
            placeholder="Search transcripts..." 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-zinc-50 dark:bg-white/5 border border-zinc-200 dark:border-white/10 rounded-xl py-3 pl-12 pr-4 text-foreground placeholder-zinc-400 focus:outline-none focus:border-cyan-500/50 transition-colors shadow-sm dark:shadow-none"
          />
        </div>
        <div className="relative shrink-0">
          <Filter className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <select 
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="appearance-none bg-zinc-50 dark:bg-white/5 border border-zinc-200 dark:border-white/10 rounded-xl py-3 pl-10 pr-10 text-foreground focus:outline-none focus:border-cyan-500/50 transition-colors shadow-sm dark:shadow-none"
          >
            <option value="all" className="bg-white dark:bg-zinc-900">All Statuses</option>
            <option value="ready" className="bg-white dark:bg-zinc-900">Ready</option>
            <option value="active" className="bg-white dark:bg-zinc-900">Active</option>
            <option value="ended" className="bg-white dark:bg-zinc-900">Ended</option>
            <option value="error" className="bg-white dark:bg-zinc-900">Error</option>
          </select>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto space-y-3 pr-2 min-h-0">
        {loading ? (
          <div className="flex justify-center p-10">
             <div className="w-8 h-8 border-4 border-cyan-600 dark:border-cyan-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : error ? (
          <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl flex items-center gap-3 text-red-600 dark:text-red-400">
            <AlertCircle className="w-5 h-5" />
            <p>{error}</p>
          </div>
        ) : sessions.length === 0 ? (
          <div className="h-64 rounded-2xl border border-zinc-300 dark:border-white/10 border-dashed flex items-center justify-center text-zinc-500 font-mono text-sm uppercase">
            No sessions found matching criteria
          </div>
        ) : (
          sessions.map((session, i) => (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              key={session.session_id}
              className="group relative flex items-center bg-zinc-50 dark:bg-white/[0.02] border border-zinc-200 dark:border-white/5 rounded-xl p-4 hover:bg-zinc-100 dark:hover:bg-white/[0.04] transition-colors shadow-sm dark:shadow-none"
            >
              <Link href={`/history/${session.session_id}`} className="absolute inset-x-0 inset-y-0 z-0" />
              
              <div className="flex-1 min-w-0 pr-14 relative z-10 flex flex-col md:flex-row gap-4 items-start md:items-center">
                <div className="flex-1 w-full min-w-0">
                  <h3 className="text-foreground font-bold truncate text-base mb-1 group-hover:text-cyan-600 dark:group-hover:text-cyan-400 transition-colors">
                    {session.title || "Untitled Session"}
                  </h3>
                  <div className="flex items-center gap-4 text-xs font-mono text-zinc-500">
                    <span className="flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5" />
                      {new Date(session.created_at).toLocaleDateString()}
                    </span>
                    <span className="flex items-center gap-1">
                      <MessageSquare className="w-3.5 h-3.5" />
                      {session.message_count} msgs
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-4 shrink-0 justify-between w-full md:w-auto">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-widest ${
                    session.status === "active" ? "bg-cyan-100 dark:bg-cyan-500/20 text-cyan-600 dark:text-cyan-400" :
                    session.status === "ended" ? "bg-zinc-200 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400" :
                    session.status === "error" ? "bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-400" :
                    "bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400"
                  }`}>
                    {session.status}
                  </span>
                  
                  <button 
                    onClick={(e) => { e.preventDefault(); deleteSession(session.session_id); }}
                    className="p-2 text-zinc-500 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-100 dark:hover:bg-red-500/10 rounded-lg transition-colors cursor-pointer"
                    title="Delete Session"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </motion.div>
          ))
        )}
      </div>
    </div>
  );
}
