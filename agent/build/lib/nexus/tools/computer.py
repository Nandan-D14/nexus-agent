"""Mouse and keyboard tools for E2B desktop control."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _mark_screen_changed(action: str) -> None:
    """Mark visual state as stale after a desktop action."""
    from nexus.tools.screen import mark_screen_changed

    mark_screen_changed(action)


def move_mouse(x: int, y: int) -> dict:
    """Move the mouse cursor to screen coordinates (x, y) without clicking.

    Use this to hover over elements, reveal tooltips, or position the cursor
    before scrolling. The cursor movement is visible on the VNC stream.

    Args:
        x: Horizontal position from left edge (0-1324).
        y: Vertical position from top edge (0-968).

    Returns:
        dict with status message.
    """
    try:
        from nexus.tools._context import get_sandbox
        sandbox = get_sandbox()
        sandbox.move_mouse(x, y)
        _mark_screen_changed("move_mouse")
        return {"status": "success", "message": f"Moved mouse to ({x}, {y})"}
    except Exception as e:
        logger.error("move_mouse failed: %s", e)
        return {"status": "error", "message": f"Move mouse failed: {e}"}


def left_click(x: int, y: int) -> dict:
    """Click the left mouse button at screen coordinates (x, y).

    Use this to click buttons, links, icons, or any UI element.
    Coordinates are based on the 1324x968 screen resolution.

    Args:
        x: Horizontal position from left edge (0-1324).
        y: Vertical position from top edge (0-968).

    Returns:
        dict with status message.
    """
    try:
        from nexus.tools._context import get_sandbox
        sandbox = get_sandbox()
        sandbox.left_click(x, y)
        _mark_screen_changed("left_click")
        return {"status": "success", "message": f"Left clicked at ({x}, {y})"}
    except Exception as e:
        logger.error("left_click failed: %s", e)
        return {"status": "error", "message": f"Left click failed: {e}"}


def right_click(x: int, y: int) -> dict:
    """Right-click at screen coordinates (x, y) to open context menus.

    Args:
        x: Horizontal position (0-1324).
        y: Vertical position (0-968).

    Returns:
        dict with status message.
    """
    try:
        from nexus.tools._context import get_sandbox
        sandbox = get_sandbox()
        sandbox.right_click(x, y)
        _mark_screen_changed("right_click")
        return {"status": "success", "message": f"Right clicked at ({x}, {y})"}
    except Exception as e:
        logger.error("right_click failed: %s", e)
        return {"status": "error", "message": f"Right click failed: {e}"}


def double_click(x: int, y: int) -> dict:
    """Double-click at screen coordinates (x, y) to open files or select text.

    Args:
        x: Horizontal position (0-1324).
        y: Vertical position (0-968).

    Returns:
        dict with status message.
    """
    try:
        from nexus.tools._context import get_sandbox
        sandbox = get_sandbox()
        sandbox.double_click(x, y)
        _mark_screen_changed("double_click")
        return {"status": "success", "message": f"Double clicked at ({x}, {y})"}
    except Exception as e:
        logger.error("double_click failed: %s", e)
        return {"status": "error", "message": f"Double click failed: {e}"}


def type_text(text: str) -> dict:
    """Type text at the current cursor position.

    Use this after clicking on a text field, editor, terminal, or any input area.
    The text is typed character by character with realistic delays.

    Args:
        text: The text to type. Can include newlines.

    Returns:
        dict with status message.
    """
    try:
        from nexus.tools._context import get_sandbox
        sandbox = get_sandbox()
        sandbox.type_text(text)
        _mark_screen_changed("type_text")
        return {"status": "success", "message": f"Typed {len(text)} characters"}
    except Exception as e:
        logger.error("type_text failed: %s", e)
        return {"status": "error", "message": f"Type text failed: {e}"}


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
        dict with status message.
    """
    try:
        from nexus.tools._context import get_sandbox
        sandbox = get_sandbox()
        sandbox.press_key(key)
        _mark_screen_changed("press_key")
        return {"status": "success", "message": f"Pressed {key}"}
    except Exception as e:
        logger.error("press_key failed: %s", e)
        return {"status": "error", "message": f"Press key failed: {e}"}


def scroll_screen(direction: str, amount: int = 3) -> dict:
    """Scroll the screen up or down.

    Args:
        direction: 'up' or 'down'.
        amount: Number of scroll steps (default 3). Use 5+ for faster scrolling.

    Returns:
        dict with status message.
    """
    try:
        from nexus.tools._context import get_sandbox
        sandbox = get_sandbox()
        sandbox.scroll(direction, amount)
        _mark_screen_changed("scroll_screen")
        return {"status": "success", "message": f"Scrolled {direction} by {amount}"}
    except Exception as e:
        logger.error("scroll_screen failed: %s", e)
        return {"status": "error", "message": f"Scroll failed: {e}"}


def drag(from_x: int, from_y: int, to_x: int, to_y: int) -> dict:
    """Drag from one screen position to another.

    Use this to move windows, drag files, select text, or resize elements.

    Args:
        from_x: Starting X coordinate.
        from_y: Starting Y coordinate.
        to_x: Ending X coordinate.
        to_y: Ending Y coordinate.

    Returns:
        dict with status message.
    """
    try:
        from nexus.tools._context import get_sandbox
        sandbox = get_sandbox()
        sandbox.drag(from_x, from_y, to_x, to_y)
        _mark_screen_changed("drag")
        return {"status": "success", "message": f"Dragged from ({from_x},{from_y}) to ({to_x},{to_y})"}
    except Exception as e:
        logger.error("drag failed: %s", e)
        return {"status": "error", "message": f"Drag failed: {e}"}
