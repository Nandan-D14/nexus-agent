/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useCallback, useEffect, useState, useRef, useMemo } from "react";
import { Search, X, Clock, ArrowRight, MessageSquare, History, Loader2, Calendar } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { useSession } from "@/lib/use-session";
import { type RecentSession } from "@/lib/message-types";

type SearchModalProps = {
  isOpen: boolean;
  onClose: () => void;
};

export function SearchModal({ isOpen, onClose }: SearchModalProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<RecentSession[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const pathname = usePathname();
  const { listSessions } = useSession();

  useEffect(() => {
    if (isOpen) {
      const timer = setTimeout(() => inputRef.current?.focus(), 100);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  const handleClose = useCallback(() => {
    setQuery("");
    setResults([]);
    onClose();
  }, [onClose]);

  // Live search with debounce
  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      setIsLoading(false);
      return;
    }

    const handler = setTimeout(async () => {
      setIsLoading(true);
      try {
        // Fetch sessions and filter locally for now (assuming backend list is limited)
        // In a real prod app, we'd use a dedicated search endpoint
        const sessions = await listSessions(50);
        const filtered = sessions.filter(s => 
          (s.title?.toLowerCase().includes(query.toLowerCase())) ||
          (s.summary?.toLowerCase().includes(query.toLowerCase()))
        );
        setResults(filtered.slice(0, 8));
      } catch (err) {
        console.error("Search failed", err);
      } finally {
        setIsLoading(false);
      }
    }, 300);

    return () => clearTimeout(handler);
  }, [query, listSessions]);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleClose]);

  if (!isOpen) return null;

  const navigateToSession = (sid: string) => {
    router.push(`/session/${sid}`);
    handleClose();
  };

  const performSearchPage = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    
    const target = `/history?q=${encodeURIComponent(trimmed)}`;
    if (pathname === "/history") {
      router.replace(target);
    } else {
      router.push(target);
    }
    handleClose();
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (results.length > 0) {
      navigateToSession(results[0].session_id);
    } else {
      performSearchPage(query);
    }
  };

  const formatTime = (ts: string | null) => {
    if (!ts) return "";
    return new Date(ts).toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[10vh] px-4">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={handleClose}
        className="fixed inset-0 bg-zinc-950/40 backdrop-blur-sm"
      />
      
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: -20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: -20 }}
        className="w-full max-w-2xl bg-white dark:bg-[#1a1a1c] rounded-2xl shadow-2xl border border-zinc-200 dark:border-white/10 overflow-hidden relative z-10"
      >
        <form onSubmit={handleSearchSubmit}>
          <div className="p-4 border-b border-zinc-200 dark:border-white/10 flex items-center gap-3">
            {isLoading ? (
              <Loader2 className="w-5 h-5 text-indigo-500 animate-spin" />
            ) : (
              <Search className="w-5 h-5 text-zinc-400" />
            )}
            <input
              ref={inputRef}
              type="text"
              placeholder="Search conversations and missions..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="flex-1 bg-transparent border-none outline-none text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-500 text-lg"
            />
            <button 
              type="button"
              onClick={handleClose}
              className="p-1 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-400 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <div className="p-2 max-h-[60vh] overflow-y-auto custom-scrollbar">
            <AnimatePresence mode="wait">
              {query.trim() === "" ? (
                <motion.div 
                  key="initial"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="py-4 px-2"
                >
                  <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-zinc-500 px-3 mb-2">Recent Missions</p>
                  <div className="space-y-1">
                    {[
                      { text: "Research competitor pricing", icon: Clock },
                      { text: "Fix typescript errors in frontend", icon: Clock },
                      { text: "Deployment status", icon: Clock },
                    ].map((item, i) => (
                      <button
                        key={i}
                        type="button"
                        onClick={() => setQuery(item.text)}
                        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-zinc-100 dark:hover:bg-zinc-800/50 text-zinc-600 dark:text-zinc-400 transition-colors text-left group"
                      >
                        <item.icon className="w-4 h-4 shrink-0 text-zinc-400 group-hover:text-indigo-500" />
                        <span className="text-sm">{item.text}</span>
                      </button>
                    ))}
                  </div>

                  <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-zinc-500 px-3 mt-6 mb-2">Quick Actions</p>
                  <div className="space-y-1">
                    <Link
                      href="/history"
                      onClick={handleClose}
                      className="flex items-center justify-between px-3 py-2.5 rounded-xl hover:bg-zinc-100 dark:hover:bg-zinc-800/50 text-zinc-600 dark:text-zinc-400 transition-colors group"
                    >
                      <div className="flex items-center gap-3">
                        <History className="w-4 h-4 text-zinc-400 group-hover:text-indigo-500" />
                        <span className="text-sm">View all history</span>
                      </div>
                      <ArrowRight className="w-4 h-4 opacity-0 group-hover:opacity-100 transition-all translate-x-[-10px] group-hover:translate-x-0" />
                    </Link>
                  </div>
                </motion.div>
              ) : results.length > 0 ? (
                <motion.div 
                  key="results"
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-1 py-2"
                >
                  <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-zinc-500 px-3 mb-2">Search Results</p>
                  {results.map((session) => (
                    <button
                      key={session.session_id}
                      onClick={() => navigateToSession(session.session_id)}
                      className="w-full flex flex-col gap-1 px-4 py-3 rounded-xl hover:bg-indigo-500/5 dark:hover:bg-indigo-500/10 border border-transparent hover:border-indigo-500/20 transition-all text-left group"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 group-hover:text-indigo-500 transition-colors truncate">
                          {session.title || "Untitled Conversation"}
                        </span>
                        <div className="flex items-center gap-1.5 shrink-0 ml-4">
                          <Calendar className="w-3 h-3 text-zinc-400" />
                          <span className="text-[10px] font-medium text-zinc-500">{formatTime(session.updated_at || session.created_at)}</span>
                        </div>
                      </div>
                      {session.summary && (
                        <p className="text-xs text-zinc-500 dark:text-zinc-500 line-clamp-1 italic">
                          {session.summary}
                        </p>
                      )}
                    </button>
                  ))}
                  
                  <div className="mt-2 pt-2 border-t border-zinc-100 dark:border-white/5">
                    <button
                      type="submit"
                      className="w-full flex items-center justify-between px-4 py-2 text-xs text-indigo-500 hover:text-indigo-400 transition-colors"
                    >
                      <span>Show all results for &quot;{query}&quot;</span>
                      <ArrowRight className="w-3 h-3" />
                    </button>
                  </div>
                </motion.div>
              ) : !isLoading ? (
                <motion.div 
                  key="empty"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="py-12 flex flex-col items-center justify-center gap-3 text-center"
                >
                  <div className="w-12 h-12 rounded-full bg-zinc-100 dark:bg-zinc-800/50 flex items-center justify-center text-zinc-400">
                    <Search className="w-6 h-6" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">No matches found</p>
                    <p className="text-xs text-zinc-500 mt-1">Try a different keyword or check your spelling.</p>
                  </div>
                </motion.div>
              ) : null}
            </AnimatePresence>
          </div>
        </form>

        <div className="p-4 bg-zinc-50 dark:bg-zinc-900/50 border-t border-zinc-200 dark:border-white/10 flex items-center justify-between">
          <div className="flex items-center gap-4 text-zinc-500">
            <div className="flex items-center gap-1.5">
              <kbd className="px-1.5 py-0.5 rounded bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-white/10 text-[9px] font-mono shadow-sm">ESC</kbd>
              <span className="text-[10px] font-medium">Close</span>
            </div>
            <div className="flex items-center gap-1.5">
              <kbd className="px-1.5 py-0.5 rounded bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-white/10 text-[9px] font-mono shadow-sm">↵</kbd>
              <span className="text-[10px] font-medium">Navigate</span>
            </div>
          </div>
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-400">Mission Search</span>
        </div>
      </motion.div>
    </div>
  );
}
