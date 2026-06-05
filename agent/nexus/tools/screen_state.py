# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Screen state tracking — prevents blind GUI actions without verification.

The perception-action loop is critical for reliable desktop control:
after every GUI action (click, type, scroll), the agent MUST take a
screenshot to verify the result before acting again. This module tracks
whether the screen has changed since the last screenshot.
"""

from __future__ import annotations

import threading
import time


_screen_state = threading.local()


def mark_dirty(action: str) -> None:
    """Mark the screen as dirty after a GUI-changing action.

    Args:
        action: Name of the action that changed the screen (e.g. "left_click").
    """
    _screen_state.dirty = True
    _screen_state.last_action = action
    _screen_state.changed_at = time.monotonic()


def is_dirty() -> bool:
    """Check if the screen has changed since the last screenshot."""
    return bool(getattr(_screen_state, "dirty", False))


def clear_dirty() -> None:
    """Clear the dirty flag — called by take_screenshot after capturing."""
    _screen_state.dirty = False
    _screen_state.last_action = ""
    _screen_state.changed_at = 0.0


def get_last_action() -> str:
    """Return the name of the last action that dirtied the screen."""
    return str(getattr(_screen_state, "last_action", "") or "")


def time_since_change() -> float:
    """Return seconds since the last screen-changing action, or 0 if clean."""
    changed_at = float(getattr(_screen_state, "changed_at", 0.0) or 0.0)
    if changed_at <= 0:
        return 0.0
    return time.monotonic() - changed_at
