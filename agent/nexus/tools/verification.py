# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Verification guard — enforces the perception-action loop.

Before executing a GUI action, this module checks whether the screen has
changed since the last screenshot. If so, it returns a warning message
that the tool gateway injects into the tool result, prompting the LLM
to take a screenshot first.
"""

from __future__ import annotations

from nexus.tools.screen_state import get_last_action, is_dirty, time_since_change

_GUI_ACTIONS = frozenset({
    "move_mouse", "left_click", "right_click", "double_click",
    "type_text", "press_key", "scroll_screen", "drag",
    "open_browser",
})


def should_verify_before_action(action_name: str) -> str | None:
    """Check if the agent should take a screenshot before this action.

    Returns a warning message if the screen is dirty and the action is a
    GUI action, or None if no verification is needed.

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
        f"WARNING: Screen changed since last screenshot (last action: {last}, "
        f"{elapsed:.1f}s ago). Take a screenshot to verify the current state "
        f"before performing '{action_name}'."
    )
