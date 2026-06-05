# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Parallel tool execution registry.

Identifies which tools can safely run concurrently (read-only tools)
and which must run sequentially (tools that modify state).
"""

from __future__ import annotations

# Tools that are safe to run in parallel — they only read data and don't
# modify any shared state (sandbox, workspace, screen, etc.).
_PARALLEL_SAFE_TOOLS: frozenset[str] = frozenset({
    # Read-only workspace tools
    "read_workspace_file",
    "read_task_state",
    "list_workspace_files",
    # Web tools (read-only)
    "web_search",
    "scrape_web_page",
    "tavily_search",
    # Google Drive (read-only)
    "search_drive",
    "read_drive_file",
    # GitHub (read-only)
    "github_search_repos",
    "github_read_file",
    "github_list_issues",
    "github_summarize_pr",
    # Gmail (read-only)
    "gmail_search",
    "gmail_read",
    # Google Tasks/Calendar (read-only)
    "tasks_list",
    "calendar_list",
    # Documents (read-only)
    "extract_pdf_text",
    # Screen observation (read-only)
    "take_screenshot",
})

# Tools that MUST run sequentially — they modify shared state.
_SEQUENTIAL_TOOLS: frozenset[str] = frozenset({
    # GUI actions (modify screen state)
    "move_mouse",
    "left_click",
    "right_click",
    "double_click",
    "type_text",
    "press_key",
    "scroll_screen",
    "drag",
    "open_browser",
    # Terminal (modifies sandbox state)
    "run_command",
    # Workspace writes (modify file system)
    "write_workspace_file",
    "write_todo_list",
    "update_todo_item",
    "prepare_task_workspace",
    "initialize_task_state",
    "update_task_state",
    # External side effects
    "gmail_send",
    "tasks_create",
    "calendar_create",
    "create_drive_doc",
    "upload_drive_file",
    "github_create_issue",
    # Background tasks
    "request_background_task",
    "schedule_monitoring_task",
    # UI control
    "show_desktop_panel",
    "show_workflow_panel",
    # Document generation
    "generate_pdf_report",
    "save_as_artifact",
    # Web automation
    "tinyfish_web_agent",
})


def is_parallelizable(tool_name: str) -> bool:
    """Check if a tool can safely run in parallel with other tools.

    Args:
        tool_name: Name of the tool function.

    Returns:
        True if the tool is read-only and safe to parallelize.
    """
    return tool_name in _PARALLEL_SAFE_TOOLS


def all_parallelizable(tool_names: list[str]) -> bool:
    """Check if ALL tools in a batch can run in parallel.

    Args:
        tool_names: List of tool function names.

    Returns:
        True if every tool in the batch is parallelizable.
    """
    return all(is_parallelizable(name) for name in tool_names)
