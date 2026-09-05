# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Verification guard for the typed perception-action loop."""

from __future__ import annotations

from nexus.tools.screen_state import get_last_action, is_dirty, time_since_change

_GUI_ACTIONS = frozenset({
    "move_mouse", "left_click", "right_click", "double_click", "triple_click",
    "type_text", "press_key", "scroll_screen", "drag",
    "open_browser",
    "playwright_navigate", "playwright_click", "playwright_type",
})


def should_verify_before_action(action_name: str) -> str | None:
    """Check if the agent must refresh its observation before this action.

    Returns a blocking reason if the screen is dirty and the action mutates
    shared browser/desktop state, or ``None`` when execution is safe.

    Args:
        action_name: Name of the tool being called.
    """
    if action_name not in _GUI_ACTIONS:
        return None
    if not is_dirty():
        return None

    last = get_last_action()
    elapsed = time_since_change()
    return (
        f"Screen changed since the last observation (last action: {last}, "
        f"{elapsed:.1f}s ago). Observe with take_screenshot, playwright_snapshot, "
        f"playwright_get_text, or playwright_verify before '{action_name}'."
    )
