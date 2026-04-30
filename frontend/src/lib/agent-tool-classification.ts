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

const BROWSER_TOOLS = new Set(["web_search", "scrape_web_page", "open_browser"]);
const FILE_TOOLS = new Set(["write_workspace_file", "read_workspace_file", "list_workspace_files"]);
const WORKFLOW_TOOLS = new Set(["write_todo_list", "prepare_task_workspace", "update_todo_item"]);

export function classifyAgentTool(tool = ""): AgentToolProvider {
  if (tool.startsWith("gmail_")) return "gmail";
  if (tool.startsWith("calendar_")) return "calendar";
  if (tool.startsWith("tasks_")) return "tasks";
  if (tool.startsWith("mcp__")) return "mcp";
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

export function providerLabel(provider: AgentToolProvider): string {
  if (provider === "gmail") return "Gmail";
  if (provider === "calendar") return "Calendar";
  if (provider === "tasks") return "Tasks";
  if (provider === "mcp") return "MCP";
  if (provider === "browser") return "Web";
  if (provider === "desktop") return "Desktop";
  if (provider === "terminal") return "Terminal";
  if (provider === "file") return "Files";
  if (provider === "workflow") return "Workflow";
  return "Tool";
}

function formatBrowserTool(tool: string): string {
  if (tool === "web_search") return "Web Search";
  if (tool === "scrape_web_page") return "Read Web Page";
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
