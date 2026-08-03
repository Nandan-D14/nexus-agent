# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""User-selected tool allowlists for per-turn hard enforcement.

Mirrors ``frontend/src/lib/tool-catalog.ts``. Empty selection means
unrestricted (preserves prior behavior). A non-empty selection expands
capability ids / connector ids into concrete ADK tool names; infrastructure
tools in ``ALWAYS_ALLOWED`` stay callable so the agent cannot be bricked.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

# Capability id → concrete tool names (planner + worker-internal).
TOOL_CAPABILITIES: dict[str, frozenset[str]] = {
    "web_research": frozenset(
        {"web_search", "tavily_search", "scrape_web_page", "search_sources"}
    ),
    "terminal": frozenset({"terminal_worker", "run_command"}),
    "computer_use": frozenset(
        {
            "desktop_worker",
            "take_screenshot",
            "open_browser",
            "move_mouse",
            "left_click",
            "right_click",
            "double_click",
            "triple_click",
            "type_text",
            "press_key",
            "scroll_screen",
            "drag",
            "playwright_navigate",
            "playwright_click",
            "playwright_type",
            "playwright_get_text",
            "playwright_wait_for",
            "playwright_snapshot",
            "playwright_verify",
        }
    ),
    "artifacts": frozenset({"publish_html_artifact", "render_ui"}),
    "memory": frozenset({"remember_fact", "recall_facts"}),
}

# Connector / connection_id → native tool names.
CONNECTOR_TOOLS: dict[str, frozenset[str]] = {
    "gmail": frozenset({"gmail_search", "gmail_read", "gmail_send"}),
    "google_drive": frozenset(
        {"search_drive", "read_drive_file", "create_drive_doc", "upload_drive_file"}
    ),
    "google_calendar": frozenset({"calendar_list", "calendar_create"}),
    "google_tasks": frozenset({"tasks_list", "tasks_create"}),
    "github": frozenset(
        {
            "github_search_repos",
            "github_read_file",
            "github_list_issues",
            "github_create_issue",
            "github_summarize_pr",
        }
    ),
    "tavily": frozenset({"tavily_search"}),
    "tinyfish": frozenset({"tinyfish_web_agent"}),
    "thesys": frozenset({"render_ui"}),
    # Legacy "system" connector from the frontend — maps to core sandbox caps.
    "system": frozenset(
        {
            "terminal_worker",
            "desktop_worker",
            "run_command",
            "take_screenshot",
            "open_browser",
            "web_search",
            "tavily_search",
            "scrape_web_page",
            "search_sources",
            "publish_html_artifact",
            "render_ui",
        }
    ),
}

# Always callable so the agent can still plan, ask, and work with files/skills.
ALWAYS_ALLOWED: frozenset[str] = frozenset(
    {
        "ask_user",
        "prepare_task_workspace",
        "initialize_task_state",
        "update_task_state",
        "read_task_state",
        "write_todo_list",
        "update_todo_item",
        "write_workspace_file",
        "read_workspace_file",
        "list_workspace_files",
        "read_skill",
        "invoke_subagent",
        "send_message",
        "get_subagent_result",
        "list_subagents",
        "cancel_subagent",
        "await_subagents",
        "request_background_task",
        "extract_pdf_text",
        "generate_pdf_report",
        "generate_excel_report",
        "generate_docx_report",
        "save_as_artifact",
    }
)


def _clean_ids(values: Iterable[str] | None) -> list[str]:
    cleaned: list[str] = []
    for item in values or []:
        val = str(item).strip()
        if val:
            cleaned.append(val)
    return cleaned


def resolve_tool_allowlist(
    tool_ids: Iterable[str] | None,
    connector_ids: Iterable[str] | None,
    *,
    mcp_tools: Iterable[Callable[..., Any]] | None = None,
) -> frozenset[str] | None:
    """Expand user selections into a concrete tool-name allowlist.

    Returns ``None`` when nothing is selected (unrestricted). Otherwise returns
    the union of capability tools, connector tools, MCP tools for the selected
    connections, and ``ALWAYS_ALLOWED``.
    """
    selected_tools = _clean_ids(tool_ids)
    selected_connectors = _clean_ids(connector_ids)
    if not selected_tools and not selected_connectors:
        return None

    allowed: set[str] = set(ALWAYS_ALLOWED)

    for tool_id in selected_tools:
        if tool_id in TOOL_CAPABILITIES:
            allowed.update(TOOL_CAPABILITIES[tool_id])
        else:
            # Allow raw tool names (e.g. from @mentions) to pass through.
            allowed.add(tool_id)

    for connector_id in selected_connectors:
        mapped = CONNECTOR_TOOLS.get(connector_id)
        if mapped:
            allowed.update(mapped)
        else:
            # Unknown connector id — keep it so MCP dynamic matching can use it.
            allowed.add(connector_id)

    if mcp_tools:
        selected_set = set(selected_connectors)
        for tool in mcp_tools:
            connection_id = getattr(tool, "_connection_id", None)
            if connection_id and str(connection_id) in selected_set:
                name = getattr(tool, "__name__", None)
                if name:
                    allowed.add(str(name))

    return frozenset(allowed)


def is_tool_allowed(
    tool_name: str,
    allowlist: frozenset[str] | None,
    *,
    connection_id: str | None = None,
) -> bool:
    """Return True when ``tool_name`` may execute under the active allowlist."""
    if allowlist is None:
        return True
    if tool_name in ALWAYS_ALLOWED:
        return True
    if tool_name in allowlist:
        return True
    if connection_id and connection_id in allowlist:
        return True
    return False
