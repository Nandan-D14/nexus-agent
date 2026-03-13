"""Tool context — provides access to the current sandbox and BG task manager.

Stored per-session via contextvars so that tool functions can retrieve
them without explicit parameter passing.
"""

from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from nexus.background_tasks import BackgroundTaskManager
    from nexus.sandbox import SandboxManager

_current_sandbox: contextvars.ContextVar["SandboxManager"] = contextvars.ContextVar(
    "_current_sandbox"
)

_current_bg_task_manager: contextvars.ContextVar[Optional["BackgroundTaskManager"]] = (
    contextvars.ContextVar("_current_bg_task_manager", default=None)
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
