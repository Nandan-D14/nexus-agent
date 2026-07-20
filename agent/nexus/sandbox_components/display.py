# Proprietary and non-commercial use only.

"""Screen capture, display, and cursor operations for the sandbox."""

from __future__ import annotations

import base64
import io

from PIL import Image

from nexus.sandbox import SandboxDeadError, _coerce_exit_code
from nexus.sandbox_components.base import SandboxComponent


class SandboxDisplay(SandboxComponent):
    def resize_screen(self, width: int, height: int) -> dict:
        """Resize the sandbox virtual display to the given resolution via xrandr."""
        self._require_sandbox()
        mode_label = f"{width}x{height}"
        cmd = (
            f"export DISPLAY=:1; "
            f"xrandr --newmode {mode_label} $(cvt {width} {height} 60 | grep Modeline | cut -d' ' -f3-) 2>/dev/null; "
            f"xrandr --addmode Virtual-1 {mode_label} 2>/dev/null; "
            f"xrandr --output Virtual-1 --mode {mode_label}"
        )
        result = self.run_command(cmd, timeout=15)
        if _coerce_exit_code(result.get("exit_code", -1)) != 0:
            return {"success": False, "error": result.get("stderr", "xrandr failed")}
        return {"success": True, "width": width, "height": height}

    def screenshot(self) -> bytes:
        """Capture the screen as PNG bytes."""
        self._require_sandbox()
        try:
            return bytes(self._sandbox.screenshot())
        except Exception as e:
            if "not found" in str(e).lower() or "timeout" in str(e).lower():
                self._sandbox = None
                raise SandboxDeadError("Sandbox timed out while taking screenshot.") from e
            raise

    def screenshot_base64(self) -> str:
        """Capture the screen as a base64-encoded PNG string."""
        return base64.b64encode(self.screenshot()).decode()

    def screenshot_jpeg(self, quality: int = 85, max_dim: int = 1024) -> bytes:
        """Capture the screen as resized JPEG bytes (smaller for Gemini)."""
        png_bytes = self.screenshot()
        img = Image.open(io.BytesIO(png_bytes))
        img.thumbnail((max_dim, max_dim))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()

    def screenshot_jpeg_base64(self, quality: int = 85) -> str:
        """Capture as base64-encoded JPEG."""
        return base64.b64encode(self.screenshot_jpeg(quality)).decode()

    def get_screen_size(self) -> tuple[int, int]:
        """Return (width, height) of the sandbox screen."""
        self._require_sandbox()
        return self._sandbox.get_screen_size()

    def get_cursor_position(self) -> tuple[int, int]:
        """Return (x, y) cursor position."""
        self._require_sandbox()
        return self._sandbox.get_cursor_position()
