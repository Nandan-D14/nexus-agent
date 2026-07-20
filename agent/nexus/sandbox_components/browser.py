# Proprietary and non-commercial use only.

"""Chromium CDP provisioning and URL navigation in the sandbox."""

from __future__ import annotations

import base64
import json
import logging
import shlex
import time
import uuid

from nexus.config import settings
from nexus.sandbox import _coerce_exit_code
from nexus.sandbox_components.base import SandboxComponent

logger = logging.getLogger("nexus.sandbox")


class SandboxBrowser(SandboxComponent):
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

    def _clear_chromium_profile_locks(self, profile_dir: str) -> None:
        """Remove stale singleton lock files that block a fresh Chromium launch.

        A Chromium process that died without cleaning up leaves ``SingletonLock``
        (and friends) in its ``--user-data-dir``, which prevents a new process
        from acquiring the profile so the CDP endpoint never comes up.
        """
        try:
            self._sandbox.commands.run(
                f"rm -f {shlex.quote(profile_dir)}/Singleton*",
                timeout=10,
            )
        except Exception as exc:
            logger.debug(
                "Failed to clear Chromium profile locks in %s: %s", profile_dir, exc
            )

    def _launch_chromium_cdp(self, port: int, profile_dir: str) -> bool:
        """Launch visible Chromium against ``profile_dir`` and wait for CDP.

        Returns ``True`` once Playwright can attach to the endpoint, ``False`` if
        the launch fails or the endpoint never becomes ready.
        """
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
    "--user-data-dir={profile_dir}",
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
        logger.info(
            "Starting Chromium with CDP on port %s (profile=%s)", port, profile_dir
        )
        self._sandbox.write_text_file("/tmp/nexus_chromium_cdp.py", launcher)
        result = self._sandbox.commands.run(
            "python3 /tmp/nexus_chromium_cdp.py",
            timeout=30,
        )
        if _coerce_exit_code(getattr(result, "exit_code", -1)) != 0:
            logger.warning(
                "Chromium CDP launch failed for profile %s: %s",
                profile_dir,
                getattr(result, "stderr", "")
                or getattr(result, "stdout", "")
                or "unknown error",
            )
            return False

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
        return self._wait_for_chromium_cdp(
            port,
            int(settings.browser_startup_timeout_seconds),
        )

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

            default_profile = "/tmp/nexus-chromium-profile"
            self._clear_chromium_profile_locks(default_profile)
            if self._launch_chromium_cdp(port, default_profile):
                return {"status": "ready", "port": port, "reused": False}

            # First launch failed — a stale profile can wedge Chromium. Retry once
            # with a fresh, unique profile directory before giving up.
            fresh_profile = f"/tmp/nexus-chromium-profile-{uuid.uuid4().hex[:8]}"
            logger.warning(
                "Chromium CDP did not become ready with the default profile; "
                "retrying with a fresh profile %s",
                fresh_profile,
            )
            if self._launch_chromium_cdp(port, fresh_profile):
                return {"status": "ready", "port": port, "reused": False}

            log_tail = self._chromium_log_tail()
            detail = f" Chromium log tail: {log_tail}" if log_tail else ""
            raise RuntimeError(
                f"Chromium CDP endpoint on 127.0.0.1:{port} did not become "
                f"ready within {settings.browser_startup_timeout_seconds}s.{detail}"
            )

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
