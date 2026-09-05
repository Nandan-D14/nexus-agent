/**
 * Copyright (c) 2026 nandan-d14. All rights reserved.
 * Proprietary and non-commercial use only.
 */

/** Built-in capability groups shown in the composer "+" tool picker. */
export const TOOL_CAPABILITIES = [
  {
    id: "web_research",
    label: "Web Research",
    description: "Search the web and scrape pages",
    tools: ["web_search", "tavily_search", "scrape_web_page", "search_sources"],
  },
  {
    id: "terminal",
    label: "Terminal",
    description: "Run shell commands in the sandbox",
    tools: ["terminal_worker", "run_command"],
  },
  {
    id: "computer_use",
    label: "Computer Use",
    description: "Control the desktop browser and screen",
    tools: ["desktop_worker", "take_screenshot", "open_browser"],
  },
  {
    id: "artifacts",
    label: "Artifacts",
    description: "Publish HTML apps and rendered UI",
    tools: ["publish_html_artifact", "publish_app_preview", "render_ui"],
  },
  {
    id: "memory",
    label: "Memory",
    description: "Remember and recall facts across sessions",
    tools: ["remember_fact", "recall_facts"],
  },
] as const;

export type ToolCapabilityId = (typeof TOOL_CAPABILITIES)[number]["id"];

export type ToolPaletteItem = {
  id: string;
  name: string;
  description: string;
  category: "System" | "Integration";
};

/** Flat list of built-in capabilities for the @ mention palette. */
export function builtInPaletteItems(): ToolPaletteItem[] {
  return TOOL_CAPABILITIES.map((cap) => ({
    id: cap.id,
    name: cap.label,
    description: cap.description,
    category: "System" as const,
  }));
}
