# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Sandbox boot wrapping, shell-pane WS events, and command redaction."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.tools.base import normalized_tool
from nexus.tools.bash import run_command
from nexus.tools.sandbox_events import redact_command_text
from nexus.tools._context import (
    set_run_id,
    set_sandbox,
    set_send_json,
    set_session_id,
    set_workspace_path,
)
from nexus.tools.workspace import read_workspace_file, write_workspace_file


@pytest.mark.asyncio
async def test_normalized_tool_needs_sandbox_wraps_sync_fn(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_ensure():
        calls.append("ensure")
        return SimpleNamespace()

    monkeypatch.setattr("nexus.tools._context.ensure_sandbox", fake_ensure)

    @normalized_tool(needs_sandbox=True)
    def ping(value: str) -> dict:
        calls.append(value)
        return {"ok": value}

    assert asyncio.iscoroutinefunction(ping)
    result = await ping("hi")
    assert calls == ["ensure", "hi"]
    assert result["status"] == "success"
    assert result["detail"]["ok"] == "hi"


def test_redact_command_text_strips_inline_keys() -> None:
    visible = redact_command_text("ORCA_KEY=sk-abcdefghijklmnopqrstuvwxyz echo hi")
    assert "sk-" not in visible
    assert "[redacted]" in visible


class _CommandSandbox:
    def run_command(self, command: str, timeout: int = 30, background: bool = False, cwd: str | None = None) -> dict:
        return {"stdout": "models listed\n", "stderr": "", "exit_code": 0}


class _FileSandbox:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}

    def write_text_file(self, path: str, content: str, *, append: bool = False) -> None:
        if append and path in self.files:
            self.files[path] += content
        else:
            self.files[path] = content

    def read_text_file(self, path: str, *, max_chars: int = 0) -> str:
        content = self.files[path]
        return content if max_chars <= 0 else content[:max_chars]

    def path_exists(self, path: str) -> bool:
        return path in self.files

    def ensure_directory(self, path: str) -> None:
        return None


@pytest.mark.asyncio
async def test_run_command_emits_sandbox_terminal_start_and_result() -> None:
    frames: list[dict] = []

    async def capture(payload: dict) -> None:
        frames.append(payload)

    send_token = set_send_json(capture)
    sandbox_token = set_sandbox(_CommandSandbox())
    try:
        result = await run_command("ls /workspace")
    finally:
        send_token.var.reset(send_token)
        sandbox_token.var.reset(sandbox_token)

    assert result["status"] == "success"
    assert [frame["type"] for frame in frames] == ["sandbox_terminal", "sandbox_terminal"]
    assert frames[0]["phase"] == "start"
    assert frames[0]["command"] == "ls /workspace"
    assert frames[1]["phase"] == "result"
    assert frames[1]["exit_code"] == 0
    assert "models listed" in frames[1]["stdout"]


@pytest.mark.asyncio
async def test_run_command_ws_payload_redacts_secrets() -> None:
    frames: list[dict] = []

    async def capture(payload: dict) -> None:
        frames.append(payload)

    send_token = set_send_json(capture)
    sandbox_token = set_sandbox(_CommandSandbox())
    try:
        await run_command("ORCA_KEY=sk-abcdefghijklmnopqrstuvwxyz echo hi")
    finally:
        send_token.var.reset(send_token)
        sandbox_token.var.reset(sandbox_token)

    command = frames[0]["command"]
    assert "sk-" not in command
    assert "[redacted]" in command


