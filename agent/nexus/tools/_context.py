# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Tool context — provides access to the current sandbox and BG task manager.

Stored per-session via contextvars so that tool functions can retrieve
them without explicit parameter passing.
"""

from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional

if TYPE_CHECKING:
    from nexus.background_tasks import BackgroundTaskManager
    from nexus.history_repository import FirestoreHistoryRepository
    from nexus.production_tasks import ProductionTaskRepository
    from nexus.runtime_config import SessionRuntimeConfig
    from nexus.sandbox import SandboxManager
    from nexus.subagents import SubagentSupervisor
    from nexus.subagent_resources import ToolResourceLocks
    from nexus.task_budget import TaskBudgetGuard

ArtifactCallback = Callable[[dict[str, Any]], Awaitable[None] | None]
SendJsonCallback = Callable[[dict[str, Any]], Awaitable[None]]

_current_sandbox: contextvars.ContextVar["SandboxManager"] = contextvars.ContextVar(
    "_current_sandbox"
)

_current_bg_task_manager: contextvars.ContextVar[Optional["BackgroundTaskManager"]] = (
    contextvars.ContextVar("_current_bg_task_manager", default=None)
)
_current_runtime_config: contextvars.ContextVar["SessionRuntimeConfig"] = (
    contextvars.ContextVar("_current_runtime_config")
)
_current_session_id: contextvars.ContextVar[str] = contextvars.ContextVar("_current_session_id")
_current_run_id: contextvars.ContextVar[str] = contextvars.ContextVar("_current_run_id")
_current_workspace_path: contextvars.ContextVar[str] = contextvars.ContextVar(
    "_current_workspace_path"
)
_current_artifact_callback: contextvars.ContextVar[Optional["ArtifactCallback"]] = (
    contextvars.ContextVar("_current_artifact_callback", default=None)
)
_current_owner_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "_current_owner_id", default=""
)
_current_history_repository: contextvars.ContextVar[Optional["FirestoreHistoryRepository"]] = (
    contextvars.ContextVar("_current_history_repository", default=None)
)
_current_production_task_repository: contextvars.ContextVar[Optional["ProductionTaskRepository"]] = (
    contextvars.ContextVar("_current_production_task_repository", default=None)
)
_current_task_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "_current_task_id", default=""
)
_current_send_json: contextvars.ContextVar[Optional["SendJsonCallback"]] = (
    contextvars.ContextVar("_current_send_json", default=None)
)
_current_subagent_supervisor: contextvars.ContextVar[Optional["SubagentSupervisor"]] = (
    contextvars.ContextVar("_current_subagent_supervisor", default=None)
)
_current_subagent_resource_locks: contextvars.ContextVar[Optional["ToolResourceLocks"]] = (
    contextvars.ContextVar("_current_subagent_resource_locks", default=None)
)
_current_task_budget_guard: contextvars.ContextVar[Optional["TaskBudgetGuard"]] = (
    contextvars.ContextVar("_current_task_budget_guard", default=None)
)
# None = unrestricted (empty user selection). A frozenset restricts gateable tools.
_current_tool_allowlist: contextvars.ContextVar[Optional[frozenset[str]]] = (
    contextvars.ContextVar("_current_tool_allowlist", default=None)
)

_ensure_sandbox_callback: contextvars.ContextVar[Optional[Callable[[], Awaitable[None]]]] = (
    contextvars.ContextVar("_ensure_sandbox_callback", default=None)
)

# question, optional multiple-choice labels
AskUserCallback = Callable[..., Awaitable[Optional[str]]]

_ask_user_callback: contextvars.ContextVar[Optional["AskUserCallback"]] = (
    contextvars.ContextVar("_ask_user_callback", default=None)
)
# Mutable single-element list so increments inside the same turn context are visible
# across tool invocations without re-setting the contextvar.
_worker_call_counter: contextvars.ContextVar[Optional[list[int]]] = (
    contextvars.ContextVar("_worker_call_counter", default=None)
)


def set_ask_user_callback(callback: "AskUserCallback | None") -> contextvars.Token:
    """Set the async callback that asks the user a question and awaits the answer."""
    return _ask_user_callback.set(callback)


def get_ask_user_callback() -> "AskUserCallback | None":
    """Retrieve the ask-user callback for the current execution context."""
    return _ask_user_callback.get()


def reset_worker_call_count() -> None:
    """Reset the per-turn foreground worker invocation counter."""
    _worker_call_counter.set([0])


def increment_worker_call_count() -> int:
    """Increment and return the per-turn worker invocation count."""
    counter = _worker_call_counter.get()
    if counter is None:
        counter = [0]
        _worker_call_counter.set(counter)
    counter[0] += 1
    return counter[0]


def set_ensure_sandbox_callback(callback: Callable[[], Awaitable[None]] | None) -> contextvars.Token:
    """Set the async callback that boots the sandbox if it isn't already alive."""
    return _ensure_sandbox_callback.set(callback)


async def ensure_sandbox() -> "SandboxManager":
    """Ensure the sandbox is alive before use. Boots it lazily if needed.

    Call this at the top of any tool that requires sandbox access.
    Returns the sandbox manager for convenience.
    """
    callback = _ensure_sandbox_callback.get()
    if callback is not None:
        await callback()
    return get_sandbox()


def set_sandbox(sandbox: "SandboxManager") -> contextvars.Token:
    """Set the sandbox for the current execution context."""
    return _current_sandbox.set(sandbox)


def get_sandbox() -> "SandboxManager":
    """Retrieve the sandbox for the current execution context."""
    try:
        return _current_sandbox.get()
    except LookupError:
        raise RuntimeError("No sandbox in current context. Was set_sandbox() called?")


