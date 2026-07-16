# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Shared resource locks for parallel agent tool execution."""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections.abc import Iterator


GUI_TOOLS: frozenset[str] = frozenset(
    {
        "take_screenshot",
        "open_browser",
        "move_mouse",
        "left_click",
        "right_click",
        "double_click",
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
)

WORKSPACE_MUTATION_TOOLS: frozenset[str] = frozenset(
    {
        "run_command",
        "prepare_task_workspace",
        "initialize_task_state",
        "update_task_state",
        "write_todo_list",
        "update_todo_item",
        "write_workspace_file",
        "generate_pdf_report",
        "generate_excel_report",
        "generate_docx_report",
        "publish_html_artifact",
        "save_as_artifact",
    }
)


class ToolResourceLocks:
    """Lock shared sandbox resources used by parallel subagents."""

    def __init__(self) -> None:
        self._locks = {
            "gui": threading.Lock(),
            "workspace_mutation": threading.Lock(),
        }

    def resources_for_tool(self, tool_name: str) -> tuple[str, ...]:
        resources: list[str] = []
        if tool_name in GUI_TOOLS:
            resources.append("gui")
        if tool_name in WORKSPACE_MUTATION_TOOLS:
            resources.append("workspace_mutation")
        return tuple(resources)

    @contextlib.contextmanager
    def sync_lock(self, tool_name: str) -> Iterator[None]:
        resources = self.resources_for_tool(tool_name)
        acquired: list[threading.Lock] = []
        try:
            for resource in resources:
                lock = self._locks[resource]
                lock.acquire()
                acquired.append(lock)
            yield
        finally:
            for lock in reversed(acquired):
                lock.release()

    @contextlib.asynccontextmanager
    async def async_lock(self, tool_name: str):
        resources = self.resources_for_tool(tool_name)
        acquired: list[threading.Lock] = []
        try:
            for resource in resources:
                lock = self._locks[resource]
                await asyncio.to_thread(lock.acquire)
                acquired.append(lock)
            yield
        finally:
            for lock in reversed(acquired):
                lock.release()
