"""Workspace tools for task-scoped files inside the sandbox."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath
import re
from typing import Any, Literal

from nexus.config import settings
from nexus.tools._context import (
    get_run_id,
    get_sandbox,
    get_session_id,
    get_workspace_path,
    set_workspace_path,
)

_STATUS_VALUES = {"pending", "in_progress", "done"}
_TODO_LINE_RE = re.compile(
    r"^(?P<index>\d+)\. \[(?P<status>pending|in_progress|done)\] (?P<title>.*?)(?: - (?P<note>.*))?$"
)


def _tool_error(message: str) -> dict[str, Any]:
    return {"error": message}


def derive_workspace_path(session_id: str, run_id: str) -> str:
    root = settings.agent_workspace_root.rstrip("/") or "/home/user/CoComputer/Workspaces"
    return f"{root}/{session_id}/{run_id}"


def derive_session_workspace_path(session_id: str) -> str:
    root = settings.agent_workspace_root.rstrip("/") or "/home/user/CoComputer/Workspaces"
    return f"{root}/{session_id}"


def get_active_workspace_path() -> str:
    try:
        return get_workspace_path()
    except RuntimeError:
        workspace_path = derive_workspace_path(get_session_id(), get_run_id())
        set_workspace_path(workspace_path)
        return workspace_path


def _normalize_relative_path(relative_path: str) -> str:
    raw = (relative_path or "").strip().replace("\\", "/")
    if not raw:
        raise ValueError("relative_path is required")
    candidate = PurePosixPath(raw)
    if candidate.is_absolute():
        raise ValueError("relative_path must stay inside the active workspace")
    parts = [part for part in candidate.parts if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise ValueError("relative_path must stay inside the active workspace")
    return "/".join(parts)


def _join_workspace_path(relative_path: str) -> tuple[str, str]:
    normalized = _normalize_relative_path(relative_path)
    workspace_path = get_active_workspace_path()
    return workspace_path, f"{workspace_path}/{normalized}"


def _build_todo_markdown(items: list[str]) -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    if not cleaned:
        raise ValueError("Provide at least one todo item")
    return "# TODO\n\n" + "\n".join(
        f"{index}. [pending] {item}" for index, item in enumerate(cleaned, start=1)
    ) + "\n"


def _parse_todo_markdown(text: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = _TODO_LINE_RE.match(line)
        if not match:
            continue
        items.append(
            {
                "status": match.group("status"),
                "title": match.group("title").strip(),
                "note": (match.group("note") or "").strip(),
            }
        )
    return items


def _format_todo_items(items: list[dict[str, str]]) -> str:
    lines = ["# TODO", ""]
    for index, item in enumerate(items, start=1):
        note = f" - {item['note']}" if item.get("note") else ""
        lines.append(f"{index}. [{item['status']}] {item['title']}{note}")
    lines.append("")
    return "\n".join(lines)


def _default_file_contents(task_summary: str) -> dict[str, str]:
    timestamp = datetime.now(timezone.utc).isoformat()
    cleaned_summary = task_summary.strip()
    task_body = (
        "# Task\n\n"
        f"Created: {timestamp}\n\n"
        "## Latest Request\n\n"
        f"{cleaned_summary or 'No task summary provided.'}\n"
    )
    notes_body = "# Notes\n\n"
    return {
        "task.md": task_body,
        "todo.md": "# TODO\n\nNo todo list yet.\n",
        "notes.md": notes_body,
    }


def _append_task_summary(existing: str, task_summary: str) -> str:
    cleaned_summary = task_summary.strip()
    if not cleaned_summary:
        return existing
    timestamp = datetime.now(timezone.utc).isoformat()
    section = (
        "\n\n## Turn Request\n\n"
        f"Timestamp: {timestamp}\n\n"
        f"{cleaned_summary}\n"
    )
    if cleaned_summary in existing:
        return existing
    return existing.rstrip() + section


async def prepare_task_workspace(task_summary: str) -> dict[str, Any]:
    """Create or reuse the per-run workspace scaffold inside the sandbox."""
    try:
        sandbox = get_sandbox()
        workspace_path = derive_workspace_path(get_session_id(), get_run_id())
        set_workspace_path(workspace_path)

        created = not sandbox.path_exists(workspace_path)
        sandbox.ensure_directory(workspace_path)
        sandbox.ensure_directory(f"{workspace_path}/sources")
        sandbox.ensure_directory(f"{workspace_path}/outputs")

        file_map = _default_file_contents(task_summary)
        touched_files: list[str] = []
        for relative_name, default_content in file_map.items():
            absolute_path = f"{workspace_path}/{relative_name}"
            if not sandbox.path_exists(absolute_path):
                sandbox.write_text_file(absolute_path, default_content)
                touched_files.append(relative_name)
                continue
            if relative_name == "task.md" and task_summary.strip():
                existing = sandbox.read_text_file(absolute_path)
                updated = _append_task_summary(existing, task_summary)
                if updated != existing:
                    sandbox.write_text_file(absolute_path, updated)
                    touched_files.append(relative_name)

        return {
            "workspace_path": workspace_path,
            "created": created,
            "touched_files": touched_files,
            "task_file": f"{workspace_path}/task.md",
            "todo_file": f"{workspace_path}/todo.md",
            "notes_file": f"{workspace_path}/notes.md",
            "sources_dir": f"{workspace_path}/sources",
            "outputs_dir": f"{workspace_path}/outputs",
        }
    except Exception as exc:
        return _tool_error(str(exc) or "Failed to prepare the task workspace.")


async def write_todo_list(items: list[str]) -> dict[str, Any]:
    """Write the task todo list to todo.md in the active workspace."""
    try:
        if not isinstance(items, list):
            return _tool_error("items must be a list of todo strings.")
        workspace_path = get_active_workspace_path()
        content = _build_todo_markdown(items)
        path = f"{workspace_path}/todo.md"
        get_sandbox().write_text_file(path, content)
        return {
            "todo_file": path,
            "item_count": len([item for item in items if item and item.strip()]),
            "status": "success",
        }
    except Exception as exc:
        return _tool_error(str(exc) or "Failed to write the todo list.")


async def update_todo_item(
    item_index: int,
    status: Literal["pending", "in_progress", "done"],
    note: str = "",
) -> dict[str, Any]:
    """Update one todo item in todo.md."""
    try:
        if status not in _STATUS_VALUES:
            return _tool_error("status must be pending, in_progress, or done")
        if not isinstance(item_index, int):
            return _tool_error(
                "item_index must be an integer. Index is 1-based. Please retry with a valid index."
            )
        if item_index < 1:
            return _tool_error(
                "item_index must be at least 1. Index is 1-based. Please retry with a valid index."
            )

        workspace_path = get_active_workspace_path()
        path = f"{workspace_path}/todo.md"
        sandbox = get_sandbox()
        items = _parse_todo_markdown(sandbox.read_text_file(path))
        if item_index > len(items):
            return _tool_error("item_index is out of range for the current todo list")
        target = items[item_index - 1]
        target["status"] = status
        target["note"] = note.strip()
        sandbox.write_text_file(path, _format_todo_items(items))
        return {
            "todo_file": path,
            "updated_item": item_index,
            "status": status,
            "title": target["title"],
        }
    except Exception as exc:
        return _tool_error(str(exc) or "Failed to update the todo item.")


async def write_workspace_file(
    relative_path: str,
    content: str,
    append: bool = False,
) -> dict[str, Any]:
    """Write text content to a file inside the active workspace."""
    try:
        workspace_path, absolute_path = _join_workspace_path(relative_path)
        content_text = content if isinstance(content, str) else str(content)
        get_sandbox().write_text_file(absolute_path, content_text, append=append)
        normalized_relative = _normalize_relative_path(relative_path)
        preview = " ".join(content_text.split())
        if len(preview) > 240:
            preview = preview[:239].rstrip() + "…"
        response = {
            "workspace_path": workspace_path,
            "workspace_file": absolute_path,
            "relative_path": normalized_relative,
            "bytes_written": len(content_text.encode("utf-8")),
            "append": append,
            "status": "success",
            "summary": preview or f"Saved {normalized_relative}",
        }
        if normalized_relative.startswith("outputs/"):
            response["output_path"] = absolute_path
        return {
            **response,
        }
    except Exception as exc:
        return _tool_error(str(exc) or "Failed to write the workspace file.")


async def read_workspace_file(relative_path: str) -> dict[str, Any]:
    """Read a text file from the active workspace."""
    try:
        workspace_path, absolute_path = _join_workspace_path(relative_path)
        content = get_sandbox().read_text_file(absolute_path)
        return {
            "workspace_path": workspace_path,
            "workspace_file": absolute_path,
            "relative_path": _normalize_relative_path(relative_path),
            "content": content,
        }
    except Exception as exc:
        return _tool_error(str(exc) or "Failed to read the workspace file.")


async def list_workspace_files(relative_path: str = "") -> dict[str, Any]:
    """List files inside the active workspace."""
    try:
        workspace_path = get_active_workspace_path()
        normalized = relative_path.strip()
        target_path = workspace_path
        display_relative = ""
        if normalized:
            _, target_path = _join_workspace_path(normalized)
            display_relative = _normalize_relative_path(normalized)
        entries = get_sandbox().list_directory(target_path)
        return {
            "workspace_path": workspace_path,
            "directory_path": target_path,
            "relative_path": display_relative,
            "entries": entries,
        }
    except Exception as exc:
        return _tool_error(str(exc) or "Failed to list workspace files.")