def set_bg_task_manager(manager: "BackgroundTaskManager") -> contextvars.Token:
    """Set the background task manager for the current execution context."""
    return _current_bg_task_manager.set(manager)


def get_bg_task_manager() -> Optional["BackgroundTaskManager"]:
    """Retrieve the background task manager (may be None)."""
    return _current_bg_task_manager.get()


def set_runtime_config(runtime_config: "SessionRuntimeConfig") -> contextvars.Token:
    """Set the runtime configuration for the current execution context."""
    return _current_runtime_config.set(runtime_config)


def get_runtime_config() -> "SessionRuntimeConfig":
    """Retrieve the runtime configuration for the current execution context."""
    try:
        return _current_runtime_config.get()
    except LookupError:
        raise RuntimeError(
            "No runtime config in current context. Was set_runtime_config() called?"
        )


def set_session_id(session_id: str) -> contextvars.Token:
    """Set the session ID for the current execution context."""
    return _current_session_id.set(session_id)


def get_session_id() -> str:
    """Retrieve the session ID for the current execution context."""
    try:
        return _current_session_id.get()
    except LookupError:
        raise RuntimeError("No session ID in current context. Was set_session_id() called?")


def set_run_id(run_id: str) -> contextvars.Token:
    """Set the run ID for the current execution context."""
    return _current_run_id.set(run_id)


def get_run_id() -> str:
    """Retrieve the run ID for the current execution context."""
    try:
        return _current_run_id.get()
    except LookupError:
        raise RuntimeError("No run ID in current context. Was set_run_id() called?")


def set_workspace_path(workspace_path: str) -> contextvars.Token:
    """Set the active workspace path for the current execution context."""
    return _current_workspace_path.set(workspace_path)


def get_workspace_path() -> str:
    """Retrieve the active workspace path for the current execution context."""
    try:
        return _current_workspace_path.get()
    except LookupError:
        raise RuntimeError(
            "No workspace path in current context. Was set_workspace_path() called?"
        )


def set_artifact_callback(callback: "ArtifactCallback" | None) -> contextvars.Token:
    """Set the output-artifact callback for the current execution context."""
    return _current_artifact_callback.set(callback)


def get_artifact_callback() -> Optional["ArtifactCallback"]:
    """Retrieve the output-artifact callback, if one is bound."""
    return _current_artifact_callback.get()


def set_owner_id(owner_id: str) -> contextvars.Token:
    """Set the authenticated owner ID for the current execution context."""
    return _current_owner_id.set(owner_id)


def get_owner_id() -> str:
    """Retrieve the authenticated owner ID for integration tools."""
    return _current_owner_id.get()


def set_history_repository(
    repository: Optional["FirestoreHistoryRepository"],
) -> contextvars.Token:
    """Set the Firestore repository for connector tools."""
    return _current_history_repository.set(repository)


def get_history_repository() -> Optional["FirestoreHistoryRepository"]:
    """Retrieve the Firestore repository for connector tools."""
    return _current_history_repository.get()


def set_production_task_repository(
    repository: Optional["ProductionTaskRepository"],
) -> contextvars.Token:
    """Set the durable production task repository for policy approvals."""
    return _current_production_task_repository.set(repository)


def get_production_task_repository() -> Optional["ProductionTaskRepository"]:
    """Retrieve the durable production task repository, if bound."""
    return _current_production_task_repository.get()


def set_task_id(task_id: str | None) -> contextvars.Token:
    """Set the durable task ID for the current execution context."""
    return _current_task_id.set(task_id or "")


def get_task_id() -> str:
    """Retrieve the durable task ID for the current execution context."""
    return _current_task_id.get()


def set_send_json(callback: Optional["SendJsonCallback"]) -> contextvars.Token:
    """Set the WebSocket send_json callback for UI control tools."""
    return _current_send_json.set(callback)


def get_send_json() -> Optional["SendJsonCallback"]:
    """Retrieve the WebSocket send_json callback for UI control tools."""
    return _current_send_json.get()


def set_subagent_supervisor(
    supervisor: Optional["SubagentSupervisor"],
) -> contextvars.Token:
    """Set the hidden subagent supervisor for actor-model tools."""
    return _current_subagent_supervisor.set(supervisor)


def get_subagent_supervisor() -> Optional["SubagentSupervisor"]:
    """Retrieve the hidden subagent supervisor, if bound."""
    return _current_subagent_supervisor.get()


def set_subagent_resource_locks(
    locks: Optional["ToolResourceLocks"],
) -> contextvars.Token:
    """Set shared resource locks for parallel subagent tool execution."""
    return _current_subagent_resource_locks.set(locks)


def get_subagent_resource_locks() -> Optional["ToolResourceLocks"]:
    """Retrieve shared resource locks, if bound."""
    return _current_subagent_resource_locks.get()


def set_task_budget_guard(
    guard: Optional["TaskBudgetGuard"],
) -> contextvars.Token:
    """Bind the mutable durable-run budget guard."""
    return _current_task_budget_guard.set(guard)


def get_task_budget_guard() -> Optional["TaskBudgetGuard"]:
    """Return the active durable-run budget guard, if any."""
    return _current_task_budget_guard.get()


def set_tool_allowlist(allowlist: frozenset[str] | None) -> contextvars.Token:
    """Bind the per-turn tool allowlist (None = unrestricted)."""
    return _current_tool_allowlist.set(allowlist)


def get_tool_allowlist() -> frozenset[str] | None:
    """Return the active per-turn tool allowlist, or None if unrestricted."""
    return _current_tool_allowlist.get()


def clear_tool_allowlist() -> None:
    """Reset the per-turn tool allowlist to unrestricted."""
    _current_tool_allowlist.set(None)
