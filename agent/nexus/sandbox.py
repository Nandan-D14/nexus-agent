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


SANDBOX_RESTART_MESSAGE = (
    "Sandbox is not running. It will be restarted in this session; "
    "retry the command after reconnect. Do not start a new session."
)

_DEAD_SANDBOX_MARKERS = (
    "sandbox not found",
    "sandbox was not found",
    "sandbox is not found",
    "sandbox not running",
    "sandbox is not running",
    "sandbox has been killed",
    "sandbox has been paused",
    "sandbox does not exist",
    "no sandbox found",
    "404 not found",
    "status code 404",
    "not found for url",
)


def is_dead_sandbox_error(
    exc: BaseException | str,
    *,
    include_timeout: bool = False,
) -> bool:
    """Return True when an E2B/API error means the remote VM is gone."""
    if isinstance(exc, SandboxDeadError):
        return True
    status = getattr(exc, "status_code", None) if not isinstance(exc, str) else None
    if status is None and not isinstance(exc, str):
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 404:
        return True
    if not isinstance(exc, str) and "notfound" in type(exc).__name__.lower():
        return True
    text = str(exc).lower()
    if any(marker in text for marker in _DEAD_SANDBOX_MARKERS):
        return True
    if include_timeout and (
        "timeout" in text or "timed out" in text or "deadline exceeded" in text
    ):
        return True
    return False


class SandboxDeadError(RuntimeError):
    """Raised when the E2B sandbox has timed out or been destroyed."""

    def __init__(self, message: str = SANDBOX_RESTART_MESSAGE) -> None:
        super().__init__(message)


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


_INVALID_SANDBOX_IDS = frozenset({"true", "false", "none", "null"})


