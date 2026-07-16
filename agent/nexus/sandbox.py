# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""E2B Desktop Sandbox wrapper — provides all computer control primitives."""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import json
import shlex
import socket
import threading
import time
from typing import Optional

import httpcore
import httpx
from PIL import Image

from nexus.config import settings

logger = logging.getLogger(__name__)


def _coerce_exit_code(value: object) -> int:
    try:
        if value is None:
            return -1
        return int(value)
    except (TypeError, ValueError):
        return -1


class SandboxDeadError(RuntimeError):
    """Raised when the E2B sandbox has timed out or been destroyed."""


class SandboxSweeper:
    """Background worker that kills orphaned E2B sandboxes."""

    def __init__(self, history_repo, e2b_api_key: str = ""):
        self.history_repo = history_repo
        self.e2b_api_key = e2b_api_key or settings.e2b_api_key
        self._running = False
        self._task = None

    async def start(self, interval_seconds: int = 3600):
        """Start the sweeper loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(interval_seconds))
        logger.info("Sandbox sweeper started (interval=%ds)", interval_seconds)

    async def stop(self):
        """Stop the sweeper loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Sandbox sweeper stopped")

    async def _loop(self, interval_seconds: int):
        while self._running:
            try:
                await self.sweep()
            except Exception:
                logger.exception("Error during sandbox sweep")
            await asyncio.sleep(interval_seconds)

    async def sweep(self):
        """Find and kill sandboxes that are not associated with any active session."""
        logger.info("Starting sandbox sweep...")
        
        # 1. Get all active sandbox IDs from Firestore
        active_ids = set(await self.history_repo.list_all_active_sandbox_ids())
        
        # 2. List all running sandboxes from E2B
        running_ids = await list_running_e2b_sandbox_ids(self.e2b_api_key)
        if running_ids is None:
            return

        killed_count = 0
        from e2b_desktop import Sandbox

        for sid in running_ids:
            if sid not in active_ids:
                logger.info("Killing orphaned sandbox: %s", sid)
                try:
                    await asyncio.to_thread(lambda: Sandbox.connect(sid, api_key=self.e2b_api_key or None).kill())
                    killed_count += 1
                except Exception:
                    logger.warning("Failed to kill orphaned sandbox %s", sid, exc_info=True)
        
        if killed_count > 0:
            logger.info("Sandbox sweep complete. Killed %d orphaned sandboxes.", killed_count)
        else:
            logger.info("Sandbox sweep complete. No orphans found.")


def _sandbox_info_id(info: object) -> str | None:
    value = getattr(info, "sandbox_id", None) or getattr(info, "id", None)
    return value if isinstance(value, str) and value else None


def _paginator_items(paginator: object) -> list[object]:
    items: list[object] = []
    current = paginator
    while True:
        batch = current.next_items()
        items.extend(batch)
        if not current.has_next:
            break
    return items


async def list_running_e2b_sandbox_ids(e2b_api_key: str = "") -> set[str] | None:
    """Return running E2B sandbox ids, or None if verification is unavailable."""
    try:
        from e2b_desktop import Sandbox

        paginator = await asyncio.to_thread(
            Sandbox.list,
            api_key=e2b_api_key or None,
        )
        running_sandboxes = await asyncio.to_thread(_paginator_items, paginator)
        return {
            sandbox_id
            for sandbox_id in (_sandbox_info_id(info) for info in running_sandboxes)
            if sandbox_id
        }
    except Exception:
        logger.warning("Failed to list running E2B sandboxes", exc_info=True)
        return None


class SandboxLifecycleController:
    """Verifies sandbox truth and reconciles stale Firestore session state."""

    def __init__(self, history_repo, e2b_api_key: str = "") -> None:
        self.history_repo = history_repo
        self.e2b_api_key = e2b_api_key or settings.e2b_api_key

    async def list_verified_active_sessions(
        self,
        owner_id: str,
        *,
        e2b_api_key: str = "",
    ) -> list[dict]:
        sessions = await self.history_repo.list_active_sessions(owner_id)
        if not sessions:
            return []

        running_ids = await list_running_e2b_sandbox_ids(e2b_api_key or self.e2b_api_key)
        if running_ids is None:
            return []

        verified: list[dict] = []
        for session in sessions:
            sandbox_id = session.get("sandbox_id")
            if isinstance(sandbox_id, str) and sandbox_id in running_ids:
                session["sandbox_verification"] = "verified"
                verified.append(session)
                continue

            session_id = session.get("session_id")
            if isinstance(session_id, str) and session_id:
                await self.history_repo.mark_session_sandbox_unavailable(
                    session_id,
                    reason="sandbox_not_running",
                )
        return verified


