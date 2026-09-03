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
    <div className="relative flex flex-1 flex-col items-center overflow-x-hidden overflow-y-auto p-6 pt-[14vh] pb-10 md:pt-[18vh]">
      <div className="relative z-10 flex w-full max-w-3xl flex-col items-center gap-6">
        <div className="relative py-2 text-center">
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, ease: "easeOut" }}
            className="flex flex-col items-center"
          >
            <span className="mb-2 text-[11px] font-semibold uppercase tracking-[0.38em] text-white drop-shadow-[0_1px_8px_rgba(0,0,0,0.55)]">
              Welcome to
            </span>
            <h1 className="relative font-cursive text-5xl font-semibold tracking-tight text-white drop-shadow-[0_2px_18px_rgba(0,0,0,0.45)] md:text-6xl">
              CoComputer
              <motion.svg
                viewBox="0 0 100 20"
                className="absolute -bottom-3 left-1/2 h-5 w-[92%] -translate-x-1/2 text-sky-300"
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 1, delay: 0.35 }}
              >
                <path
                  d="M5 15 Q 50 5 95 15"
                  fill="transparent"
                  stroke="currentColor"
                  strokeWidth="2.4"
                  strokeLinecap="round"
                />
              </motion.svg>
            </h1>
          </motion.div>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.28 }}
            className="mt-8 font-cursive text-lg italic text-white drop-shadow-[0_1px_10px_rgba(0,0,0,0.5)] md:text-xl"
          >
            &quot;the art of automation&quot;
          </motion.p>
        </div>

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
