/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

"use client";

import { useRef, useLayoutEffect, useState, useEffect, type KeyboardEvent } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Plus, Monitor, Mic, ArrowUp, Square, Paperclip, X } from "lucide-react";
import { ToolPicker } from "./tool-picker";
import type { SessionConnector } from "@/lib/session-utils";
import type { UploadedInputFile } from "@/lib/message-types";
import { authenticatedFetch } from "@/lib/api-client";

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

type AgentSkill = {
  skill_id: string;
  name: string;
  category: string;
  description: string;
  trigger: string;
  instructions: string;
  source: "built_in" | "user";
  enabled: boolean;
};

type ToolItem = {
  id: string;
  name: string;
  description: string;
  category: "System" | "Integration";
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
  const highlightRef = useRef<HTMLDivElement>(null);

  const [skills, setSkills] = useState<AgentSkill[]>([]);
  const [showMenu, setShowMenu] = useState(false);
  const [menuFilter, setMenuFilter] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);

  const [showToolMenu, setShowToolMenu] = useState(false);
  const [toolFilter, setToolFilter] = useState("");
  const [selectedToolIndex, setSelectedToolIndex] = useState(0);

  useEffect(() => {
    async function loadSkills() {
      try {
        const response = await authenticatedFetch("/api/v1/skills");
        if (response.ok) {
          const body = (await response.json()) as { skills?: AgentSkill[] };
          setSkills((body.skills ?? []).filter((s) => s.enabled));
        }
      } catch (err) {
        console.error("Failed to load skills in ChatComposer:", err);
      }
    }
    void loadSkills();
  }, []);

  useLayoutEffect(() => {
    const maxHeight = 200;
    const el = inputRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
    }
  }, [textInput, inputRef]);

  const filteredSkills = skills.filter((skill) => {
    const needle = menuFilter.trim().toLowerCase();
    if (!needle) return true;
    return (
      skill.name.toLowerCase().includes(needle) ||
      skill.skill_id.toLowerCase().includes(needle) ||
      (skill.description || "").toLowerCase().includes(needle)
    );
  });

  const coreTools: ToolItem[] = [
    { id: "tavily_search", name: "Tavily Web Search", description: "AI-powered web search tool", category: "System" },
    { id: "web_search", name: "Google Web Search", description: "Standard search engine query", category: "System" },
    { id: "run_command", name: "Terminal Command", description: "Run shell/bash command inside sandbox", category: "System" },
    { id: "open_browser", name: "Sandbox Browser", description: "Interact via browser in sandbox", category: "System" },
    { id: "take_screenshot", name: "Take Screenshot", description: "Observe desktop screen visually", category: "System" },
    { id: "publish_html_artifact", name: "Publish HTML Artifact", description: "Build standalone HTML application", category: "System" },
  ];

  const integrationTools: ToolItem[] = availableConnectors
    .filter((conn) => conn.connection_id !== "system" && conn.enabled)
    .map((conn) => ({
      id: conn.connection_id,
      name: conn.name,
      description: `Access connector: ${conn.provider}`,
      category: "Integration",
    }));

  const allTools = [...coreTools, ...integrationTools];

  const filteredTools = allTools.filter((tool) => {
    const needle = toolFilter.trim().toLowerCase();
    if (!needle) return true;
    return (
      tool.name.toLowerCase().includes(needle) ||
      tool.id.toLowerCase().includes(needle) ||
      tool.description.toLowerCase().includes(needle)
    );
  });

  const selectSkill = (skill: AgentSkill) => {
    const words = textInput.split(/\s+/);
    words.pop();
    words.push(`/${skill.skill_id} `);
    onChangeText(words.join(" "));
    setShowMenu(false);
    setTimeout(() => {
      inputRef.current?.focus();
    }, 10);
  };

  const selectTool = (tool: ToolItem) => {
    const words = textInput.split(/\s+/);
    words.pop();
    words.push(`@[${tool.id}] `);
    onChangeText(words.join(" "));
    setShowToolMenu(false);
    setTimeout(() => {
      inputRef.current?.focus();
    }, 10);
  };

  const handleInputChange = (val: string) => {
    onChangeText(val);
    const words = val.split(/\s+/);
    const lastWord = words[words.length - 1] || "";
    if (lastWord.startsWith("/")) {
      setShowMenu(true);
      setMenuFilter(lastWord.slice(1));
      setSelectedIndex(0);
      setShowToolMenu(false);
    } else if (lastWord.startsWith("@")) {
      setShowToolMenu(true);
      setToolFilter(lastWord.slice(1));
      setSelectedToolIndex(0);
      setShowMenu(false);
    } else {
      setShowMenu(false);
      setShowToolMenu(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (showMenu && filteredSkills.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((prev) => (prev + 1) % filteredSkills.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((prev) => (prev - 1 + filteredSkills.length) % filteredSkills.length);
        return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        selectSkill(filteredSkills[selectedIndex]);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setShowMenu(false);
        return;
      }
    }

    if (showToolMenu && filteredTools.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedToolIndex((prev) => (prev + 1) % filteredTools.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedToolIndex((prev) => (prev - 1 + filteredTools.length) % filteredTools.length);
        return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        selectTool(filteredTools[selectedToolIndex]);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setShowToolMenu(false);
        return;
      }
    }

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmitText();
    }
  };

  const handleScroll = (e: React.UIEvent<HTMLTextAreaElement>) => {
    if (highlightRef.current) {
      highlightRef.current.scrollTop = e.currentTarget.scrollTop;
    }
  };

  const renderHighlightedText = (text: string) => {
    if (!text) return null;
    const parts = text.split(/(\s+)/);
    return parts.map((part, i) => {
      if (part.startsWith("/")) {
        return (
          <span key={i} className="text-indigo-600 dark:text-indigo-400 font-semibold bg-indigo-500/10 dark:bg-indigo-500/20 px-1.5 py-0.5 rounded-md inline-block">
            {part}
          </span>
        );
      }
      if (part.startsWith("@")) {
        return (
          <span key={i} className="text-emerald-600 dark:text-emerald-400 font-semibold bg-emerald-500/10 dark:bg-emerald-500/20 px-1.5 py-0.5 rounded-md inline-block">
            {part}
          </span>
        );
      }
      return <span key={i}>{part}</span>;
    });
  };

  const isBusy = phase === "thinking" || phase === "acting";

  return (
    <div className={`relative flex flex-col bg-white/80 dark:bg-white/[0.04] backdrop-blur-md border border-zinc-200/80 dark:border-white/8 rounded-[24px] p-1 shadow-2xl transition-all focus-within:border-indigo-500/30 ${isLanding ? "min-h-[120px]" : "min-h-[80px]"}`}>
      {/* Floating Skills Dropdown */}
      {showMenu && filteredSkills.length > 0 && (
        <div className="absolute bottom-full left-0 right-0 mb-3 z-50 px-4">
          <div className="border border-zinc-200/80 dark:border-white/8 bg-white/90 dark:bg-[#1c1c1e]/90 backdrop-blur-md shadow-2xl rounded-2xl p-1 max-h-60 overflow-y-auto no-scrollbar">
            <div className="flex flex-col gap-1" role="listbox" aria-label="Skills Command Menu">
              {filteredSkills.map((skill, index) => {
                const isSelected = index === selectedIndex;
                return (
                  <div
                    key={skill.skill_id}
                    onClick={() => selectSkill(skill)}
                    role="option"
                    aria-selected={isSelected}
                    className={`flex items-center justify-between w-full px-3 py-2 rounded-lg transition-colors cursor-pointer ${
                      isSelected
                        ? "bg-indigo-500/10 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 font-medium"
                        : "text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-white/[0.04]"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold">/{skill.skill_id}</span>
                      <span className="text-xs text-zinc-500">({skill.name})</span>
                    </div>
                    <span className="text-xs max-w-[250px] truncate text-zinc-400">
                      {skill.description}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Floating Tools Dropdown */}
      {showToolMenu && filteredTools.length > 0 && (
        <div className="absolute bottom-full left-0 right-0 mb-3 z-50 px-4">
          <div className="border border-zinc-200/80 dark:border-white/8 bg-white/90 dark:bg-[#1c1c1e]/90 backdrop-blur-md shadow-2xl rounded-2xl p-1 max-h-60 overflow-y-auto no-scrollbar">
            <div className="flex flex-col gap-1" role="listbox" aria-label="Tools Command Menu">
              {filteredTools.map((tool, index) => {
                const isSelected = index === selectedToolIndex;
                return (
                  <div
                    key={tool.id}
                    onClick={() => selectTool(tool)}
                    role="option"
                    aria-selected={isSelected}
                    className={`flex items-center justify-between w-full px-3 py-2 rounded-lg transition-colors cursor-pointer ${
                      isSelected
                        ? "bg-emerald-500/10 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 font-medium"
                        : "text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-white/[0.04]"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold">@{tool.id}</span>
                      <span className="text-xs text-zinc-400">({tool.category})</span>
                    </div>
                    <span className="text-xs max-w-[250px] truncate text-zinc-400">
                      {tool.description}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Text input area */}
      <div className={`relative flex w-full items-start px-4 ${isLanding ? "py-3 min-h-[80px]" : "py-4 min-h-[80px]"}`}>
        {/* Highlight Overlay */}
        <div
          ref={highlightRef}
          className={`pointer-events-none absolute inset-x-4 overflow-hidden whitespace-pre-wrap break-words text-[18px] leading-relaxed text-zinc-900 dark:text-zinc-200 no-scrollbar ${
            isLanding ? "top-3 bottom-3 py-0" : "top-4 bottom-4 py-0"
          }`}
        >
          {renderHighlightedText(textInput)}
        </div>

        {/* Text Area */}
        <textarea
          suppressHydrationWarning
          ref={inputRef}
          value={textInput}
          onChange={(e) => handleInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          onScroll={handleScroll}
          placeholder="Send message to CoComputer"
          rows={1}
          className={`w-full bg-transparent border-none p-0 outline-none text-transparent caret-zinc-900 dark:caret-white placeholder-zinc-500 placeholder:font-medium focus:ring-0 resize-none overflow-y-auto no-scrollbar max-h-60 leading-relaxed ${isLanding ? "text-[18px]" : "text-[18px]"}`}
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