class SandboxManager:
    """Manages a single E2B Desktop sandbox instance."""

    def __init__(self, *, e2b_api_key: str = "") -> None:
        self._sandbox = None
        self._stream_url: Optional[str] = None
        self._e2b_api_key = e2b_api_key
        # Browser tools may race during a new session. One launch attempt per
        # sandbox avoids conflicting Chromium processes sharing the CDP port.
        self._chromium_cdp_lock = threading.Lock()

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

    def extend_timeout(self, timeout: int = 900) -> None:
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
                self._provision_sandbox()
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

    def _provision_sandbox(self) -> None:
        """Pre-install task libraries and provision one Chromium CDP target."""
        libs = ["weasyprint", "openpyxl", "python-docx", "fpdf2", "markdown2", "pandas", "yfinance", "matplotlib", "seaborn"]
        cmd = f"pip install {' '.join(libs)}"
        try:
            # We run this in the background or with a long timeout
            # For simplicity, we'll just run it with a timeout.
            logger.info("Provisioning sandbox with libraries: %s", libs)
            self._sandbox.commands.run(cmd, timeout=300)
        except Exception as e:
            logger.warning("Sandbox provisioning failed: %s", e)
        try:
            self.ensure_chromium_cdp()
        except Exception as exc:
            logger.warning("Chromium CDP provisioning failed: %s", exc)

    def keep_alive(self, timeout: int = 900) -> None:
        """Extend sandbox timeout."""
        if self._sandbox:
            self._sandbox.set_timeout(timeout)

    def pause(self) -> str | None:
        """Pause the sandbox so it can be resumed later via ``connect``/``resume``.

        Current E2B Desktop SDK exposes ``Sandbox.pause()`` which returns the
        sandbox id. That id is what ``Sandbox.connect(id)`` resumes.
        """
        if not self._sandbox:
            return None
        try:
            sandbox_id = self._sandbox.pause()
            logger.info("Sandbox paused (id=%s)", sandbox_id)
            self._sandbox = None
            self._stream_url = None
            return str(sandbox_id) if sandbox_id else None
        except Exception as exc:
            logger.warning("Sandbox pause failed: %s — destroying instead", exc)
            try:
                self.destroy()
            except Exception:
                self._sandbox = None
                self._stream_url = None
            return None

    def connect(self, sandbox_id: str) -> dict:
        """Connect to an existing (running or paused) sandbox.

        E2B ``Sandbox.connect`` auto-resumes paused sandboxes.
        Returns {sandbox_id, stream_url}.
        """
        from e2b_desktop import Sandbox

        logger.info("Connecting to sandbox %s ...", sandbox_id)
        self._sandbox = Sandbox.connect(
            sandbox_id,
            api_key=self._e2b_api_key or None,
            timeout=settings.sandbox_timeout_seconds,
        )
        self._sandbox.stream.start(require_auth=False)
        self._stream_url = self._sandbox.stream.get_url()
        self.ensure_chromium_cdp()
        logger.info("Sandbox connected -- stream URL: %s", self._stream_url)
        return {
            "sandbox_id": self._sandbox.sandbox_id,
            "stream_url": self._stream_url,
        }

    def resume(self, sandbox_id: str) -> dict:
        """Resume a paused sandbox.

        E2B has no ``Sandbox.resume`` — ``Sandbox.connect`` resumes paused
        sandboxes. This method is the session-layer alias for that path.
        """
        return self.connect(sandbox_id)

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

    def ensure_directory(self, path: str) -> None:
        """Create a directory and its parents inside the sandbox."""
        safe_path = shlex.quote(path)
        result = self.run_command(f"mkdir -p {safe_path}", timeout=30)
        if _coerce_exit_code(result.get("exit_code", -1)) == 0:
            return

        path_b64 = base64.b64encode(path.encode("utf-8")).decode("ascii")
        script = (
            "import base64, pathlib; "
            f"path = base64.b64decode('{path_b64}').decode('utf-8'); "
            "pathlib.Path(path).mkdir(parents=True, exist_ok=True)"
        )
        fallback = self.run_command(f"python3 -c {shlex.quote(script)}", timeout=30)
        if _coerce_exit_code(fallback.get("exit_code", -1)) == 0:
            logger.warning(
                "ensure_directory recovered via python fallback for %s after mkdir failed "
                "(exit=%s, stderr=%s, stdout=%s)",
                path,
                result.get("exit_code"),
                result.get("stderr") or "",
                result.get("stdout") or "",
            )
            return

        logger.error(
            "ensure_directory failed for %s: mkdir exit=%s stderr=%s stdout=%s; "
            "python fallback exit=%s stderr=%s stdout=%s",
            path,
            result.get("exit_code"),
            result.get("stderr") or "",
            result.get("stdout") or "",
            fallback.get("exit_code"),
            fallback.get("stderr") or "",
            fallback.get("stdout") or "",
        )
        raise RuntimeError(
            fallback.get("stderr")
            or result.get("stderr")
            or f"Failed to create directory {path}"
        )

    def write_text_file(self, path: str, content: str, *, append: bool = False) -> None:
        """Write UTF-8 text into a sandbox file."""
        path_b64 = base64.b64encode(path.encode("utf-8")).decode("ascii")
        data_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
        mode = "ab" if append else "wb"
        script = (
            "import base64, pathlib; "
            f"path = base64.b64decode('{path_b64}').decode('utf-8'); "
            f"data = base64.b64decode('{data_b64}'); "
            "target = pathlib.Path(path); "
            "target.parent.mkdir(parents=True, exist_ok=True); "
            f"target.open('{mode}').write(data)"
        )
        result = self.run_command(f"python3 -c {shlex.quote(script)}", timeout=30)
        if _coerce_exit_code(result.get("exit_code", -1)) != 0:
            raise RuntimeError(result.get("stderr") or f"Failed to write file {path}")

    def write_binary_file(self, path: str, content: bytes) -> None:
        """Write binary content into a sandbox file."""
        path_b64 = base64.b64encode(path.encode("utf-8")).decode("ascii")
        data_b64 = base64.b64encode(content).decode("ascii")
        script = (
            "import base64, pathlib; "
            f"path = base64.b64decode('{path_b64}').decode('utf-8'); "
            f"data = base64.b64decode('{data_b64}'); "
            "target = pathlib.Path(path); "
            "target.parent.mkdir(parents=True, exist_ok=True); "
            "target.write_bytes(data)"
        )
        result = self.run_command(f"python3 -c {shlex.quote(script)}", timeout=60)
        if _coerce_exit_code(result.get("exit_code", -1)) != 0:
            raise RuntimeError(result.get("stderr") or f"Failed to write file {path}")

    def read_binary_file(self, path: str) -> bytes:
        """Read binary content from a sandbox file."""
        path_b64 = base64.b64encode(path.encode("utf-8")).decode("ascii")
        script = (
            "import base64, pathlib, sys; "
            f"path = base64.b64decode('{path_b64}').decode('utf-8'); "
            "sys.stdout.write(base64.b64encode(pathlib.Path(path).read_bytes()).decode('ascii'))"
        )
        result = self.run_command(f"python3 -c {shlex.quote(script)}", timeout=60)
        if _coerce_exit_code(result.get("exit_code", -1)) != 0:
            raise RuntimeError(result.get("stderr") or f"Failed to read file {path}")
        return base64.b64decode(str(result.get("stdout") or ""))

    def read_text_file(self, path: str) -> str:
        """Read UTF-8 text from a sandbox file."""
        path_b64 = base64.b64encode(path.encode("utf-8")).decode("ascii")
        script = (
            "import base64, pathlib; "
            f"path = base64.b64decode('{path_b64}').decode('utf-8'); "
            "print(pathlib.Path(path).read_text(encoding='utf-8'))"
        )
        result = self.run_command(f"python3 -c {shlex.quote(script)}", timeout=30)
        if _coerce_exit_code(result.get("exit_code", -1)) != 0:
            raise RuntimeError(result.get("stderr") or f"Failed to read file {path}")
        return str(result.get("stdout") or "")

    def path_exists(self, path: str) -> bool:
        """Return True when the given sandbox path exists."""
        safe_path = shlex.quote(path)
        result = self.run_command(f"test -e {safe_path}", timeout=15)
        return _coerce_exit_code(result.get("exit_code", -1)) == 0

    def list_directory(self, path: str) -> list[dict[str, object]]:
        """Return a shallow directory listing for the given sandbox path."""
        path_b64 = base64.b64encode(path.encode("utf-8")).decode("ascii")
        script = (
            "import base64, json, pathlib; "
            f"path = pathlib.Path(base64.b64decode('{path_b64}').decode('utf-8')); "
            "entries = []; "
            "exists = path.exists(); "
            "iterable = sorted(path.iterdir(), key=lambda item: item.name.lower()) if exists and path.is_dir() else []; "
            "for item in iterable: "
            " entries.append({'name': item.name, 'path': str(item), 'is_dir': item.is_dir(), 'size': item.stat().st_size if item.exists() else 0}); "
            "print(json.dumps(entries))"
        )
        result = self.run_command(f"python3 -c {shlex.quote(script)}", timeout=30)
        if _coerce_exit_code(result.get("exit_code", -1)) != 0:
            raise RuntimeError(result.get("stderr") or f"Failed to list directory {path}")
        raw = str(result.get("stdout") or "").strip()
        if not raw:
            return []
        return list(json.loads(raw))

    # -- Applications --------------------------------------------------------

    def _is_chromium_cdp_port_reachable(self, port: int) -> bool:
        """Probe CDP without allowing a connection refusal to abort provisioning."""
        command = (
            f"if curl -fsS --max-time 2 http://127.0.0.1:{port}/json/version "
            ">/dev/null 2>&1; then printf CDP_READY; fi; exit 0"
        )
        try:
            result = self._sandbox.commands.run(command, timeout=10)
        except Exception as exc:
            logger.debug("Chromium CDP readiness probe failed: %s", exc)
            return False
        return "CDP_READY" in str(getattr(result, "stdout", ""))

    def _can_connect_to_chromium_cdp(self, port: int) -> bool:
        """Verify Playwright can attach to the endpoint, not only reach its HTTP port."""
        script = (
            "from playwright.sync_api import sync_playwright; "
            "p = sync_playwright().start(); "
            f"browser = p.chromium.connect_over_cdp('http://127.0.0.1:{port}'); "
            "print('CDP_CONNECTED'); browser.close(); p.stop()"
        )
        try:
            result = self._sandbox.commands.run(
                f"python3 -c {shlex.quote(script)}",
                timeout=20,
            )
        except Exception as exc:
            logger.debug("Chromium CDP connection probe failed: %s", exc)
            return False
        return (
            _coerce_exit_code(getattr(result, "exit_code", -1)) == 0
            and "CDP_CONNECTED" in str(getattr(result, "stdout", ""))
        )

    def _wait_for_chromium_cdp(self, port: int, timeout_seconds: int) -> bool:
        """Wait for a usable CDP endpoint with bounded exponential backoff."""
        deadline = time.monotonic() + max(1, timeout_seconds)
        delay = max(float(settings.browser_startup_retry_initial_seconds), 0.05)
        max_delay = max(float(settings.browser_startup_retry_max_seconds), delay)
        attempt = 0
        port_reachable_logged = False

        while True:
            if self._is_chromium_cdp_port_reachable(port):
                if not port_reachable_logged:
                    logger.info("Chromium CDP port %s reachable", port)
                    port_reachable_logged = True
                if self._can_connect_to_chromium_cdp(port):
                    logger.info("Chromium CDP connected on port %s", port)
                    return True

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            sleep_for = min(delay, remaining)
            attempt += 1
            logger.debug(
                "Waiting for Chromium CDP on port %s (probe %s, retry in %.2fs)",
                port,
                attempt,
                sleep_for,
            )
            time.sleep(sleep_for)
            delay = min(delay * 2, max_delay)

    def _chromium_log_tail(self) -> str:
        try:
            result = self._sandbox.commands.run(
                "tail -n 40 /tmp/nexus-chromium.log 2>/dev/null || true",
                timeout=10,
            )
            return str(getattr(result, "stdout", "")).strip()[-4000:]
        except Exception:
            return ""

    def ensure_chromium_cdp(self) -> dict:
        """Ensure visible Chromium has a reachable, Playwright-verified CDP endpoint."""
        self._require_sandbox()
        port = int(settings.browser_cdp_port)

        with self._chromium_cdp_lock:
            if self._is_chromium_cdp_port_reachable(port):
                logger.info("Chromium CDP port %s reachable; reusing browser", port)
                if self._can_connect_to_chromium_cdp(port):
                    logger.info("Chromium CDP connected on port %s", port)
                    return {"status": "ready", "port": port, "reused": True}
                logger.warning(
                    "Chromium CDP port %s is reachable but Playwright cannot connect; "
                    "starting a fresh browser process",
                    port,
                )

            import_check = self._sandbox.commands.run(
                "python3 -c 'import playwright'",
                timeout=15,
            )
            if _coerce_exit_code(getattr(import_check, "exit_code", -1)) != 0:
                installed = self._sandbox.commands.run(
                    "pip install playwright && python3 -m playwright install chromium",
                    timeout=300,
                )
                if _coerce_exit_code(getattr(installed, "exit_code", -1)) != 0:
                    raise RuntimeError(
                        getattr(installed, "stderr", "")
                        or "Failed to install Playwright Chromium"
                    )

            launcher = f"""import json
import os
import subprocess
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    executable = p.chromium.executable_path

env = dict(os.environ)
env["DISPLAY"] = ":1"
command = [
    executable,
    "--remote-debugging-port={port}",
    "--remote-debugging-address=127.0.0.1",
    "--user-data-dir=/tmp/nexus-chromium-profile",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--no-first-run",
    "--no-default-browser-check",
    "about:blank",
]
with open("/tmp/nexus-chromium.log", "ab") as log:
    process = subprocess.Popen(
        command,
        env=env,
        stdout=log,
        stderr=log,
        start_new_session=True,
    )
if process.poll() is not None:
    raise SystemExit("Chromium exited immediately with code %s" % process.returncode)
print(json.dumps({{"pid": process.pid, "port": {port}}}))
"""
            logger.info("Starting Chromium with CDP on port %s", port)
            self._sandbox.write_text_file("/tmp/nexus_chromium_cdp.py", launcher)
            result = self._sandbox.commands.run(
                "python3 /tmp/nexus_chromium_cdp.py",
                timeout=30,
            )
            if _coerce_exit_code(getattr(result, "exit_code", -1)) != 0:
                raise RuntimeError(
                    getattr(result, "stderr", "")
                    or getattr(result, "stdout", "")
                    or "Chromium CDP launch failed"
                )

            launch_details: dict[str, object] = {}
            try:
                launch_details = json.loads(str(getattr(result, "stdout", "")).strip())
            except (json.JSONDecodeError, TypeError):
                logger.warning("Chromium launcher returned no process metadata")
            logger.info(
                "Chromium process started (pid=%s, cdp_port=%s)",
                launch_details.get("pid", "unknown"),
                port,
            )

            if not self._wait_for_chromium_cdp(
                port,
                int(settings.browser_startup_timeout_seconds),
            ):
                log_tail = self._chromium_log_tail()
                detail = f" Chromium log tail: {log_tail}" if log_tail else ""
                raise RuntimeError(
                    f"Chromium CDP endpoint on 127.0.0.1:{port} did not become "
                    f"ready within {settings.browser_startup_timeout_seconds}s.{detail}"
                )
            return {"status": "ready", "port": port, "reused": False}

    def open_url(self, url: str) -> None:
        """Open a URL in the provisioned visible Chromium CDP browser."""
        self._require_sandbox()
        self.ensure_chromium_cdp()
        url_b64 = base64.b64encode(url.encode("utf-8")).decode("ascii")
        port = int(settings.browser_cdp_port)
        script = (
            "import base64; "
            "from playwright.sync_api import sync_playwright; "
            f"url=base64.b64decode('{url_b64}').decode('utf-8'); "
            "p=sync_playwright().start(); "
            f"browser=p.chromium.connect_over_cdp('http://127.0.0.1:{port}'); "
            "context=browser.contexts[0] if browser.contexts else browser.new_context(); "
            "page=context.pages[0] if context.pages else context.new_page(); "
            "page.goto(url, wait_until='domcontentloaded', timeout=30000); "
            "print(page.url); "
            "browser.close(); p.stop()"
        )
        result = self._sandbox.commands.run(
            f"python3 -c {shlex.quote(script)}",
            timeout=45,
        )
        if _coerce_exit_code(getattr(result, "exit_code", -1)) != 0:
            raise RuntimeError(
                getattr(result, "stderr", "")
                or "Failed to navigate Chromium"
            )
