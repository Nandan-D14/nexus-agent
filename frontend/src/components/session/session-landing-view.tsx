/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { motion } from "framer-motion";
import { ChatComposer } from "./chat-composer";
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
  return (
    <div className="flex-1 flex flex-col items-center relative p-6 pt-[25vh]">
      <div className="max-w-3xl w-full flex flex-col items-center gap-2">
        <div className="text-center relative py-2">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="flex flex-col items-center"
          >
            <span className="text-zinc-500 dark:text-zinc-500 text-[10px] font-medium tracking-[0.2em] uppercase mb-0.5">
              Welcome to
            </span>
            <h1 className="text-4xl md:text-5xl font-cursive text-indigo-500 dark:text-indigo-400 relative">
              CoComputer
              <motion.svg
                viewBox="0 0 100 20"
                className="absolute -bottom-2 left-0 w-full h-4 text-cyan-500/40 dark:text-cyan-400/30"
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 1, delay: 0.5 }}
              >
                <path
                  d="M5 15 Q 50 5 95 15"
                  fill="transparent"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              </motion.svg>
            </h1>
          </motion.div>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3 }}
            className="mt-8 text-base md:text-lg text-zinc-400 dark:text-zinc-500 font-cursive italic"
          >
            &quot;the art of automation&quot;
          </motion.p>
        </div>

        {/* Search & Input Area */}
        <div className="w-full max-w-3xl mx-auto mt-4 px-4">
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
        </div>
      </div>

      {(pageError || error) && (
        <div className="absolute bottom-4 border border-red-500/20 bg-red-950/20 px-4 py-2 text-sm text-red-300 rounded-lg">
          {pageError || error}
        </div>
      )}
      {isLoading && (
        <div className="absolute bottom-4 border border-card-border dark:border-[#1c1c1e] bg-card dark:bg-[#09090b] px-4 py-2 text-sm text-muted dark:text-zinc-500 rounded-lg">
          Loading session...
        </div>
      )}
    </div>
  );
}
