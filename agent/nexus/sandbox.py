"""E2B Desktop Sandbox wrapper — provides all computer control primitives."""

from __future__ import annotations

import base64
import io
import logging
import socket
import time
from typing import Optional

import httpcore
import httpx
from PIL import Image

from nexus.config import settings

logger = logging.getLogger(__name__)


class SandboxDeadError(RuntimeError):
    """Raised when the E2B sandbox has timed out or been destroyed."""


class SandboxManager:
    """Manages a single E2B Desktop sandbox instance."""

    def __init__(self, *, e2b_api_key: str = "") -> None:
        self._sandbox = None
        self._stream_url: Optional[str] = None
        self._e2b_api_key = e2b_api_key

    @property
    def is_alive(self) -> bool:
        return self._sandbox is not None

    @property
    def stream_url(self) -> Optional[str]:
        return self._stream_url

    def _require_sandbox(self) -> None:
        """Raise SandboxDeadError if sandbox is gone."""
        if self._sandbox is None:
            raise SandboxDeadError(
                "Sandbox is not running. It may have timed out. "
                "Please end this session and create a new one."
            )

    def extend_timeout(self, timeout: int = 300) -> None:
        """Best-effort extend sandbox lifetime."""
        if self._sandbox:
            try:
                self._sandbox.set_timeout(timeout)
            except Exception:
                logger.debug("Failed to extend sandbox timeout", exc_info=True)

    # -- Lifecycle -----------------------------------------------------------

    def create(self) -> dict:
        """Boot a new E2B desktop sandbox. Returns {sandbox_id, stream_url}."""
        from e2b_desktop import Sandbox

        retries = max(settings.sandbox_create_retries, 1)
        backoff = max(settings.sandbox_create_retry_backoff_seconds, 0.0)
        max_backoff = max(settings.sandbox_create_retry_max_seconds, backoff)

        def is_transient(exc: Exception) -> bool:
            return isinstance(
                exc,
                (
                    socket.gaierror,
                    httpx.ConnectError,
                    httpx.RemoteProtocolError,
                    httpx.TimeoutException,
                    httpcore.ConnectError,
                    httpcore.RemoteProtocolError,
                ),
            )

        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                suffix = f" (attempt {attempt}/{retries})" if retries > 1 else ""
                logger.info("Creating E2B desktop sandbox%s...", suffix)
                self._sandbox = Sandbox.create(
                    api_key=self._e2b_api_key or None,
                    resolution=(settings.sandbox_resolution_w, settings.sandbox_resolution_h),
                    timeout=settings.sandbox_timeout_seconds,
                )
                self._sandbox.stream.start(require_auth=False)
                self._stream_url = self._sandbox.stream.get_url()
                logger.info("Sandbox ready -- stream URL: %s", self._stream_url)
                self._set_wallpaper()
                return {
                    "sandbox_id": self._sandbox.sandbox_id,
                    "stream_url": self._stream_url,
                }
            except Exception as exc:
                last_exc = exc
                if self._sandbox is not None:
                    try:
                        self._sandbox.kill()
                    except Exception:
                        logger.warning("Failed to cleanup sandbox after create error", exc_info=True)
                    finally:
                        self._sandbox = None
                        self._stream_url = None
                if is_transient(exc) and attempt < retries:
                    delay = min(backoff * (2 ** (attempt - 1)), max_backoff)
                    logger.warning(
                        "Sandbox create failed (attempt %s/%s): %s. Retrying in %.1fs",
                        attempt,
                        retries,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                raise

        raise RuntimeError("Sandbox creation failed") from last_exc

    def _set_wallpaper(self) -> None:
        """Set a custom Windows 11 wallpaper via XFCE config. Cosmetic — errors are swallowed."""
        wallpaper_url = "https://images.wallpapersden.com/image/download/windows-11-4k-esthetics_bWpmZ22UmZqaraWkpJRqZmdlrWdtbWU.jpg"
        cmd = (
            "sleep 3; "
            # Step 1: download the wallpaper image
            f"curl -L -o /tmp/nexus_bg.jpg '{wallpaper_url}' 2>/dev/null || "
            f"wget -O /tmp/nexus_bg.jpg '{wallpaper_url}' 2>/dev/null; "
            # Step 2: write into ALL existing XFCE last-image properties
            "for p in $(xfconf-query -c xfce4-desktop -l 2>/dev/null | grep 'last-image'); do "
            "  xfconf-query -c xfce4-desktop -p \"$p\" -s /tmp/nexus_bg.jpg 2>/dev/null || true; "
            "done; "
            "xfconf-query -c xfce4-desktop "
            "  -p /backdrop/screen0/monitorVirtual-1/workspace0/last-image "
            "  -s /tmp/nexus_bg.jpg --create -t string 2>/dev/null || true; "
            "xfconf-query -c xfce4-desktop "
            "  -p /backdrop/screen0/monitorVirtual-1/workspace0/image-style "
            "  -s 4 --create -t int 2>/dev/null || true; "
            # Step 3: restart xfdesktop to pick up the new config
            "pkill xfdesktop 2>/dev/null; sleep 0.5; "
            "DISPLAY=:1 nohup xfdesktop --disable-wm-check >/dev/null 2>&1 & "
            "true"
        )
        try:
            self._sandbox.commands.run(cmd, timeout=35)
            logger.debug("Custom wallpaper applied via curl + xfconf-query")
        except Exception:
            logger.debug("Wallpaper setup failed (non-critical)", exc_info=True)

    def keep_alive(self, timeout: int = 300) -> None:
        """Extend sandbox timeout."""
        if self._sandbox:
            self._sandbox.set_timeout(timeout)

    def pause(self) -> str | None:
        """Snapshot the sandbox state. Returns the sandbox_id so it can be resumed later.

        Clears internal references so ``is_alive`` returns False after this call.
        Returns None if no sandbox is running or if the E2B API call fails.
        """
        if self._sandbox is None:
            return None
        try:
            sandbox_id: str = self._sandbox.sandbox_id
            self._sandbox.pause()
            logger.info("Sandbox paused (id=%s)", sandbox_id)
            return sandbox_id
        except Exception as exc:
            logger.warning("Failed to pause sandbox: %s", exc)
            return None
        finally:
            self._sandbox = None
            self._stream_url = None

    def resume(self, sandbox_id: str) -> dict:
        """Resume a previously paused sandbox. Returns {sandbox_id, stream_url}.

        Raises if the E2B API call fails (e.g. snapshot expired after 24 hours).
        """
        from e2b_desktop import Sandbox

        logger.info("Resuming sandbox %s ...", sandbox_id)
        self._sandbox = Sandbox.resume(
            sandbox_id,
            api_key=self._e2b_api_key or None,
            timeout=settings.sandbox_timeout_seconds,
        )
        self._sandbox.stream.start(require_auth=False)
        self._stream_url = self._sandbox.stream.get_url()
        logger.info("Sandbox resumed -- stream URL: %s", self._stream_url)
        return {
            "sandbox_id": self._sandbox.sandbox_id,
            "stream_url": self._stream_url,
        }

    def destroy(self) -> None:
        """Kill the sandbox."""
        if self._sandbox:
            try:
                self._sandbox.kill()
                logger.info("Sandbox destroyed")
            except Exception as exc:
                logger.warning("Error destroying sandbox: %s", exc)
            finally:
                self._sandbox = None
                self._stream_url = None

    # -- Screen --------------------------------------------------------------

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

    # -- Terminal ------------------------------------------------------------

    def run_command(self, command: str, timeout: int = 30, background: bool = False) -> dict:
        """Run a shell command. Returns {stdout, stderr, exit_code}."""
        self._require_sandbox()
        if background:
            # Launch in background using nohup so it doesn't block
            bg_cmd = f"nohup {command} > /dev/null 2>&1 & echo $!"
            result = self._sandbox.commands.run(bg_cmd, timeout=10)
            pid = (result.stdout or "").strip()
            return {
                "stdout": f"Started in background (PID: {pid})" if pid else "Started in background",
                "stderr": result.stderr or "",
                "exit_code": 0,
            }
        try:
            result = self._sandbox.commands.run(command, timeout=timeout)
            return {
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
                "exit_code": result.exit_code,
            }
        except Exception as e:
            err_msg = str(e)
            # Try to extract structured info from CommandExitException
            stdout = getattr(e, 'stdout', '') or ''
            stderr = getattr(e, 'stderr', '') or err_msg
            exit_code = getattr(e, 'exit_code', -1)
            if "deadline exceeded" in err_msg or "timeout" in err_msg.lower():
                stderr = f"Command timed out after {timeout}s. If launching a GUI app, use background=True."
                exit_code = -1
            return {
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code if exit_code is not None else -1,
            }

    # -- Applications --------------------------------------------------------

    def open_url(self, url: str) -> None:
        """Open a URL in the default browser."""
        self._require_sandbox()
        self._sandbox.open(url)
