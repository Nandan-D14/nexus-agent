"use client";

import { useEffect, useState, useRef } from "react";
import { Search, X, Clock, ArrowRight, MessageSquare, History } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";

type SearchModalProps = {
  isOpen: boolean;
  onClose: () => void;
};

export function SearchModal({ isOpen, onClose }: SearchModalProps) {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (isOpen) {
      setQuery("");
      const timer = setTimeout(() => inputRef.current?.focus(), 100);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  if (!isOpen) return null;

  const performSearch = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    
    const target = `/history?q=${encodeURIComponent(trimmed)}`;
    if (pathname === "/history") {
      router.replace(target);
    } else {
      router.push(target);
    }
    onClose();
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    performSearch(query);
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[10vh] px-4">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="fixed inset-0 bg-zinc-950/40 backdrop-blur-sm"
      />
      
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: -20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: -20 }}
        className="w-full max-w-2xl bg-white dark:bg-[#1a1a1c] rounded-2xl shadow-2xl border border-zinc-200 dark:border-white/10 overflow-hidden relative z-10"
      >
        <form onSubmit={handleSearch}>
          <div className="p-4 border-b border-zinc-200 dark:border-white/10 flex items-center gap-3">
            <Search className="w-5 h-5 text-zinc-400" />
            <input
              ref={inputRef}
              type="text"
              placeholder="Search missions, tools, or templates..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="flex-1 bg-transparent border-none outline-none text-zinc-900 dark:text-zinc-100 placeholder-zinc-500 text-lg"
            />
            <button 
              type="button"
              onClick={onClose}
              className="p-1 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-400 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <div className="p-2 max-h-[60vh] overflow-y-auto">
            {query.trim() === "" ? (
              <div className="py-4 px-2">
                <p className="text-[11px] font-bold uppercase tracking-widest text-zinc-500 px-3 mb-2">Recent Searches</p>
                <div className="space-y-1">
                  {[
                    { text: "Research competitor pricing", icon: Clock },
                    { text: "Fix typescript errors in frontend", icon: Clock },
                    { text: "Deployment status", icon: Clock },
                  ].map((item, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => performSearch(item.text)}
                      className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-zinc-100 dark:hover:bg-zinc-800/50 text-zinc-600 dark:text-zinc-400 transition-colors text-left"
                    >
                      <item.icon className="w-4 h-4 shrink-0" />
                      <span className="text-sm">{item.text}</span>
                    </button>
                  ))}
                </div>

                <p className="text-[11px] font-bold uppercase tracking-widest text-zinc-500 px-3 mt-6 mb-2">Quick Actions</p>
                <div className="space-y-1">
                  <Link
                    href="/history"
                    onClick={onClose}
                    className="flex items-center justify-between px-3 py-2.5 rounded-xl hover:bg-zinc-100 dark:hover:bg-zinc-800/50 text-zinc-600 dark:text-zinc-400 transition-colors group"
                  >
                    <div className="flex items-center gap-3">
                      <History className="w-4 h-4" />
                      <span className="text-sm">View mission history</span>
                    </div>
                    <ArrowRight className="w-4 h-4 opacity-0 group-hover:opacity-100 transition-opacity" />
                  </Link>
                  <Link
                    href="/dashboard"
                    onClick={onClose}
                    className="flex items-center justify-between px-3 py-2.5 rounded-xl hover:bg-zinc-100 dark:hover:bg-zinc-800/50 text-zinc-600 dark:text-zinc-400 transition-colors group"
                  >
                    <div className="flex items-center gap-3">
                      <MessageSquare className="w-4 h-4" />
                      <span className="text-sm">Go to Chat Console</span>
                    </div>
                    <ArrowRight className="w-4 h-4 opacity-0 group-hover:opacity-100 transition-opacity" />
                  </Link>
                </div>
              </div>
            ) : (
              <div className="py-2">
                  <button
                      type="submit"
                      className="w-full flex items-center justify-between px-4 py-3 rounded-xl bg-zinc-100 dark:bg-zinc-800/50 text-zinc-900 dark:text-zinc-100 transition-colors hover:bg-zinc-200 dark:hover:bg-zinc-800"
                  >
                      <div className="flex items-center gap-3">
                          <Search className="w-4 h-4 text-indigo-500" />
                          <span className="text-sm font-medium">Search for "{query}"</span>
                      </div>
                      <span className="text-[10px] bg-zinc-200 dark:bg-zinc-700 px-1.5 py-0.5 rounded uppercase font-bold tracking-tighter">Enter</span>
                  </button>
              </div>
            )}
          </div>
        </form>

        <div className="p-4 bg-zinc-50 dark:bg-zinc-900/50 border-t border-zinc-200 dark:border-white/10 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5">
              <span className="px-1.5 py-0.5 rounded bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-white/10 text-[10px] font-mono shadow-sm">ESC</span>
              <span className="text-[10px] text-zinc-500 font-medium">Close</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="px-1.5 py-0.5 rounded bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-white/10 text-[10px] font-mono shadow-sm">↵</span>
              <span className="text-[10px] text-zinc-500 font-medium">Select</span>
            </div>
          </div>
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-400">CoComputer Search</span>
        </div>
      </motion.div>
    </div>
  );
}
