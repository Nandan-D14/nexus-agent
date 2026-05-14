/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useRef, useLayoutEffect, type KeyboardEvent } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Plus, Monitor, Mic, ArrowUp, Square, Paperclip, X } from "lucide-react";
import { ToolPicker } from "./tool-picker";
import type { SessionConnector } from "@/lib/session-utils";
import type { UploadedInputFile } from "@/lib/message-types";

type Props = {
  textInput: string;
  onChangeText: (text: string) => void;
  onSubmitText: () => void;
  onOpenFilePicker: () => void;
  uploadDisabled: boolean;
  uploadedFiles: UploadedInputFile[];
  onRemoveFile: (path: string) => void;
  onToggleMic: () => void;
  isRecording: boolean;
  voiceStatus: string;
  phase: string;
  isLoading: boolean;
  isUploadingFile: boolean;
  onStopAgent: () => void;
  onShowDesktop: () => void;
  availableConnectors: SessionConnector[];
  selectedConnectorIds: string[];
  onToggleConnector: (id: string) => void;
  onToggleAllConnectors: (ids: string[]) => void;
  isLanding?: boolean;
  inputRef?: React.RefObject<HTMLTextAreaElement | null>;
};

export function ChatComposer({
  textInput,
  onChangeText,
  onSubmitText,
  onOpenFilePicker,
  uploadDisabled,
  uploadedFiles,
  onRemoveFile,
  onToggleMic,
  isRecording,
  voiceStatus,
  phase,
  isLoading,
  isUploadingFile,
  onStopAgent,
  onShowDesktop,
  availableConnectors,
  selectedConnectorIds,
  onToggleConnector,
  onToggleAllConnectors,
  isLanding = false,
  inputRef: externalInputRef,
}: Props) {
  const localInputRef = useRef<HTMLTextAreaElement>(null);
  const inputRef = externalInputRef || localInputRef;

  useLayoutEffect(() => {
    const maxHeight = 200;
    const el = inputRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
    }
  }, [textInput, inputRef]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmitText();
    }
  };

  const isBusy = phase === "thinking" || phase === "acting";

  return (
    <div className={`relative flex flex-col bg-white/80 dark:bg-white/[0.04] backdrop-blur-md border border-zinc-200/80 dark:border-white/8 rounded-[24px] p-1 shadow-2xl transition-all focus-within:border-indigo-500/30 ${isLanding ? "min-h-[120px]" : "min-h-[80px]"}`}>
      {/* Text input area */}
      <div className={`relative flex w-full items-start px-4 ${isLanding ? "py-3 min-h-[80px]" : "py-4 min-h-[80px]"}`}>
        <textarea
          suppressHydrationWarning
          ref={inputRef}
          value={textInput}
          onChange={(e) => onChangeText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Send message to CoComputer"
          rows={1}
          className={`w-full bg-transparent border-none p-0 outline-none text-zinc-900 dark:text-zinc-200 placeholder-zinc-500 focus:ring-0 resize-none overflow-y-auto no-scrollbar max-h-60 leading-relaxed placeholder:font-medium ${isLanding ? "text-[18px]" : "text-[18px]"}`}
        />
      </div>

      {/* File attachments */}
      {uploadedFiles.length > 0 && (
        <div className="flex flex-wrap gap-2 px-3 pb-1 mb-2">
          {uploadedFiles.map((file) => (
            <span
              key={file.path}
              className="inline-flex items-center gap-2 rounded-full border border-zinc-700 bg-zinc-800 px-3 py-1 text-xs text-zinc-200"
            >
              <Paperclip className="h-3.5 w-3.5" />
              <span className="max-w-44 truncate">{file.name}</span>
              <button
                type="button"
                onClick={() => onRemoveFile(file.path)}
                className="text-zinc-400 transition-colors hover:text-zinc-200"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Action bar */}
      <div className="flex items-center justify-between mt-1 px-2 pb-2">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onOpenFilePicker}
            disabled={uploadDisabled}
            className="p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded-full transition-colors flex items-center justify-center border border-zinc-700/50 disabled:opacity-40"
            title="Attach"
          >
            <Plus className="w-4 h-4" />
          </button>

          <ToolPicker
            availableConnectors={availableConnectors}
            selectedConnectorIds={selectedConnectorIds}
            onToggleConnector={onToggleConnector}
            onToggleAll={onToggleAllConnectors}
          />

          <button
            type="button"
            onClick={onShowDesktop}
            className="p-1.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded transition-colors"
            title="Workspace Context"
          >
            <Monitor className="w-4 h-4" />
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onToggleMic}
            disabled={voiceStatus !== "connected"}
            className={`p-1.5 rounded transition-colors ${
              isRecording
                ? "text-red-400 bg-red-500/10"
                : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
            } disabled:opacity-40`}
            title="Voice Input"
          >
            <Mic className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={isBusy ? onStopAgent : onSubmitText}
            disabled={
              !isBusy && (!textInput.trim() || isLoading || isUploadingFile)
            }
            className={`p-1.5 rounded-full transition-colors border border-zinc-700/50 ${
              isBusy
                ? "bg-red-500/10 text-red-500 border-red-500/30 hover:bg-red-500/20"
                : textInput.trim() && !isLoading && !isUploadingFile
                ? "bg-[#3a3a3c] text-indigo-400 hover:bg-indigo-500"
                : "bg-zinc-800 text-zinc-500 cursor-not-allowed opacity-50"
            }`}
            title={isBusy ? "Stop" : "Send"}
          >
            {isBusy ? (
              <Square className="w-4 h-4 fill-current" />
            ) : (
              <ArrowUp className="w-4 h-4" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
