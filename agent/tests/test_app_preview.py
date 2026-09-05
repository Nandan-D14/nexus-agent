# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Live app preview URL, workspace zip, and text-file open helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.sandbox import SandboxManager
from nexus.sandbox_components.files import (
    SandboxFiles,
    TEXT_PREVIEW_MAX_BYTES,
    is_previewable_text_file,
)
from nexus.tools._context import (
    set_sandbox,
    set_send_json,
    set_workspace_path,
)
from nexus.tools.docs import publish_app_preview


def test_get_preview_url_prefixes_https() -> None:
    manager = SandboxManager()
    inner = MagicMock()
    inner.get_host.return_value = "5173-abc.e2b.app"
    manager._sandbox = inner
    assert manager.get_preview_url(5173) == "https://5173-abc.e2b.app"
    inner.get_host.assert_called_once_with(5173)


def test_get_preview_url_keeps_existing_scheme() -> None:
    manager = SandboxManager()
    inner = MagicMock()
    inner.get_host.return_value = "https://3000-xyz.e2b.app"
    manager._sandbox = inner
    assert manager.get_preview_url(3000) == "https://3000-xyz.e2b.app"


def test_probe_listening_port_uses_in_sandbox_tcp_connect() -> None:
    manager = SandboxManager()
    manager._sandbox = MagicMock()
    manager.run_command = MagicMock(return_value={"exit_code": 0, "stdout": "ok"})  # type: ignore[method-assign]
    assert manager.probe_listening_port(5173) is True
    command = manager.run_command.call_args.args[0]
    assert "127.0.0.1" in command
    assert "5173" in command

    manager.run_command = MagicMock(return_value={"exit_code": 1, "stdout": "fail"})  # type: ignore[method-assign]
    assert manager.probe_listening_port(5173) is False


def test_is_previewable_text_file_open_path() -> None:
    assert is_previewable_text_file("src/App.tsx", 1200) is True
    assert is_previewable_text_file("package.json", 800) is True
    assert is_previewable_text_file(".gitignore", 40) is True
    assert is_previewable_text_file("Dockerfile", 200) is True
    assert is_previewable_text_file("photo.png", 400) is False
    assert is_previewable_text_file("bundle.js", TEXT_PREVIEW_MAX_BYTES + 1) is False


def test_archive_tree_excludes_dependency_dirs() -> None:
    owner = MagicMock()
    owner.run_command.return_value = {"exit_code": 0, "stdout": ""}
    files = SandboxFiles(owner)
    files.read_binary_file = MagicMock(return_value=b"tgz-bytes")  # type: ignore[method-assign]
    payload = files.archive_tree("/home/user/workspace")
    assert payload == b"tgz-bytes"
    command = owner.run_command.call_args.args[0]
    assert "tar -C" in command
    assert "--exclude=node_modules" in command
    assert "--exclude=.git" in command
    files.read_binary_file.assert_called_once_with("/tmp/cocomputer-workspace.tgz")


@pytest.mark.asyncio
async def test_publish_app_preview_emits_ws_payload(monkeypatch) -> None:
    frames: list[dict] = []

    async def capture(payload: dict) -> None:
        frames.append(payload)

    async def fake_ensure():
        return SimpleNamespace()

    monkeypatch.setattr("nexus.tools._context.ensure_sandbox", fake_ensure)

    sandbox = SimpleNamespace(
        is_alive=True,
        probe_listening_port=lambda port: port == 5173,
        get_preview_url=lambda port: f"https://{port}-abc.e2b.app",
        run_command=lambda *a, **k: {"exit_code": 0, "stdout": "", "stderr": ""},
        read_text_file=lambda path: "",
        write_text_file=lambda *a, **k: None,
    )
    send_token = set_send_json(capture)
    sandbox_token = set_sandbox(sandbox)
    workspace_token = set_workspace_path("/home/user/CoComputer/Workspaces/s1/r1")
    try:
        result = await publish_app_preview(5173, title="Vite app")
    finally:
        send_token.var.reset(send_token)
        sandbox_token.var.reset(sandbox_token)
        workspace_token.var.reset(workspace_token)

    assert result["status"] == "success"
    assert result["detail"]["url"] == "https://5173-abc.e2b.app"
    assert result["detail"]["port"] == 5173
    assert len(frames) == 1
    assert frames[0]["type"] == "app_preview"
    assert frames[0]["url"] == "https://5173-abc.e2b.app"
    assert frames[0]["port"] == 5173
    assert frames[0]["title"] == "Vite app"
    assert frames[0]["workspace_path"] == "/home/user/CoComputer/Workspaces/s1/r1"


@pytest.mark.asyncio
async def test_publish_app_preview_rejects_silent_port(monkeypatch) -> None:
    async def fake_ensure():
        return SimpleNamespace()

    monkeypatch.setattr("nexus.tools._context.ensure_sandbox", fake_ensure)
    sandbox = SimpleNamespace(
        is_alive=True,
        probe_listening_port=lambda port: False,
        get_preview_url=lambda port: "https://unused.e2b.app",
    )
    sandbox_token = set_sandbox(sandbox)
    try:
        result = await publish_app_preview(5173)
    finally:
        sandbox_token.var.reset(sandbox_token)

    assert result["status"] == "error"
    assert result["error_code"] == "PORT_NOT_LISTENING"
    assert "0.0.0.0" in result["summary"]


@pytest.mark.asyncio
async def test_publish_app_preview_invalid_port(monkeypatch) -> None:
    async def fake_ensure():
        return SimpleNamespace()

    monkeypatch.setattr("nexus.tools._context.ensure_sandbox", fake_ensure)
    result = await publish_app_preview(0)
    assert result["status"] == "error"
    assert result["error_code"] == "INVALID_INPUT"
