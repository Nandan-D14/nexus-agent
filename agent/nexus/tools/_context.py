"""Tool context — provides access to the current sandbox and BG task manager.

Stored per-session via contextvars so that tool functions can retrieve
them without explicit parameter passing.
"""

from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from nexus.background_tasks import BackgroundTaskManager
    from nexus.runtime_config import SessionRuntimeConfig
    from nexus.sandbox import SandboxManager

_current_sandbox: contextvars.ContextVar["SandboxManager"] = contextvars.ContextVar(
    "_current_sandbox"
)

_current_bg_task_manager: contextvars.ContextVar[Optional["BackgroundTaskManager"]] = (
    contextvars.ContextVar("_current_bg_task_manager", default=None)
)
_current_runtime_config: contextvars.ContextVar["SessionRuntimeConfig"] = (
    contextvars.ContextVar("_current_runtime_config")
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