def is_valid_sandbox_id(value: object) -> bool:
    """Return True for a real E2B sandbox id, not SDK booleans serialized as strings."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    if len(text) < 8 or text.lower() in _INVALID_SANDBOX_IDS:
        return False
    return True


def _sandbox_info_id(info: object) -> str | None:
    value = getattr(info, "sandbox_id", None) or getattr(info, "id", None)
    return value if is_valid_sandbox_id(value) else None


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
        # Display / input / files / browser concerns are delegated to bound
        # components (built lazily). See __getattr__.
        self._components = None

    def _ensure_components(self):
        components = self.__dict__.get("_components")
        if components is None:
            from nexus.sandbox_components import (
                SandboxBrowser,
                SandboxDisplay,
                SandboxFiles,
                SandboxInput,
            )

            self._display = SandboxDisplay(self)
            self._input = SandboxInput(self)
            self._files = SandboxFiles(self)
            self._browser = SandboxBrowser(self)
            components = (self._display, self._input, self._files, self._browser)
            self._components = components
        return components

    def __getattr__(self, name: str):
        # Only invoked for methods moved to a bound component (display, input,
        # files, browser). Method names are unique across components; the
        # class-level lookup avoids triggering the components' own __getattr__.
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        for component in self._ensure_components():
            if getattr(type(component), name, None) is not None:
                return getattr(component, name)
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}"
        )

    @property
    def is_alive(self) -> bool:
        return self._sandbox is not None

    @property
    def stream_url(self) -> Optional[str]:
        return self._stream_url

    def get_preview_url(self, port: int) -> str:
        """Public HTTPS URL for a port listening inside the sandbox."""
        self._require_sandbox()
        try:
            host = str(self._sandbox.get_host(int(port)) or "").strip()
        except Exception as exc:
            self._raise_if_dead(exc)
            raise
        if not host:
            raise RuntimeError(f"Sandbox did not return a host for port {port}")
        if host.startswith("http://") or host.startswith("https://"):
            return host
        return f"https://{host}"

    def probe_listening_port(self, port: int, *, timeout: int = 4) -> bool:
        """Return True if something is accepting TCP connections on 127.0.0.1:port."""
        self._require_sandbox()
        script = (
            "import socket, sys\n"
            f"port = {int(port)}\n"
            "sock = socket.socket()\n"
            "sock.settimeout(3)\n"
            "try:\n"
            "    sock.connect(('127.0.0.1', port))\n"
            "    print('ok')\n"
            "except Exception as exc:\n"
            "    print('fail:' + type(exc).__name__)\n"
            "    sys.exit(1)\n"
            "finally:\n"
            "    sock.close()\n"
        )
        result = self.run_command(f"python3 -c {shlex.quote(script)}", timeout=max(timeout, 5))
        return _coerce_exit_code(result.get("exit_code", -1)) == 0

    def find_listening_web_ports(self) -> list[int]:
        """Find common web dev ports accepting TCP connections inside the sandbox."""
        if self._sandbox is None:
            return []
        script = (
            "import socket\n"
            "found = []\n"
            "for p in [5173, 3001, 3000, 8080, 8000, 5000, 4173, 8088, 80]:\n"
            "    s = socket.socket()\n"
            "    s.settimeout(0.3)\n"
            "    try:\n"
            "        s.connect(('127.0.0.1', p))\n"
            "        found.append(p)\n"
            "    except Exception:\n"
            "        pass\n"
            "    finally:\n"
            "        s.close()\n"
            "print(','.join(map(str, found)))\n"
        )
        try:
            result = self.run_command(f"python3 -c {shlex.quote(script)}", timeout=5)
            out = (result.get("stdout") or "").strip()
            if not out:
                return []
            return [int(p.strip()) for p in out.split(",") if p.strip().isdigit()]
        except Exception:
            return []

    def mark_dead(self) -> None:
        """Drop a stale E2B client without attempting to kill the remote VM."""
        if self._sandbox is not None or self._stream_url is not None:
            logger.info("Dropping stale sandbox client (remote VM is gone)")
        self._sandbox = None
        self._stream_url = None

    def _require_sandbox(self) -> None:
        """Raise SandboxDeadError if sandbox is gone."""
        if self._sandbox is None:
            raise SandboxDeadError()

    def _raise_if_dead(self, exc: BaseException) -> None:
        """Mark the client dead and raise SandboxDeadError for remote-gone faults."""
        if is_dead_sandbox_error(exc):
            self.mark_dead()
            raise SandboxDeadError() from exc

    def extend_timeout(self, timeout: int | None = None) -> bool:
        """Extend sandbox lifetime. Returns False and marks dead on failure."""
        seconds = settings.sandbox_timeout_seconds if timeout is None else timeout
        if not self._sandbox:
            return False
        try:
            self._sandbox.set_timeout(seconds)
            return True
        except Exception:
            logger.info("Failed to extend sandbox timeout; marking client dead", exc_info=True)
            self.mark_dead()
            return False

    # -- Lifecycle -----------------------------------------------------------

    def create(self) -> dict:
        """Boot a new E2B desktop sandbox. Returns {sandbox_id, stream_url}."""
        from e2b_desktop import Sandbox

        retries = max(settings.sandbox_create_retries, 1)
        backoff = max(settings.sandbox_create_retry_backoff_seconds, 0.0)
        max_backoff = max(settings.sandbox_create_retry_max_seconds, backoff)

        def is_transient(exc: Exception) -> bool:
            # Transient network faults talking to the E2B API must be retried.
            # WinError 10054 ("connection forcibly closed") surfaces as
            # httpcore.ReadError (a subclass of httpcore.NetworkError); timeouts
            # subclass httpcore.TimeoutException; httpx.TransportError is the
            # base for all httpx connect/read/write/timeout/protocol faults.
            return isinstance(
                exc,
                (
                    socket.gaierror,
                    ConnectionError,  # incl. ConnectionResetError (WinError 10054)
                    httpx.TransportError,
                    httpcore.NetworkError,
                    httpcore.TimeoutException,
                    httpcore.RemoteProtocolError,
                ),
            )

        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                suffix = f" (attempt {attempt}/{retries})" if retries > 1 else ""
                logger.info("Creating E2B desktop sandbox%s...", suffix)
                create_kwargs = dict(
                    api_key=self._e2b_api_key or None,
                    resolution=(settings.sandbox_resolution_w, settings.sandbox_resolution_h),
                    timeout=settings.sandbox_timeout_seconds,
                )
                if settings.sandbox_template_id:
                    create_kwargs["template"] = settings.sandbox_template_id
                self._sandbox = Sandbox.create(**create_kwargs)
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
            # Background the whole script so boot is not blocked on the curl
            # download. Wrap in `sh -c` so nohup covers every statement, not
            # just the leading `sleep`.
            backgrounded = f"nohup sh -c {shlex.quote(cmd)} >/dev/null 2>&1 & echo scheduled"
            self._sandbox.commands.run(backgrounded, timeout=10)
            logger.debug("Custom wallpaper scheduled via curl + xfconf-query (background)")
        except Exception:
            logger.debug("Wallpaper setup failed (non-critical)", exc_info=True)

    def _provision_sandbox(self) -> None:
        """Pre-install task libraries and provision one Chromium CDP target.

        When a pre-baked template is configured the libraries are already in the
        image, so the boot-time ``pip install`` (up to 300s) is skipped.
        """
        if settings.sandbox_template_id:
            logger.info("Skipping runtime provisioning; using pre-baked template %s", settings.sandbox_template_id)
        else:
            libs = ["weasyprint", "openpyxl", "python-docx", "python-pptx", "fpdf2", "markdown2", "pandas", "yfinance", "matplotlib", "seaborn"]
            cmd = f"pip install {' '.join(libs)}"
            try:
                logger.info("Provisioning sandbox with libraries: %s", libs)
                self._sandbox.commands.run(cmd, timeout=300)
            except Exception as e:
                logger.warning("Sandbox provisioning failed: %s", e)

            # Surface silent degradation: boot-time pip can fail without raising,
            # or packages may still be missing after a partial install.
            verify = self.run_command(
                'python3 -c "import docx, openpyxl, pptx, fpdf, markdown2"',
                timeout=60,
            )
            if verify.get("exit_code") != 0:
                logger.error(
                    "Sandbox doc-generation dependencies missing after provisioning: %s",
                    verify.get("stderr") or verify.get("stdout") or verify,
                )

            # Pre-provision Node.js so web/react/vite projects work out of the box
            # without triggering interactive sudo/curl policy approval prompts.
            try:
                node_check = self.run_command("command -v node", timeout=10)
                if not (node_check.get("stdout") and str(node_check.get("stdout")).strip()):
                    logger.info("Node.js missing in sandbox; installing Node.js 20...")
                    self.run_command(
                        "curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt-get install -y nodejs",
                        timeout=180,
                    )
            except Exception as exc:
                logger.warning("Node.js provisioning check failed (non-fatal): %s", exc)
        try:
            self.ensure_chromium_cdp()
        except Exception as exc:
            logger.warning("Chromium CDP provisioning failed: %s", exc)

    def keep_alive(self, timeout: int | None = None) -> bool:
        """Extend sandbox timeout."""
        return self.extend_timeout(timeout)

    def pause(self) -> str | None:
        """Pause the sandbox so it can be resumed later via ``connect``/``resume``.

        Current E2B Desktop SDK's ``Sandbox.pause()`` returns a boolean. Keep
        the existing ``sandbox_id`` so the VM can be resumed later.
        """
        if not self._sandbox:
            return None
        try:
            existing_id = getattr(self._sandbox, "sandbox_id", None)
            paused = self._sandbox.pause()
            logger.info("Sandbox paused (id=%s, existing=%s)", paused, existing_id)
            self._sandbox = None
            self._stream_url = None
            if is_valid_sandbox_id(existing_id):
                return str(existing_id)
            if is_valid_sandbox_id(paused):
                return str(paused)
            return None
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

        if not is_valid_sandbox_id(sandbox_id):
            raise ValueError(f"Invalid sandbox ID: {sandbox_id!r}")
        logger.info("Connecting to sandbox %s ...", sandbox_id)
        self._sandbox = Sandbox.connect(
            sandbox_id,
            api_key=self._e2b_api_key or None,
            timeout=settings.sandbox_timeout_seconds,
        )
        if not hasattr(self._sandbox, "_Sandbox__vnc_server"):
            try:
                from e2b_desktop.main import _VNCServer
                self._sandbox._Sandbox__vnc_server = _VNCServer(self._sandbox)
                if not hasattr(self._sandbox, "_display"):
                    self._sandbox._display = ":0"
            except Exception as exc:
                logger.warning("Could not initialize _VNCServer on resumed sandbox: %s", exc)
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

    def run_command(self, command: str, timeout: int = 30, background: bool = False, cwd: str | None = None) -> dict:
        """Run a shell command. Returns {stdout, stderr, exit_code}."""
        self._require_sandbox()
        try:
            kwargs = {"timeout": timeout}
            if cwd and str(cwd).strip() and cwd != "~":
                kwargs["cwd"] = cwd
            if background:
                # Launch in background using nohup so it doesn't block
                bg_cmd = f"nohup {command} > /dev/null 2>&1 & echo $!"
                result = self._sandbox.commands.run(bg_cmd, **kwargs)
                pid = (result.stdout or "").strip()
                return {
                    "stdout": f"Started in background (PID: {pid})" if pid else "Started in background",
                    "stderr": result.stderr or "",
                    "exit_code": 0,
                }
            result = self._sandbox.commands.run(command, **kwargs)
            return {
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
                "exit_code": result.exit_code,
            }
        except SandboxDeadError:
            raise
        except Exception as e:
            self._raise_if_dead(e)
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
