"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ListTodo, Check, CircleDashed, ChevronDown, ChevronUp, X } from "lucide-react";
import { cn } from "@/lib/utils";

export type TodoItem = {
  title: string;
  status: "pending" | "in_progress" | "done";
  note?: string;
};

interface TodoListProps {
  items: TodoItem[];
  defaultExpanded?: boolean;
}

export function TodoList({ items, defaultExpanded = false }: TodoListProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  if (!items || items.length === 0) return null;

  const total = items.length;
  const completed = items.filter((i) => i.status === "done").length;
  const inProgress = items.filter((i) => i.status === "in_progress").length;
  const progress = Math.round((completed / total) * 100);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "done":
        return <Check className="w-3.5 h-3.5 text-emerald-400" strokeWidth={3} />;
      case "in_progress":
        return <CircleDashed className="w-3.5 h-3.5 text-indigo-400 animate-spin" />;
      default:
        return <div className="w-3.5 h-3.5 rounded-full border border-zinc-600" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "done":
        return "text-zinc-500 line-through";
      case "in_progress":
        return "text-zinc-100";
      default:
        return "text-zinc-400";
    }
  };

  return (
    <div className="w-full mb-6 select-none">
      {/* Header - Always visible */}
      <div className="flex items-center justify-between px-2 py-2 rounded-lg hover:bg-zinc-800/30 transition-colors">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-2 flex-1 text-left"
        >
          <div className="w-6 h-6 rounded-md bg-zinc-900 border border-zinc-800 flex items-center justify-center">
            <ListTodo className="w-3.5 h-3.5 text-indigo-400" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="text-[13px] font-medium text-zinc-200">Tasks</span>
              <span className="text-[11px] text-zinc-500">{completed}/{total}</span>
              {inProgress > 0 && (
                <span className="text-[11px] text-indigo-400">{inProgress} active</span>
              )}
            </div>
            <div className="w-full h-1 bg-zinc-800/50 rounded-full mt-1 overflow-hidden">
              <motion.div
                className={cn("h-full rounded-full", progress === 100 ? "bg-emerald-500" : "bg-indigo-500")}
                initial={{ width: 0 }}
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.5 }}
              />
            </div>
          </div>
          {isExpanded ? (
            <ChevronUp className="w-4 h-4 text-zinc-500" />
          ) : (
            <ChevronDown className="w-4 h-4 text-zinc-500" />
          )}
        </button>
      </div>

      {/* Tasks - Collapsible */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="mt-1 space-y-0.5 pl-8 pr-2">
              {items.map((item, index) => (
                <motion.div
                  key={`${item.title}-${index}`}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.03 }}
                  className="flex items-start gap-2.5 py-1.5 px-2 rounded-md hover:bg-zinc-800/20 transition-colors"
                >
                  <div className="mt-0.5 shrink-0">{getStatusIcon(item.status)}</div>
                  <div className="flex-1 min-w-0">
                    <span className={cn("text-[13px]", getStatusColor(item.status))}>
                      {item.title}
                    </span>
                    {item.note && (
                      <div className="text-[11px] text-zinc-500 mt-0.5 line-clamp-2">
                        {item.note}
                      </div>
                    )}
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
