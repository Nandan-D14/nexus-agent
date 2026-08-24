from __future__ import annotations

import logging
from types import SimpleNamespace

from nexus.config import settings
from nexus.sandbox import SandboxManager


class _Commands:
    def __init__(self, readiness: list[bool]) -> None:
        self._readiness = iter(readiness)
        self.calls: list[str] = []

    def run(self, command: str, timeout: int):
        self.calls.append(command)
        if "curl -fsS" in command:
            return SimpleNamespace(
                exit_code=0,
                stdout="CDP_READY" if next(self._readiness) else "",
            )
        if command == "python3 -c 'import playwright'":
            return SimpleNamespace(exit_code=0, stdout="")
        if command == "python3 /tmp/nexus_chromium_cdp.py":
            return SimpleNamespace(exit_code=0, stdout='{"pid": 4242, "port": 9222}')
        if "connect_over_cdp" in command:
            return SimpleNamespace(exit_code=0, stdout="CDP_CONNECTED")
        raise AssertionError(f"Unexpected sandbox command: {command}")


class _Sandbox:
    def __init__(self, readiness: list[bool]) -> None:
        self.commands = _Commands(readiness)
        self.files: dict[str, str] = {}

    def write_text_file(self, path: str, content: str) -> None:
        self.files[path] = content


def test_chromium_cdp_waits_retries_and_logs_lifecycle(monkeypatch, caplog) -> None:
    monkeypatch.setattr(settings, "browser_startup_timeout_seconds", 3)
    monkeypatch.setattr(settings, "browser_startup_retry_initial_seconds", 0.01)
    monkeypatch.setattr(settings, "browser_startup_retry_max_seconds", 0.02)
    sleeps: list[float] = []
    monkeypatch.setattr("nexus.sandbox.time.sleep", sleeps.append)

    manager = SandboxManager()
    sandbox = _Sandbox([False, False, True])
    manager._sandbox = sandbox

    with caplog.at_level(logging.INFO, logger="nexus.sandbox"):
        result = manager.ensure_chromium_cdp()

    assert result == {"status": "ready", "port": 9222, "reused": False}
    launcher = sandbox.files["/tmp/nexus_chromium_cdp.py"]
    assert "--remote-debugging-port=9222" in launcher
    assert sleeps
    messages = [record.getMessage() for record in caplog.records]
    assert any("Chromium process started" in message for message in messages)
    assert any("CDP port 9222 reachable" in message for message in messages)
    assert any("CDP connected on port 9222" in message for message in messages)


def test_chromium_cdp_reuses_verified_endpoint(monkeypatch, caplog) -> None:
    manager = SandboxManager()
    sandbox = _Sandbox([True])
    manager._sandbox = sandbox

    with caplog.at_level(logging.INFO, logger="nexus.sandbox"):
        result = manager.ensure_chromium_cdp()

    assert result == {"status": "ready", "port": 9222, "reused": True}
    assert "/tmp/nexus_chromium_cdp.py" not in sandbox.files
    assert any("reusing browser" in record.getMessage() for record in caplog.records)


class _RetryCommands:
    """Simulates a stale profile: the first launch fails, the retry succeeds."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.rm_commands: list[str] = []
        self.launch_attempts = 0

    def run(self, command: str, timeout: int):
        self.calls.append(command)
        if command.startswith("rm -f"):
            self.rm_commands.append(command)
            return SimpleNamespace(exit_code=0, stdout="")
        if command == "python3 -c 'import playwright'":
            return SimpleNamespace(exit_code=0, stdout="")
        if "curl -fsS" in command:
            # Only reachable once the fresh-profile launch has run.
            reachable = self.launch_attempts >= 2
            return SimpleNamespace(
                exit_code=0,
                stdout="CDP_READY" if reachable else "",
            )
        if command == "python3 /tmp/nexus_chromium_cdp.py":
            self.launch_attempts += 1
            if self.launch_attempts == 1:
                return SimpleNamespace(
                    exit_code=1, stdout="", stderr="profile locked"
                )
            return SimpleNamespace(
                exit_code=0, stdout='{"pid": 4242, "port": 9222}'
            )
        if "connect_over_cdp" in command:
            return SimpleNamespace(exit_code=0, stdout="CDP_CONNECTED")
        raise AssertionError(f"Unexpected sandbox command: {command}")


class _RetrySandbox:
    def __init__(self) -> None:
        self.commands = _RetryCommands()
        self.files: dict[str, str] = {}
        self.launcher_history: list[str] = []

    def write_text_file(self, path: str, content: str) -> None:
        self.files[path] = content
        if path == "/tmp/nexus_chromium_cdp.py":
            self.launcher_history.append(content)


def test_chromium_cdp_clears_lock_and_retries_fresh_profile(monkeypatch, caplog) -> None:
    monkeypatch.setattr(settings, "browser_startup_timeout_seconds", 3)
    monkeypatch.setattr(settings, "browser_startup_retry_initial_seconds", 0.01)
    monkeypatch.setattr(settings, "browser_startup_retry_max_seconds", 0.02)
    monkeypatch.setattr("nexus.sandbox.time.sleep", lambda *_a, **_k: None)

    manager = SandboxManager()
    sandbox = _RetrySandbox()
    manager._sandbox = sandbox

    with caplog.at_level(logging.WARNING, logger="nexus.sandbox"):
        result = manager.ensure_chromium_cdp()

    assert result == {"status": "ready", "port": 9222, "reused": False}
    # Stale singleton locks were cleared before launching.
    assert any(
        "/tmp/nexus-chromium-profile/Singleton*" in cmd
        for cmd in sandbox.commands.rm_commands
    )
    # Two launches: the default profile, then a fresh unique profile.
    assert len(sandbox.launcher_history) == 2
    assert '"--user-data-dir=/tmp/nexus-chromium-profile"' in sandbox.launcher_history[0]
    assert '"--user-data-dir=/tmp/nexus-chromium-profile-' in sandbox.launcher_history[1]
    assert any(
        "retrying with a fresh profile" in record.getMessage()
        for record in caplog.records
    )
