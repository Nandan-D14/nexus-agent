"use client";

import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle2, Circle, ListTodo, Check } from "lucide-react";

export type TodoItem = {
  title: string;
  status: "pending" | "in_progress" | "done";
  note?: string;
};

interface TodoListProps {
  items: TodoItem[];
}

export function TodoList({ items }: TodoListProps) {
  if (!items || items.length === 0) return null;

  return (
    <div className="w-full mb-6">
      <div className="flex items-center gap-2 mb-3 px-1">
        <ListTodo className="w-4 h-4 text-zinc-400" />
        <span className="text-xs font-semibold text-zinc-300 tracking-tight">Agent Plan</span>
      </div>
      
      <div className="flex flex-col gap-1.5">
        <AnimatePresence mode="popLayout">
          {items.map((item, index) => (
            <motion.div
              key={`${item.title}-${index}`}
              initial={{ opacity: 0, y: 10, filter: "blur(2px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.25, delay: index * 0.05, ease: "easeOut" }}
              className={`group relative flex items-start gap-3 p-3 rounded-lg border transition-all duration-300 ${
                item.status === "done"
                  ? "bg-[#161618]/50 border-zinc-800/50"
                  : item.status === "in_progress"
                  ? "bg-[#1c1c1f] border-zinc-700/60 shadow-sm"
                  : "bg-[#111114]/50 border-transparent hover:bg-[#161618]"
              }`}
            >
              <div className="mt-0.5 shrink-0">
                {item.status === "done" ? (
                  <div className="w-4 h-4 rounded-full bg-emerald-500/20 flex items-center justify-center">
                    <Check className="w-2.5 h-2.5 text-emerald-400" strokeWidth={3} />
                  </div>
                ) : item.status === "in_progress" ? (
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
                    className="w-4 h-4 rounded-full border-[1.5px] border-zinc-700 border-t-zinc-300"
                  />
                ) : (
                  <div className="w-4 h-4 rounded-full border-[1.5px] border-zinc-800" />
                )}
              </div>
              
              <div className="flex-1 min-w-0 flex flex-col justify-center min-h-[20px]">
                <div className={`text-[13px] leading-tight ${
                  item.status === "done" ? "text-zinc-500 line-through" : item.status === "in_progress" ? "text-zinc-200 font-medium" : "text-zinc-400"
                }`}>
                  {item.title}
                </div>
                {item.note && (
                  <div className="mt-1 text-[11px] text-zinc-500/80 leading-relaxed">
                    {item.note}
                  </div>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
