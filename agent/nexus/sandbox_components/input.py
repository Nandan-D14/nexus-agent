# Proprietary and non-commercial use only.

"""Mouse and keyboard input operations for the sandbox."""

from __future__ import annotations

from nexus.sandbox_components.base import SandboxComponent


class SandboxInput(SandboxComponent):
    # -- Mouse ---------------------------------------------------------------

    def left_click(self, x: int, y: int) -> None:
        """Left-click at screen coordinates."""
        self._require_sandbox()
        self._sandbox.left_click(x, y)

    def right_click(self, x: int, y: int) -> None:
        """Right-click at screen coordinates."""
        self._require_sandbox()
        self._sandbox.right_click(x, y)

    def double_click(self, x: int, y: int) -> None:
        """Double-click at screen coordinates."""
        self._require_sandbox()
        self._sandbox.double_click(x, y)

    def triple_click(self, x: int, y: int) -> None:
        """Triple-click at screen coordinates to select a line or paragraph.

        E2B's desktop sandbox has no native triple-click, so this issues three
        rapid left-clicks at the same point, which most desktop apps interpret
        as a triple-click (paragraph/line selection).
        """
        self._require_sandbox()
        self._sandbox.left_click(x, y)
        self._sandbox.left_click(x, y)
        self._sandbox.left_click(x, y)

    def move_mouse(self, x: int, y: int) -> None:
        """Move mouse to coordinates without clicking."""
        self._require_sandbox()
        self._sandbox.move_mouse(x, y)

    def drag(self, from_x: int, from_y: int, to_x: int, to_y: int) -> None:
        """Drag from one point to another."""
        self._require_sandbox()
        self._sandbox.drag(fr=(from_x, from_y), to=(to_x, to_y))

    def scroll(self, direction: str = "down", amount: int = 3) -> None:
        """Scroll the screen. direction: 'up' or 'down'."""
        self._require_sandbox()
        self._sandbox.scroll(direction, amount)

    # -- Keyboard ------------------------------------------------------------

    def type_text(self, text: str) -> None:
        """Type text at the current cursor position."""
        self._require_sandbox()
        self._sandbox.write(text, chunk_size=25, delay_in_ms=75)

    def press_key(self, key: str) -> None:
        """Press a key or key combination. Examples: 'enter', 'ctrl+c', 'alt+tab'."""
        self._require_sandbox()
        key_aliases = {
            "return": "enter",
            "esc": "escape",
            "del": "delete",
            "control": "ctrl",
            "command": "meta",
            "cmd": "meta",
            "option": "alt",
            "spacebar": "space",
            "pgup": "pageup",
            "pgdn": "pagedown",
        }

        def normalize(part: str) -> str:
            lowered = part.strip().lower()
            return key_aliases.get(lowered, lowered)

        if "+" in key:
            combo = [normalize(part) for part in key.split("+") if part.strip()]
            self._sandbox.press(combo)
        else:
            self._sandbox.press(normalize(key))
