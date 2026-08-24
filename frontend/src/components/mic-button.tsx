/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useCallback } from "react";

type Props = {
  isRecording: boolean;
  onStart: () => void;
  onStop: () => void;
  disabled: boolean;
};

export function MicButton({ isRecording, onStart, onStop, disabled }: Props) {
  const toggle = useCallback(() => {
    if (disabled) return;
    if (isRecording) {
      onStop();
    } else {
      onStart();
    }
  }, [disabled, isRecording, onStart, onStop]);

  /* Spacebar toggle (only when not focused on an input/textarea) */
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.code !== "Space") return;
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      e.preventDefault();
      toggle();
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [toggle]);

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={disabled}
      aria-label={isRecording ? "Stop recording" : "Start recording"}
      className={`
        relative flex items-center justify-center
        w-8 h-8 rounded-full
        transition-all duration-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/40
        ${
          disabled
            ? "text-zinc-400 dark:text-zinc-600 cursor-not-allowed"
            : isRecording
              ? "bg-red-500 text-white shadow-[0_0_12px_rgba(239,68,68,0.4)]"
              : "text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-200 hover:bg-zinc-200/50 dark:hover:bg-zinc-700/50 active:scale-95"
        }
      `}
    >
      {/* Recording indicator */}
      {isRecording && !disabled && (
        <>
          <span className="absolute inset-0 rounded-full border border-red-400 animate-pulse" />
          <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-red-500 rounded-full border-2 border-background dark:border-[#212126]" />
        </>
      )}

      {isRecording ? (
        <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
          <rect x="6" y="6" width="12" height="12" rx="1.5" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
          <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
          <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
          <line x1="12" y1="19" x2="12" y2="22" />
        </svg>
      )}
    </button>
  );
}
