# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Mouse and keyboard tools for E2B desktop control."""

from __future__ import annotations

import logging

from nexus.tools.base import normalized_tool, tool_error, tool_success

logger = logging.getLogger(__name__)


def _mark_screen_changed(action: str) -> None:
    """Mark visual state as stale after a desktop action."""
    from nexus.tools.screen import mark_screen_changed
    from nexus.tools.screen_state import mark_dirty
    mark_screen_changed(action)
    mark_dirty(action)


@normalized_tool
def move_mouse(x: int, y: int) -> dict:
    """Move the mouse cursor to screen coordinates (x, y) without clicking.

    Use this to hover over elements, reveal tooltips, or position the cursor
    before scrolling. The cursor movement is visible on the VNC stream.

    Args:
        x: Horizontal position from left edge (0-1324).
        y: Vertical position from top edge (0-968).

    Returns:
        NormalizedToolResult confirming cursor position.
    """
    try:
        from nexus.tools._context import get_sandbox
        sandbox = get_sandbox()
        sandbox.move_mouse(x, y)
        _mark_screen_changed("move_mouse")
        return tool_success(
            f"Moved mouse to ({x}, {y})",
            x=x, y=y, action="move_mouse",
        )
    except Exception as e:
        logger.error("move_mouse failed: %s", e)
        return tool_error(f"Move mouse to ({x}, {y}) failed: {e}")


@normalized_tool
def left_click(x: int, y: int) -> dict:
    """Click the left mouse button at screen coordinates (x, y).

    Use this to click buttons, links, icons, or any UI element.
    Coordinates are based on the 1324x968 screen resolution.
    IMPORTANT: Take a screenshot after clicking to verify the result.

    Args:
        x: Horizontal position from left edge (0-1324).
        y: Vertical position from top edge (0-968).

    Returns:
        NormalizedToolResult confirming click position.
    """
    try:
        from nexus.tools._context import get_sandbox
        sandbox = get_sandbox()
        sandbox.left_click(x, y)
        _mark_screen_changed("left_click")
        return tool_success(
            f"Left clicked at ({x}, {y})",
            x=x, y=y, action="left_click",
        )
    except Exception as e:
        logger.error("left_click failed: %s", e)
        return tool_error(f"Left click at ({x}, {y}) failed: {e}")


@normalized_tool
def right_click(x: int, y: int) -> dict:
    """Right-click at screen coordinates (x, y) to open context menus.

    Args:
        x: Horizontal position (0-1324).
        y: Vertical position (0-968).

    Returns:
        NormalizedToolResult confirming right-click position.
    """
    try:
        from nexus.tools._context import get_sandbox
        sandbox = get_sandbox()
        sandbox.right_click(x, y)
        _mark_screen_changed("right_click")
        return tool_success(
            f"Right clicked at ({x}, {y})",
            x=x, y=y, action="right_click",
        )
    except Exception as e:
        logger.error("right_click failed: %s", e)
        return tool_error(f"Right click at ({x}, {y}) failed: {e}")


@normalized_tool
def double_click(x: int, y: int) -> dict:
    """Double-click at screen coordinates (x, y) to open files or select text.

    Args:
        x: Horizontal position (0-1324).
        y: Vertical position (0-968).

    Returns:
        NormalizedToolResult confirming double-click position.
    """
    try:
        from nexus.tools._context import get_sandbox
        sandbox = get_sandbox()
        sandbox.double_click(x, y)
        _mark_screen_changed("double_click")
        return tool_success(
            f"Double clicked at ({x}, {y})",
            x=x, y=y, action="double_click",
        )
    except Exception as e:
        logger.error("double_click failed: %s", e)
        return tool_error(f"Double click at ({x}, {y}) failed: {e}")


@normalized_tool
def type_text(text: str) -> dict:
    """Type text at the current cursor position.

    Use this after clicking on a text field, editor, terminal, or any input area.
    The text is typed character by character with realistic delays.

    Args:
        text: The text to type. Can include newlines.

    Returns:
        NormalizedToolResult confirming characters typed.
    """
    try:
        from nexus.tools._context import get_sandbox
        sandbox = get_sandbox()
        sandbox.type_text(text)
        _mark_screen_changed("type_text")
        return tool_success(
            f"Typed {len(text)} characters",
            char_count=len(text), action="type_text",
        )
    except Exception as e:
        logger.error("type_text failed: %s", e)
        return tool_error(f"Type text failed: {e}")


@normalized_tool
def press_key(key: str) -> dict:
    """Press a keyboard key or key combination.

    Examples:
        press_key("enter")       - Press Enter
        press_key("ctrl+c")      - Copy
        press_key("ctrl+v")      - Paste
        press_key("alt+tab")     - Switch windows
        press_key("ctrl+s")      - Save
        press_key("escape")      - Escape
        press_key("tab")         - Tab (move to next form field)
        press_key("backspace")   - Backspace
        press_key("ctrl+shift+t") - Reopen closed tab

    Args:
        key: Key name or combo with '+' separator. Case-insensitive.

    Returns:
        NormalizedToolResult confirming key pressed.
    """
    try:
        from nexus.tools._context import get_sandbox
        sandbox = get_sandbox()
        sandbox.press_key(key)
        _mark_screen_changed("press_key")
        return tool_success(
            f"Pressed {key}",
            key=key, action="press_key",
        )
    except Exception as e:
        logger.error("press_key failed: %s", e)
        return tool_error(f"Press key '{key}' failed: {e}")


@normalized_tool
def scroll_screen(direction: str, amount: int = 3) -> dict:
    """Scroll the screen up or down.

    Args:
        direction: 'up' or 'down'.
        amount: Number of scroll steps (default 3). Use 5+ for faster scrolling.

    Returns:
        NormalizedToolResult confirming scroll direction and amount.
    """
    try:
        from nexus.tools._context import get_sandbox
        sandbox = get_sandbox()
        sandbox.scroll(direction, amount)
        _mark_screen_changed("scroll_screen")
        return tool_success(
            f"Scrolled {direction} by {amount}",
            direction=direction, amount=amount, action="scroll_screen",
        )
    except Exception as e:
        logger.error("scroll_screen failed: %s", e)
        return tool_error(
            f"Scroll {direction} failed: {e}",
            suggested_alternatives=["press_key"],
        )


@normalized_tool
def drag(from_x: int, from_y: int, to_x: int, to_y: int) -> dict:
    """Drag from one screen position to another.

    Use this to move windows, drag files, select text, or resize elements.

    Args:
        from_x: Starting X coordinate.
        from_y: Starting Y coordinate.
        to_x: Ending X coordinate.
        to_y: Ending Y coordinate.

    Returns:
        NormalizedToolResult confirming drag start and end positions.
    """
    try:
        from nexus.tools._context import get_sandbox
        sandbox = get_sandbox()
        sandbox.drag(from_x, from_y, to_x, to_y)
        _mark_screen_changed("drag")
        return tool_success(
            f"Dragged from ({from_x},{from_y}) to ({to_x},{to_y})",
            from_x=from_x, from_y=from_y, to_x=to_x, to_y=to_y,
            action="drag",
        )
    except Exception as e:
        logger.error("drag failed: %s", e)
        return tool_error(f"Drag from ({from_x},{from_y}) to ({to_x},{to_y}) failed: {e}")