@pytest.mark.asyncio
async def test_write_workspace_file_emits_sandbox_editor_events() -> None:
    frames: list[dict] = []

    async def capture(payload: dict) -> None:
        frames.append(payload)

    sandbox = _FileSandbox()
    send_token = set_send_json(capture)
    session_token = set_session_id("session-ws")
    run_token = set_run_id("run-ws")
    workspace_token = set_workspace_path("/home/user/CoComputer/Workspaces/session-ws/run-ws")
    sandbox_token = set_sandbox(sandbox)
    try:
        with patch(
            "nexus.tools.workspace.upload_artifact_async",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await write_workspace_file("notes.md", "hello editor")
    finally:
        for token in (sandbox_token, workspace_token, run_token, session_token, send_token):
            token.var.reset(token)

    assert result["status"] == "success"
    assert [frame["type"] for frame in frames] == ["sandbox_editor", "sandbox_editor"]
    assert frames[0]["phase"] == "start"
    assert frames[0]["action"] == "write"
    assert frames[0]["path"] == "notes.md"
    assert frames[0]["content"] == "hello editor"
    assert frames[1]["phase"] == "result"
    assert frames[1]["bytes_written"] == len("hello editor")
    assert "content" not in frames[1]


@pytest.mark.asyncio
async def test_read_workspace_file_emits_sandbox_editor_content_on_result() -> None:
    frames: list[dict] = []

    async def capture(payload: dict) -> None:
        frames.append(payload)

    sandbox = _FileSandbox()
    sandbox.files["/home/user/CoComputer/Workspaces/session-ws/run-ws/notes.md"] = "stored body"
    send_token = set_send_json(capture)
    session_token = set_session_id("session-ws")
    run_token = set_run_id("run-ws")
    workspace_token = set_workspace_path("/home/user/CoComputer/Workspaces/session-ws/run-ws")
    sandbox_token = set_sandbox(sandbox)
    try:
        result = await read_workspace_file("notes.md")
    finally:
        for token in (sandbox_token, workspace_token, run_token, session_token, send_token):
            token.var.reset(token)

    assert result["status"] == "success"
    assert frames[0]["phase"] == "start"
    assert frames[0]["action"] == "read"
    assert "content" not in frames[0]
    assert frames[1]["phase"] == "result"
    assert frames[1]["content"] == "stored body"


VITE_CONFIG_WITHOUT_HOSTS = """\
import { defineConfig } from 'vite'
export default defineConfig({
  plugins: [],
})
"""


@pytest.mark.asyncio
async def test_write_workspace_file_injects_vite_allowed_hosts() -> None:
    frames: list[dict] = []

    async def capture(payload: dict) -> None:
        frames.append(payload)

    sandbox = _FileSandbox()
    send_token = set_send_json(capture)
    session_token = set_session_id("session-ws")
    run_token = set_run_id("run-ws")
    workspace_token = set_workspace_path("/home/user/CoComputer/Workspaces/session-ws/run-ws")
    sandbox_token = set_sandbox(sandbox)
    try:
        with patch(
            "nexus.tools.workspace.upload_artifact_async",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await write_workspace_file("vite.config.ts", VITE_CONFIG_WITHOUT_HOSTS)
    finally:
        for token in (sandbox_token, workspace_token, run_token, session_token, send_token):
            token.var.reset(token)

    written = sandbox.files["/home/user/CoComputer/Workspaces/session-ws/run-ws/vite.config.ts"]
    assert result["status"] == "success"
    assert "allowedHosts: true" in written
    assert "allowedHosts: true" in frames[0]["content"]


@pytest.mark.asyncio
async def test_run_command_auto_backgrounds_vite_dev(monkeypatch) -> None:
    monkeypatch.setattr("nexus.tools.bash.asyncio.sleep", AsyncMock())
    calls: list[dict] = []

    class _DevSandbox:
        def run_command(self, command: str, timeout: int = 30, background: bool = False, cwd: str | None = None) -> dict:
            calls.append({"command": command, "background": background, "cwd": cwd})
            return {"stdout": "Started in background (PID: 9)", "stderr": "", "exit_code": 0}

        def find_listening_web_ports(self) -> list[int]:
            return []

    send_token = set_send_json(AsyncMock())
    sandbox_token = set_sandbox(_DevSandbox())
    try:
        result = await run_command("npm run dev -- --host 0.0.0.0 --port 5173")
    finally:
        send_token.var.reset(send_token)
        sandbox_token.var.reset(sandbox_token)

    assert result["status"] == "success"
    assert "auto-backgrounded" in result["summary"]
    assert any(
        call["background"] is True and "npm run dev" in call["command"] for call in calls
    )
