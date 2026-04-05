"""Tool context — provides access to the current sandbox and BG task manager.

Stored per-session via contextvars so that tool functions can retrieve
them without explicit parameter passing.
"""

from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional

if TYPE_CHECKING:
    from nexus.background_tasks import BackgroundTaskManager
    from nexus.runtime_config import SessionRuntimeConfig
    from nexus.sandbox import SandboxManager

ArtifactCallback = Callable[[dict[str, Any]], Awaitable[None] | None]

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
