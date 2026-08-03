/**
 * Copyright (c) 2026 Agentic Company. All rights reserved.
 * Proprietary and non-commercial use only.
 */

export type AgentToolProvider =
  | "gmail"
  | "calendar"
  | "tasks"
  | "mcp"
  | "browser"
  | "desktop"
  | "terminal"
  | "file"
  | "workflow"
  | "skill"
  | "subagent"
  | "worker"
  | "generic";

export type AgentSurface = "workflow" | "desktop";

const DESKTOP_TOOLS = new Set([
  "left_click",
  "right_click",
  "double_click",
  "move_mouse",
  "drag",
  "type_text",
  "press_key",
  "scroll_screen",
  "take_screenshot",
]);

const BROWSER_TOOLS = new Set(["web_search", "search_web", "scrape_web_page", "open_browser", "tavily_search"]);
const FILE_TOOLS = new Set(["write_workspace_file", "read_workspace_file", "list_workspace_files"]);
const WORKFLOW_TOOLS = new Set([
  "write_todo_list",
  "update_todo_item",
  "prepare_task_workspace",
  "initialize_task_state",
  "update_task_state",
  "read_task_state",
  "publish_html_artifact",
  "render_ui",
  "ask_user",
  "request_background_task",
]);
const SKILL_TOOLS = new Set(["read_skill"]);
const SUBAGENT_TOOLS = new Set([
  "invoke_subagent",
  "send_message",
  "get_subagent_result",
  "list_subagents",
  "cancel_subagent",
  "await_subagents",
]);
const WORKER_TOOLS = new Set(["terminal_worker", "desktop_worker"]);

const WORKFLOW_VISUAL_TOOLS = new Set(["publish_html_artifact", "render_ui"]);

export function isWorkflowVisualTool(tool = ""): boolean {
  return WORKFLOW_VISUAL_TOOLS.has(tool);
}

export function classifyAgentTool(tool = ""): AgentToolProvider {
  if (tool.startsWith("gmail_")) return "gmail";
  if (tool.startsWith("calendar_")) return "calendar";
  if (tool.startsWith("tasks_")) return "tasks";
  if (tool.startsWith("mcp__")) return "mcp";
  if (SKILL_TOOLS.has(tool)) return "skill";
  if (SUBAGENT_TOOLS.has(tool)) return "subagent";
  if (WORKER_TOOLS.has(tool)) return "worker";
  if (DESKTOP_TOOLS.has(tool)) return "desktop";
  if (BROWSER_TOOLS.has(tool)) return "browser";
  if (tool === "run_command") return "terminal";
  if (FILE_TOOLS.has(tool)) return "file";
  if (WORKFLOW_TOOLS.has(tool)) return "workflow";
  return "generic";
}

export function surfaceForAgentTool(tool = ""): AgentSurface {
  const provider = classifyAgentTool(tool);
  if (provider === "desktop") return "desktop";
  if (provider === "browser" && tool === "open_browser") return "desktop";
  return "workflow";
}

export function displayAgentToolName(tool = ""): string {
  if (!tool) return "Tool";
  if (tool.startsWith("mcp__")) {
    const [, server, remoteTool] = tool.split("__");
    return `MCP: ${formatToolPart(server)}${remoteTool ? ` / ${formatToolPart(remoteTool)}` : ""}`;
  }

  const named: Record<string, string> = {
    read_skill: "Read Skill",
    invoke_subagent: "Spawn Subagent",
    send_message: "Message Subagent",
    get_subagent_result: "Check Subagent",
    list_subagents: "List Subagents",
    cancel_subagent: "Cancel Subagent",
    await_subagents: "Await Subagents",
    terminal_worker: "Terminal Worker",
    desktop_worker: "Desktop Worker",
    render_ui: "Render C1 UI",
    publish_html_artifact: "Publish HTML",
    ask_user: "Ask User",
    prepare_task_workspace: "Prepare Workspace",
    write_todo_list: "Update Todo List",
    update_todo_item: "Update Todo Item",
    read_task_state: "Read Task State",
    update_task_state: "Update Task State",
    initialize_task_state: "Init Task State",
    request_background_task: "Background Task",
    web_search: "Web Search",
    search_web: "Web Search",
    scrape_web_page: "Read Web Page",
    tavily_search: "Tavily Search",
    run_command: "Terminal Command",
    read_workspace_file: "Read File",
    write_workspace_file: "Write File",
    list_workspace_files: "List Files",
  };
  if (named[tool]) return named[tool];

  const provider = classifyAgentTool(tool);
  const action = tool.replace(/^(gmail|calendar|tasks)_/, "");
  if (provider === "gmail") return `Gmail: ${formatToolPart(action)}`;
  if (provider === "calendar") return `Calendar: ${formatToolPart(action)}`;
  if (provider === "tasks") return `Tasks: ${formatToolPart(action)}`;
  if (provider === "browser") return formatBrowserTool(tool);
  if (provider === "desktop") return formatDesktopTool(tool);
  if (provider === "terminal") return "Terminal Command";
  if (provider === "file") return formatToolPart(tool.replace(/_workspace_/g, "_"));
  return formatToolPart(tool);
}

