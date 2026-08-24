/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useEffect, useRef } from "react";
import { Terminal } from "lucide-react";

import type { TerminalSessionState } from "@/lib/sandbox-session";

type Props = {
  session: TerminalSessionState | null;
};

function truncateCommand(command: string, limit = 72): string {
  const text = command.trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, limit - 1)}…`;
}

export function SandboxTerminalPane({ session }: Props) {
  const scrollerRef = useRef<HTMLPreElement>(null);
  const running = session?.running ?? false;
  const command = session?.command || "";
  const cwd = session?.cwd || "~";
  const stdout = session?.stdout || "";
  const stderr = session?.stderr || "";
  const exitCode = session?.exitCode ?? null;

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [stdout, stderr, running, command]);

  const body = [stdout, stderr].filter(Boolean).join(stdout && stderr ? "\n" : "");

  return (
    <div className="flex h-full flex-col bg-[#0c0c0d] text-zinc-100">
      <div className="flex items-center justify-between gap-3 border-b border-zinc-800/80 bg-[#141416] px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <Terminal className="h-3.5 w-3.5 shrink-0 text-zinc-400" />
          <span className="truncate text-[12px] font-medium text-zinc-200">
            CoComputer is using Terminal
          </span>
        </div>
        <span className="min-w-0 truncate font-mono text-[11px] text-zinc-500">
          {running
            ? `Executing command ${truncateCommand(command) || "…"}`
            : command
              ? truncateCommand(command)
              : "Idle"}
        </span>
      </div>

      <pre
        ref={scrollerRef}
        className="min-h-0 flex-1 overflow-auto px-4 py-3 font-mono text-[12px] leading-6 text-zinc-200"
      >
        <span className="text-emerald-400">ubuntu@sandbox</span>
        <span className="text-zinc-500">:</span>
        <span className="text-sky-400">{cwd}</span>
        <span className="text-zinc-500">$ </span>
        <span className="text-zinc-100">{command || (running ? "" : "—")}</span>
        {command ? "\n" : ""}
        {body}
        {running ? <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-zinc-200 align-middle" /> : null}
        {!running && typeof exitCode === "number" ? (
          <span className={`mt-3 block text-[11px] ${exitCode === 0 ? "text-emerald-400" : "text-red-400"}`}>
            Exit {exitCode}
          </span>
        ) : null}
      </pre>
    </div>
  );
}
