/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { FileCode } from "lucide-react";

import {
  fileNameFromPath,
  languageFromPath,
  type EditorSessionState,
} from "@/lib/sandbox-session";

type Props = {
  session: EditorSessionState | null;
};

export function SandboxEditorPane({ session }: Props) {
  const path = session?.path || "untitled";
  const content = session?.content || "";
  const running = session?.running ?? false;
  const action = session?.action || "write";
  const lines = content.length ? content.split("\n") : [""];
  const fileName = fileNameFromPath(path);
  const language = languageFromPath(path);
  const verb =
    action === "read" ? "Reading" : session?.append ? "Appending" : "Writing";

  return (
    <div className="flex h-full flex-col bg-[#0c0c0d] text-zinc-100">
      <div className="flex items-center justify-between gap-3 border-b border-zinc-800/80 bg-[#141416] px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <FileCode className="h-3.5 w-3.5 shrink-0 text-zinc-400" />
          <span className="truncate text-[12px] font-medium text-zinc-200">
            CoComputer is using Editor
          </span>
        </div>
        <span className="min-w-0 truncate font-mono text-[11px] text-zinc-500">
          {verb} {path}
          {running ? "…" : ""}
        </span>
      </div>

      <div className="flex items-center gap-1 border-b border-zinc-800/60 bg-[#101012] px-3 pt-2">
        <div className="rounded-t-md border border-b-0 border-zinc-700 bg-[#17171a] px-3 py-1.5 text-[11px] font-medium text-zinc-200">
          {fileName}
          <span className="ml-2 font-mono text-[10px] uppercase tracking-wide text-zinc-500">
            {language}
          </span>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {content || running ? (
          <div className="flex min-h-full font-mono text-[12px] leading-6">
            <div className="select-none border-r border-zinc-800/80 bg-[#101012] px-3 py-3 text-right text-zinc-600">
              {lines.map((_, index) => (
                <div key={index}>{index + 1}</div>
              ))}
            </div>
            <pre className="flex-1 whitespace-pre-wrap break-words px-4 py-3 text-zinc-200">
              {content || (running ? "" : "")}
              {running ? (
                <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-zinc-200 align-middle" />
              ) : null}
            </pre>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-[13px] text-zinc-500">
            No file preview
          </div>
        )}
      </div>

      {typeof session?.bytesWritten === "number" && !running ? (
        <div className="border-t border-zinc-800/80 px-4 py-1.5 font-mono text-[10px] text-zinc-500">
          {session.bytesWritten} bytes
          {session.append ? " · append" : ""}
        </div>
      ) : null}
    </div>
  );
}
