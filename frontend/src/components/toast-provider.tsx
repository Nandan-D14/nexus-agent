/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import React, {
  createContext,
  useContext,
  useCallback,
  useMemo,
  useState,
  useEffect,
  ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  CheckCircle2,
  AlertCircle,
  Info,
  AlertTriangle,
  X,
} from "lucide-react";

export type ToastType = "success" | "error" | "info" | "warning";

export interface ToastItem {
  id: string;
  message: string;
  type: ToastType;
  duration?: number;
}

export interface ToastContextType {
  toast: ((message: string, type?: ToastType) => void) & {
    success?: (message: string) => void;
    error?: (message: string) => void;
    info?: (message: string) => void;
    warning?: (message: string) => void;
  };
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

const TOAST_TIMEOUT_MS: Record<ToastType, number> = {
  error: 4500,
  success: 3500,
  info: 3500,
  warning: 4000,
};

const ICONS = {
  success: CheckCircle2,
  error: AlertCircle,
  info: Info,
  warning: AlertTriangle,
};

const ICON_COLORS = {
  success: "text-emerald-500 dark:text-emerald-400 bg-emerald-500/10 dark:bg-emerald-500/15 border-emerald-500/20",
  error: "text-rose-500 dark:text-rose-400 bg-rose-500/10 dark:bg-rose-500/15 border-rose-500/20",
  info: "text-sky-500 dark:text-sky-400 bg-sky-500/10 dark:bg-sky-500/15 border-sky-500/20",
  warning: "text-amber-500 dark:text-amber-400 bg-amber-500/10 dark:bg-amber-500/15 border-amber-500/20",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback(
    (message: string, type: ToastType = "info", duration?: number) => {
      if (!message) return;
      const id = `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
      const timeoutDuration = duration ?? TOAST_TIMEOUT_MS[type] ?? 3500;

      setToasts((prev) => [...prev.slice(-4), { id, message, type, duration: timeoutDuration }]);

      setTimeout(() => {
        removeToast(id);
      }, timeoutDuration);
    },
    [removeToast]
  );

  const toastFn = useMemo(() => {
    const fn = (message: string, type?: ToastType) => showToast(message, type);
    fn.success = (message: string) => showToast(message, "success");
    fn.error = (message: string) => showToast(message, "error");
    fn.info = (message: string) => showToast(message, "info");
    fn.warning = (message: string) => showToast(message, "warning");
    return fn;
  }, [showToast]);

  const value = useMemo(() => ({ toast: toastFn }), [toastFn]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      {mounted &&
        createPortal(
          <div
            aria-live="polite"
            className="fixed top-5 right-5 z-[99999] flex flex-col gap-2.5 max-w-sm sm:max-w-md w-full pointer-events-none px-4 sm:px-0"
          >
            <AnimatePresence mode="popLayout">
              {toasts.map((item) => {
                const IconComponent = ICONS[item.type] || Info;
                const iconColor = ICON_COLORS[item.type] || ICON_COLORS.info;

                return (
                  <motion.div
                    key={item.id}
                    layout
                    initial={{ opacity: 0, y: -16, scale: 0.95 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: -12, scale: 0.95, transition: { duration: 0.15 } }}
                    transition={{ type: "spring", stiffness: 400, damping: 30 }}
                    className="pointer-events-auto flex items-start gap-3 w-full p-3.5 rounded-2xl bg-white/95 dark:bg-[#18181b]/95 backdrop-blur-md border border-zinc-200/80 dark:border-zinc-800/80 shadow-[0_8px_30px_rgb(0,0,0,0.08)] dark:shadow-[0_8px_30px_rgb(0,0,0,0.4)] text-zinc-900 dark:text-zinc-100"
                  >
                    <div
                      className={`flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-xl border ${iconColor}`}
                    >
                      <IconComponent className="w-4 h-4" />
                    </div>

                    <div className="flex-1 pt-1 min-w-0 pr-1">
                      <p className="text-sm font-medium leading-snug break-words">
                        {item.message}
                      </p>
                    </div>

                    <button
                      type="button"
                      onClick={() => removeToast(item.id)}
                      className="flex-shrink-0 p-1 -mr-1 -mt-1 rounded-lg text-zinc-400 hover:text-zinc-700 dark:text-zinc-500 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800/60 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400"
                      aria-label="Dismiss toast"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          </div>,
          document.body
        )}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (context === undefined) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}
