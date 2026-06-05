# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Workspace tools for task-scoped files inside the sandbox."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import PurePosixPath
import re
from typing import Any, Literal

from nexus.config import settings
from nexus.storage import artifact_storage_metadata, upload_artifact
from nexus.task_state import (
    build_initial_task_state,
    infer_task_type,
    merge_task_state,
    refresh_task_state_for_request,
)
from nexus.tools._context import (
    get_run_id,
    get_sandbox,
    get_send_json,
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


async def _emit_todo_update(items: list[dict[str, str]]) -> None:
    send_json = get_send_json()
    if not send_json:
        return
    await send_json(
        {
            "type": "todo_list_updated",
            "items": [
                {"title": item["title"], "status": item["status"], "note": item["note"]}
                for item in items
            ],
        }
    )


async def _emit_task_state_update(state: dict[str, Any]) -> None:
    send_json = get_send_json()
    if not send_json:
        return
    await send_json({"type": "task_state_updated", "state": state})


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
        workspace_path = derive_session_workspace_path(get_session_id())
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


def _task_state_path(workspace_path: str) -> str:
    return f"{workspace_path}/task_state.json"


def _load_task_state(workspace_path: str) -> dict[str, Any]:
    sandbox = get_sandbox()
    path = _task_state_path(workspace_path)
    if not sandbox.path_exists(path):
        return {}
    try:
        loaded = json.loads(sandbox.read_text_file(path))
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _save_task_state(workspace_path: str, state: dict[str, Any]) -> str:
    content = json.dumps(state, indent=2, sort_keys=True)
    path = _task_state_path(workspace_path)
    get_sandbox().write_text_file(path, content)
    upload_artifact(get_session_id(), get_run_id(), "task_state.json", content)
    return path


from nexus.tools.base import normalized_tool, tool_error, tool_success

@normalized_tool
async def prepare_task_workspace(task_summary: str) -> dict[str, Any]:
    """Create or reuse the per-run workspace scaffold inside the sandbox."""
    try:
        sandbox = get_sandbox()
        workspace_path = derive_session_workspace_path(get_session_id())
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
                upload_artifact(get_session_id(), get_run_id(), relative_name, default_content)
                touched_files.append(relative_name)
                continue
            if relative_name == "task.md" and task_summary.strip():
                existing = sandbox.read_text_file(absolute_path)
                updated = _append_task_summary(existing, task_summary)
                if updated != existing:
                    sandbox.write_text_file(absolute_path, updated)
                    upload_artifact(get_session_id(), get_run_id(), relative_name, updated)
                    touched_files.append(relative_name)

        state_path = _task_state_path(workspace_path)
        existing_state = _load_task_state(workspace_path)
        task_state = refresh_task_state_for_request(
            existing_state,
            task_id=get_run_id(),
            run_id=get_run_id(),
            task_summary=task_summary,
            active_agent="nexus_orchestrator",
        )
        _save_task_state(workspace_path, task_state)
        if not existing_state:
            touched_files.append("task_state.json")
        await _emit_task_state_update(task_state)

        return {
            "workspace_path": workspace_path,
            "created": created,
            "touched_files": touched_files,
            "task_file": f"{workspace_path}/task.md",
            "todo_file": f"{workspace_path}/todo.md",
            "notes_file": f"{workspace_path}/notes.md",
            "task_state_file": state_path,
            "task_type": task_state["task_type"],
            "stage": task_state["stage"],
            "review_status": task_state["review_status"],
            "sources_dir": f"{workspace_path}/sources",
            "outputs_dir": f"{workspace_path}/outputs",
        }
    except Exception as exc:
        return _tool_error(str(exc) or "Failed to prepare the task workspace.")


@normalized_tool
async def initialize_task_state(
    task_summary: str,
    task_type: str = "general_task",
    active_agent: str = "nexus_orchestrator",
) -> dict[str, Any]:
    """Initialize or refresh task_state.json for the current agentic workflow.

    Args:
        task_summary: Description of the current task.
        task_type: One of code_task, browser_task, gui_task, deep_research, etc.
        active_agent: Name of the agent currently working.

    Returns:
        NormalizedToolResult with task state details.
    """
    try:
        workspace_path = get_active_workspace_path()
        resolved_type = task_type if task_type != "general_task" else infer_task_type(task_summary)
        existing_state = _load_task_state(workspace_path)
        if existing_state:
            state = refresh_task_state_for_request(
                existing_state,
                task_id=get_run_id(),
                run_id=get_run_id(),
                task_summary=task_summary,
                task_type=resolved_type,
                active_agent=active_agent,
            )
        else:
            state = build_initial_task_state(
                task_id=get_run_id(),
                run_id=get_run_id(),
                task_summary=task_summary,
                task_type=resolved_type,
                active_agent=active_agent,
            )
        path = _save_task_state(workspace_path, state)
        await _emit_task_state_update(state)
        return tool_success(
            f"Initialized task state: {resolved_type}",
            task_state_file=path,
            task_id=state["task_id"],
            task_type=state["task_type"],
            stage=state["stage"],
            active_agent=state["active_agent"],
            review_status=state["review_status"],
        )
    except Exception as exc:
        return tool_error(str(exc) or "Failed to initialize task state.")


@normalized_tool
async def update_task_state(
    stage: str = "intake",
    active_agent: str = "",
    review_status: str = "",
    todo: list[str] = None,
    evidence: list[str] = None,
    artifact_paths: list[str] = None,
    summary: str = "",
) -> dict[str, Any]:
    """Update durable task stage, active agent, evidence, artifacts, and review status.

    Args:
        stage: Current workflow stage (intake, planning, executing, reviewing, etc.).
        active_agent: Name of the agent currently working.
        review_status: Review state (not_required, pending, passed, changes_requested).
        todo: Updated todo list items.
        evidence: List of evidence descriptions.
        artifact_paths: List of output file paths.
        summary: Brief description of current progress.

    Returns:
        NormalizedToolResult with updated task state.
    """
    try:
        workspace_path = get_active_workspace_path()
        state = _load_task_state(workspace_path)
        if not state:
            state = build_initial_task_state(
                task_id=get_run_id(),
                run_id=get_run_id(),
                task_summary=summary,
                active_agent=active_agent or "nexus_orchestrator",
            )
        updated = merge_task_state(
            state,
            stage=stage,
            active_agent=active_agent or None,
            review_status=review_status or None,
            todo=todo,
            evidence=evidence,
            artifact_paths=artifact_paths,
            summary=summary,
        )
        path = _save_task_state(workspace_path, updated)
        await _emit_task_state_update(updated)
        return tool_success(
            f"Task state updated: stage={updated.get('stage', 'intake')}, agent={updated.get('active_agent', '')}",
            task_state_file=path,
            task_id=updated.get("task_id", ""),
            task_type=updated.get("task_type", "general_task"),
            stage=updated.get("stage", "intake"),
            active_agent=updated.get("active_agent", ""),
            review_status=updated.get("review_status", "not_required"),
            evidence_count=len(updated.get("evidence") or []),
            artifact_count=len(updated.get("artifact_paths") or []),
        )
    except Exception as exc:
        return tool_error(str(exc) or "Failed to update task state.")


@normalized_tool
async def read_task_state() -> dict[str, Any]:
    """Read task_state.json from the active workspace.

    Returns:
        NormalizedToolResult with the current task state, or error if not found.
    """
    try:
        workspace_path = get_active_workspace_path()
        state = _load_task_state(workspace_path)
        if not state:
            return tool_error(
                "task_state.json does not exist yet.",
                error_code="NOT_FOUND",
                suggested_alternatives=["initialize_task_state"],
            )
        return tool_success(
            f"Task state: {state.get('task_type', 'unknown')} / {state.get('stage', 'unknown')}",
            task_state_file=_task_state_path(workspace_path),
            state=state,
        )
    except Exception as exc:
        return tool_error(str(exc) or "Failed to read task state.")


@normalized_tool
async def write_todo_list(items: list[str]) -> dict[str, Any]:
    """Write the task todo list to todo.md in the active workspace.

    Args:
        items: List of todo item descriptions.

    Returns:
        NormalizedToolResult with todo file path and item count.
    """
    try:
        if not isinstance(items, list):
            return tool_error("items must be a list of todo strings.", error_code="INVALID_INPUT")
        workspace_path = get_active_workspace_path()
        content = _build_todo_markdown(items)
        path = f"{workspace_path}/todo.md"
        get_sandbox().write_text_file(path, content)

        # Mirror to GCS
        upload_artifact(get_session_id(), get_run_id(), "todo.md", content)

        # Sync to frontend
        todo_items = _parse_todo_markdown(content)
        await _emit_todo_update(todo_items)

        return tool_success(
            f"Wrote {len(todo_items)} todo items",
            todo_file=path,
            item_count=len(todo_items),
        )
    except Exception as exc:
        return tool_error(str(exc) or "Failed to write the todo list.")


@normalized_tool
async def update_todo_item(
    item_index: int,
    status: Literal["pending", "in_progress", "done"],
    note: str = "",
) -> dict[str, Any]:
    """Update one todo item in todo.md.

    Args:
        item_index: 1-based index of the todo item.
        status: New status (pending, in_progress, done).
        note: Optional note to attach to the item.

    Returns:
        NormalizedToolResult with updated item details.
    """
    try:
        if status not in _STATUS_VALUES:
            return tool_error("status must be pending, in_progress, or done", error_code="INVALID_INPUT")
        if not isinstance(item_index, int):
            return tool_error(
                "item_index must be an integer. Index is 1-based. Please retry with a valid index.",
                error_code="INVALID_INPUT",
            )
        if item_index < 1:
            return tool_error(
                "item_index must be at least 1. Index is 1-based. Please retry with a valid index.",
                error_code="INVALID_INPUT",
            )

        workspace_path = get_active_workspace_path()
        path = f"{workspace_path}/todo.md"
        sandbox = get_sandbox()
        items = _parse_todo_markdown(sandbox.read_text_file(path))
        if item_index > len(items):
            return tool_error("item_index is out of range for the current todo list", error_code="INVALID_INPUT")
        target = items[item_index - 1]
        target["status"] = status
        target["note"] = note.strip()
        formatted = _format_todo_items(items)
        sandbox.write_text_file(path, formatted)

        # Mirror to GCS
        upload_artifact(get_session_id(), get_run_id(), "todo.md", formatted)

        # Sync to frontend
        await _emit_todo_update(items)

        return tool_success(
            f"Updated todo #{item_index} to {status}",
            todo_file=path,
            updated_item=item_index,
            item_status=status,
            title=target["title"],
        )
    except Exception as exc:
        return tool_error(str(exc) or "Failed to update the todo item.")


@normalized_tool
async def write_workspace_file(
    relative_path: str,
    content: str,
    append: bool = False,
) -> dict[str, Any]:
    """Write text content to a file inside the active workspace.

    Args:
        relative_path: Path relative to workspace root (e.g. "notes.md", "outputs/report.html").
        content: Text content to write.
        append: If True, append to existing file instead of overwriting.

    Returns:
        NormalizedToolResult with file path and bytes written.
    """
    try:
        workspace_path, absolute_path = _join_workspace_path(relative_path)
        content_text = content if isinstance(content, str) else str(content)
        sandbox = get_sandbox()
        sandbox.write_text_file(absolute_path, content_text, append=append)

        normalized_relative = _normalize_relative_path(relative_path)

        # Mirror to GCS
        full_content = content_text
        if append:
            try:
                full_content = sandbox.read_text_file(absolute_path)
            except Exception:
                pass

        gcs_url = upload_artifact(get_session_id(), get_run_id(), normalized_relative, full_content)

        preview = " ".join(content_text.split())
        if len(preview) > 240:
            preview = preview[:239].rstrip() + "…"

        result_meta = {
            "workspace_path": workspace_path,
            "workspace_file": gcs_url or absolute_path,
            "relative_path": normalized_relative,
            "metadata": artifact_storage_metadata(get_session_id(), get_run_id(), normalized_relative),
            "bytes_written": len(content_text.encode("utf-8")),
            "append": append,
        }
        if gcs_url:
            result_meta["gcs_url"] = gcs_url
        if normalized_relative.startswith("outputs/"):
            result_meta["output_path"] = gcs_url or absolute_path

        return tool_success(
            preview or f"Saved {normalized_relative}",
            **result_meta,
        )
    except Exception as exc:
        return tool_error(str(exc) or "Failed to write the workspace file.")


@normalized_tool
async def read_workspace_file(relative_path: str) -> dict[str, Any]:
    """Read a text file from the active workspace.

    Args:
        relative_path: Path relative to workspace root.

    Returns:
        NormalizedToolResult with file content.
    """
    try:
        workspace_path, absolute_path = _join_workspace_path(relative_path)
        content = get_sandbox().read_text_file(absolute_path)
        return tool_success(
            f"Read {_normalize_relative_path(relative_path)} ({len(content)} chars)",
            workspace_path=workspace_path,
            workspace_file=absolute_path,
            relative_path=_normalize_relative_path(relative_path),
            content=content,
        )
    except Exception as exc:
        return tool_error(str(exc) or "Failed to read the workspace file.")


@normalized_tool
async def list_workspace_files(relative_path: str = "") -> dict[str, Any]:
    """List files inside the active workspace.

    Args:
        relative_path: Optional subdirectory to list (relative to workspace root).

    Returns:
        NormalizedToolResult with directory entries.
    """
    try:
        workspace_path = get_active_workspace_path()
        normalized = relative_path.strip()
        target_path = workspace_path
        display_relative = ""
        if normalized:
            _, target_path = _join_workspace_path(normalized)
            display_relative = _normalize_relative_path(normalized)
        entries = get_sandbox().list_directory(target_path)
        return tool_success(
            f"Listed {len(entries)} entries in {display_relative or 'workspace root'}",
            workspace_path=workspace_path,
            directory_path=target_path,
            relative_path=display_relative,
            entries=entries,
            entry_count=len(entries),
        )
    except Exception as exc:
        return tool_error(str(exc) or "Failed to list workspace files.")
