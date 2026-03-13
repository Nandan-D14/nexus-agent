"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { getAuth } from "firebase/auth";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Clock, MessageSquare, AlertCircle, RefreshCw } from "lucide-react";
import { motion } from "framer-motion";

interface Message {
  id: string;
  role: "user" | "agent";
  source: string;
  text: string;
  createdAt: string;
  turnIndex: number;
}

export default function HistoryTranscriptPage() {
  const { user } = useAuth();
  const params = useParams();
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchSessionMessages() {
      if (!user) return;
      try {
        const token = await getAuth().currentUser?.getIdToken();
        const res = await fetch(`http://localhost:8000/api/v1/history/${params.session_id}/messages`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (!res.ok) throw new Error("Failed to load session transcript");
        const data = await res.json();
        setMessages(data.messages || []);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    void fetchSessionMessages();
  }, [user, params.session_id]);

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
        <Link href="/history" className="flex items-center gap-2 text-zinc-400 hover:text-white mb-6 w-fit transition-colors">
          <ArrowLeft className="w-4 h-4" />
          <span className="text-sm font-bold uppercase tracking-widest">Back to History</span>
        </Link>
        <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl flex items-center gap-3 text-red-400">
          <AlertCircle className="w-5 h-5" />
          <p>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full max-h-screen">
      <div className="p-4 md:p-8 shrink-0 bg-background dark:bg-[#030303] border-b border-card-border dark:border-white/5 z-10 block">
        <Link href="/history" className="flex items-center gap-2 text-muted dark:text-zinc-500 hover:text-foreground dark:hover:text-white mb-4 w-fit transition-colors group">
          <ArrowLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform" />
          <span className="text-xs font-bold uppercase tracking-widest">Back to History</span>
        </Link>
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl md:text-3xl font-black italic uppercase tracking-tighter text-foreground dark:text-white">
              Session Transcript
            </h1>
            <p className="text-muted dark:text-zinc-500 font-mono text-xs mt-2 uppercase">ID: {params.session_id}</p>
          </div>
          <div className="flex gap-4 text-xs font-mono text-muted dark:text-zinc-400">
            <span className="flex items-center gap-1.5"><Clock className="w-3.5 h-3.5" /> Ended</span>
            <span className="flex items-center gap-1.5"><MessageSquare className="w-3.5 h-3.5" /> {messages.length}</span>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6">
        {messages.length === 0 ? (
          <div className="h-64 rounded-2xl border border-card-border dark:border-white/10 border-dashed flex items-center justify-center text-muted dark:text-zinc-500 font-mono text-sm uppercase">
            No messages recorded in this session
          </div>
        ) : (
          messages.map((m, i) => (
            <motion.div 
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: Math.min(i * 0.05, 0.5) }}
              key={m.id} 
              className={`flex flex-col gap-1 max-w-4xl ${m.role === "user" ? "ml-auto items-end" : "mr-auto items-start"}`}
            >
              <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-muted dark:text-zinc-600 mb-1 px-1">
                {m.role === "user" ? (
                  <>You <span className="opacity-50">via</span> {m.source}</>
                ) : (
                  <>Nexus <span className="opacity-50">via</span> {m.source}</>
                )}
              </div>
              <div className={`p-4 rounded-xl text-sm leading-relaxed ${
                m.role === "user" 
                  ? "bg-cyan-500/10 border border-cyan-500/20 text-cyan-950 dark:text-cyan-50 rounded-br-none" 
                  : "bg-card dark:bg-white/5 border border-card-border dark:border-white/10 text-foreground dark:text-zinc-300 rounded-bl-none shadow-sm dark:shadow-none"
              }`}>
                {m.text}
              </div>
              {m.createdAt && (
                <div className="text-[9px] font-mono text-muted dark:text-zinc-600 px-1 mt-1">
                  {new Date((m.createdAt as any)._seconds ? (m.createdAt as any)._seconds * 1000 : m.createdAt).toLocaleTimeString()}
                </div>
              )}
            </motion.div>
          ))
        )}
      </div>
    </div>
  );
}
