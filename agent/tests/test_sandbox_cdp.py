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