export function providerLabel(provider: AgentToolProvider, tool?: string): string {
  if (provider === "gmail") return "Gmail";
  if (provider === "calendar") return "Calendar";
  if (provider === "tasks") return "Tasks";
  if (provider === "mcp") return "MCP";
  if (provider === "browser") return "Web";
  if (provider === "desktop") return "Desktop";
  if (provider === "terminal") return "Terminal";
  if (provider === "file") return "Files";
  if (provider === "skill") return "Skill";
  if (provider === "subagent") return "Subagent";
  if (provider === "worker") return "Worker";
  if (provider === "workflow") {
    if (tool === "render_ui") return "C1 Visual";
    if (tool === "publish_html_artifact") return "HTML Artifact";
    if (tool === "ask_user") return "Question";
    return "Workflow";
  }
  return "Tool";
}

/** Short verb label shown in the chat activity log before the detail. */
export function toolActionLabel(tool = ""): string {
  const provider = classifyAgentTool(tool);
  if (tool === "read_skill") return "Reading skill";
  if (tool === "render_ui") return "Rendering C1 UI";
  if (tool === "publish_html_artifact") return "Publishing artifact";
  if (tool === "ask_user") return "Asking user";
  if (tool === "terminal_worker") return "Terminal worker";
  if (tool === "desktop_worker") return "Desktop worker";
  if (tool === "invoke_subagent") return "Spawning subagent";
  if (tool === "await_subagents") return "Awaiting subagents";
  if (tool === "get_subagent_result") return "Checking subagent";
  if (tool === "list_subagents") return "Listing subagents";
  if (tool === "send_message") return "Messaging subagent";
  if (tool === "cancel_subagent") return "Cancelling subagent";
  if (tool === "prepare_task_workspace") return "Preparing workspace";
  if (tool === "write_todo_list") return "Updating plan";
  if (tool === "update_todo_item") return "Updating todo";
  if (tool === "read_workspace_file") return "Reading file";
  if (tool === "write_workspace_file") return "Writing file";
  if (tool === "list_workspace_files") return "Listing files";
  if (provider === "terminal") return "Running command";
  if (provider === "browser") return "Web lookup";
  if (provider === "desktop") return "Desktop action";
  return displayAgentToolName(tool);
}

/** Counted label for consecutive identical tool invocations in the activity log. */
export function formatGroupedToolLabel(tool = "", count = 1): string {
  if (count <= 1) return toolActionLabel(tool);
  if (tool === "gmail_read") return `Read ${count} emails`;
  if (tool === "gmail_search") return `Searched Gmail ×${count}`;
  if (tool === "read_workspace_file") return `Read ${count} files`;
  if (tool === "write_workspace_file") return `Wrote ${count} files`;
  if (tool === "list_workspace_files") return `Listed files ×${count}`;
  if (tool === "update_todo_item") return `Updated todo ×${count}`;
  if (tool === "web_search" || tool === "search_web" || tool === "tavily_search") {
    return `Searched web ×${count}`;
  }
  if (tool === "scrape_web_page") return `Read ${count} pages`;
  if (tool === "run_command") return `Ran ${count} commands`;
  return `${toolActionLabel(tool)} ×${count}`;
}

function formatBrowserTool(tool: string): string {
  if (tool === "web_search" || tool === "search_web") return "Web Search";
  if (tool === "scrape_web_page") return "Read Web Page";
  if (tool === "tavily_search") return "Tavily Search";
  if (tool === "open_browser") return "Open Browser";
  return formatToolPart(tool);
}

function formatDesktopTool(tool: string): string {
  if (tool === "take_screenshot") return "Screenshot";
  if (tool === "type_text") return "Typing";
  if (tool === "press_key") return "Key Press";
  if (tool.includes("click")) return "Click";
  if (tool === "move_mouse") return "Move Pointer";
  if (tool === "scroll_screen") return "Scroll";
  if (tool === "drag") return "Drag";
  return formatToolPart(tool);
}

function formatToolPart(value = ""): string {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ") || "Tool";
}
