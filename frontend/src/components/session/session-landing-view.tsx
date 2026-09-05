/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useCallback } from "react";
import { motion } from "framer-motion";
import { ChatComposer } from "./chat-composer";
import { LandingPromptStarters } from "./landing-prompt-starters";
import type { SessionConnector } from "@/lib/session-utils";
import type { UploadedInputFile } from "@/lib/message-types";

type Props = {
  onShowDesktop: () => void;
  textInput: string;
  onChangeText: (text: string) => void;
  onSubmitText: () => void;
  onOpenFilePicker: (kind?: "image" | "file") => void;
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
  agentRunning?: boolean;
  availableConnectors: SessionConnector[];
  selectedConnectorIds: string[];
  onToggleConnector: (id: string) => void;
  onToggleAllConnectors: (ids: string[]) => void;
  selectedToolIds: string[];
  onToggleTool: (id: string) => void;
  onToggleAllTools: (ids: string[]) => void;
  connectorsLoading?: boolean;
  onRefreshTools?: () => void;
  pageError: string | null;
  error: string | null;
  landingInputRef?: React.RefObject<HTMLDivElement | null>;
};

export function SessionLandingView({
  onShowDesktop,
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
  agentRunning = false,
  availableConnectors,
  selectedConnectorIds,
  onToggleConnector,
  onToggleAllConnectors,
  selectedToolIds,
  onToggleTool,
  onToggleAllTools,
  connectorsLoading,
  onRefreshTools,
  pageError,
  error,
  landingInputRef,
}: Props) {
  const insertPrompt = useCallback(
    (prompt: string) => {
      onChangeText(prompt);
      const editor = landingInputRef?.current;
      if (!editor) return;
      editor.textContent = prompt;
      editor.dispatchEvent(new InputEvent("input", { bubbles: true }));
      editor.focus();
      const range = document.createRange();
      range.selectNodeContents(editor);
      range.collapse(false);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
    },
    [landingInputRef, onChangeText],
  );

  return (
    <div className="relative flex flex-1 flex-col items-center justify-center overflow-x-hidden overflow-y-auto p-6 py-10">
      <div className="relative z-10 flex w-full max-w-3xl flex-col items-center gap-6">
        <motion.h1
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: "easeOut" }}
          className="py-2 text-center font-serif text-5xl tracking-tight text-white drop-shadow-[0_2px_18px_rgba(0,0,0,0.45)] md:text-6xl"
        >
          From ideas to{" "}
          <span className="bg-gradient-to-r from-sky-400 to-cyan-300 bg-clip-text text-transparent">
            impact
          </span>
          .
        </motion.h1>

        <div className="mx-auto mt-2 flex w-full max-w-3xl flex-col gap-4 px-4">
          <ChatComposer
            isLanding
            inputRef={landingInputRef}
            textInput={textInput}
            onChangeText={onChangeText}
            onSubmitText={onSubmitText}
            onOpenFilePicker={onOpenFilePicker}
            uploadDisabled={uploadDisabled}
            uploadedFiles={uploadedFiles}
            onRemoveFile={onRemoveFile}
            onToggleMic={onToggleMic}
            isRecording={isRecording}
            voiceStatus={voiceStatus}
            phase={phase}
            isLoading={isLoading}
            isUploadingFile={isUploadingFile}
            onStopAgent={onStopAgent}
            agentRunning={agentRunning}
            onShowDesktop={onShowDesktop}
            availableConnectors={availableConnectors}
            selectedConnectorIds={selectedConnectorIds}
            onToggleConnector={onToggleConnector}
            onToggleAllConnectors={onToggleAllConnectors}
            selectedToolIds={selectedToolIds}
            onToggleTool={onToggleTool}
            onToggleAllTools={onToggleAllTools}
            connectorsLoading={connectorsLoading}
            onRefreshTools={onRefreshTools}
          />
          <LandingPromptStarters onInsertPrompt={insertPrompt} />
        </div>
      </div>
    </div>
  );
}
