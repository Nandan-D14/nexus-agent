"use client";

import { useState, useCallback } from "react";

type Props = {
  onCreateSession: () => void;
  onDestroySession: () => void;
  isLoading: boolean;
  hasSession: boolean;
};

export function SessionControls({
  onCreateSession,
  onDestroySession,
  isLoading,
  hasSession,
}: Props) {
  const [confirmDestroy, setConfirmDestroy] = useState(false);

  const handleDestroy = useCallback(() => {
    if (!confirmDestroy) {
      setConfirmDestroy(true);
      return;
    }
    setConfirmDestroy(false);
    onDestroySession();
  }, [confirmDestroy, onDestroySession]);

  const handleCancelDestroy = useCallback(() => {
    setConfirmDestroy(false);
  }, []);

  /* ---- Loading state ---- */
  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-3">
        {/* Spinner */}
        <svg
          className="animate-spin h-5 w-5 text-[#22d3ee]"
          viewBox="0 0 24 24"
          fill="none"
        >
          <circle
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="3"
            className="opacity-20"
          />
          <path
            d="M12 2a10 10 0 0 1 10 10"
            stroke="currentColor"
            strokeWidth="3"
            strokeLinecap="round"
          />
        </svg>
        <span className="text-sm text-zinc-400">
          {hasSession ? "Shutting down..." : "Launching CoComputer..."}
        </span>
      </div>
    );
  }

  /* ---- No session: Launch button ---- */
  if (!hasSession) {
    return (
      <button
        type="button"
        onClick={onCreateSession}
        className="
          relative group w-full max-w-sm mx-auto flex items-center justify-center gap-2.5
          px-8 py-4 rounded-xl font-semibold text-base
          bg-gradient-to-r from-[#22d3ee] to-cyan-600
          text-[#09090b]
          shadow-[0_0_32px_rgba(34,211,238,0.25)]
          hover:shadow-[0_0_48px_rgba(34,211,238,0.4)]
          hover:scale-[1.02]
          active:scale-[0.98]
          transition-all duration-200
          focus:outline-none focus-visible:ring-2 focus-visible:ring-[#22d3ee]/50
        "
      >
        {/* Rocket icon */}
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          className="w-5 h-5"
        >
          <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09Z" />
          <path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2Z" />
          <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0" />
          <path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5" />
        </svg>
        Launch CoComputer
      </button>
    );
  }

  /* ---- Active session: End button with confirm ---- */
  return (
    <div className="flex items-center gap-2">
      {confirmDestroy ? (
        <>
          <span className="text-sm text-red-400">End this session?</span>
          <button
            type="button"
            onClick={handleDestroy}
            className="
              px-3 py-1.5 rounded-lg text-xs font-semibold
              bg-red-600 text-white
              hover:bg-red-500
              transition-colors duration-150
              focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500/50
            "
          >
            Confirm
          </button>
          <button
            type="button"
            onClick={handleCancelDestroy}
            className="
              px-3 py-1.5 rounded-lg text-xs font-medium
              text-zinc-400 hover:text-zinc-200
              transition-colors duration-150
              focus:outline-none
            "
          >
            Cancel
          </button>
        </>
      ) : (
        <button
          type="button"
          onClick={handleDestroy}
          className="
            flex items-center gap-1.5
            px-3.5 py-1.5 rounded-lg text-xs font-semibold
            border border-red-600/50 text-red-400
            hover:bg-red-600/10 hover:border-red-500
            transition-all duration-150
            focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500/50
          "
        >
          {/* Power-off icon */}
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            className="w-3.5 h-3.5"
          >
            <path d="M18.36 6.64a9 9 0 1 1-12.73 0" />
            <line x1="12" y1="2" x2="12" y2="12" />
          </svg>
          End Session
        </button>
      )}
    </div>
  );
}
