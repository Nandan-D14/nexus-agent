# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""In-session sandbox death detection, reconnect, and idle pause."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.sandbox import (
    SANDBOX_RESTART_MESSAGE,
    SandboxDeadError,
    SandboxManager,
    is_dead_sandbox_error,
    is_valid_sandbox_id,
)
from nexus.session import Session, SessionManager
from nexus.tools.base import normalized_tool
from nexus import orchestrator as orchestrator_module


class _StatusError(Exception):
    def __init__(self, message: str, status_code: int = 404) -> None:
        super().__init__(message)
        self.status_code = status_code


def test_is_dead_sandbox_error_detects_404_and_not_command_not_found() -> None:
    assert is_dead_sandbox_error(_StatusError("404 not found"))
    assert is_dead_sandbox_error(Exception("Sandbox not found"))
    assert is_dead_sandbox_error(SandboxDeadError())
    assert not is_dead_sandbox_error(Exception("bash: foo: command not found"))
    assert not is_dead_sandbox_error(Exception("deadline exceeded"))
    assert is_dead_sandbox_error(Exception("deadline exceeded"), include_timeout=True)


def test_extend_timeout_failure_marks_dead() -> None:
    manager = SandboxManager()
    client = MagicMock()
    client.set_timeout.side_effect = Exception("sandbox not found")
    manager._sandbox = client
    manager._stream_url = "http://vnc"

    assert manager.extend_timeout() is False
    assert manager.is_alive is False
    assert manager.stream_url is None


def test_pause_keeps_real_sandbox_id_when_sdk_returns_bool() -> None:
    manager = SandboxManager()
    client = MagicMock()
    client.sandbox_id = "iyu3ebm8aqm5x7mim2hkf"
    client.pause.return_value = True
    manager._sandbox = client
    manager._stream_url = "http://vnc"

    paused = manager.pause()

    assert paused == "iyu3ebm8aqm5x7mim2hkf"
    assert manager.is_alive is False
    assert not is_valid_sandbox_id("True")
    assert not is_valid_sandbox_id(True)


def test_run_command_404_raises_sandbox_dead_error() -> None:
    manager = SandboxManager()
    client = MagicMock()
    client.commands.run.side_effect = _StatusError("404 not found")
    manager._sandbox = client
    manager._stream_url = "http://vnc"

    with pytest.raises(SandboxDeadError, match="restarted in this session"):
        manager.run_command("echo sandbox-ok")

    assert manager.is_alive is False
    assert "Do not start a new session" in SANDBOX_RESTART_MESSAGE


def test_run_command_timeout_does_not_mark_dead() -> None:
    manager = SandboxManager()
    client = MagicMock()
    client.commands.run.side_effect = Exception("deadline exceeded")
    manager._sandbox = client
    manager._stream_url = "http://vnc"

    result = manager.run_command("sleep 99")
    assert result["exit_code"] == -1
    assert manager.is_alive is True


def test_require_sandbox_message_does_not_ask_for_new_session() -> None:
    manager = SandboxManager()
    with pytest.raises(SandboxDeadError) as exc_info:
        manager._require_sandbox()
    assert "new session" in str(exc_info.value).lower()
    assert "Do not start a new session" in str(exc_info.value)


def _session_with_sandbox(sandbox: MagicMock) -> Session:
    return Session(
        id="sess-1",
        owner_id="user-1",
        runtime_config=MagicMock(),
        sandbox=sandbox,
        sandbox_id="old-id",
        stream_url="http://old-vnc",
        status="active",
    )


@pytest.mark.asyncio
async def test_ensure_session_ready_creates_after_stale_probe() -> None:
    sandbox = MagicMock()
    sandbox.is_alive = True
    sandbox.extend_timeout.return_value = False
    sandbox.create.return_value = {"sandbox_id": "new-id", "stream_url": "http://new-vnc"}

    manager = SessionManager()
    session = _session_with_sandbox(sandbox)
    manager._local_sessions[session.id] = session

    ready = await manager.ensure_session_ready(session.id)

    sandbox.create.assert_called_once()
    sandbox.resume.assert_not_called()
    assert ready.sandbox_id == "new-id"
    assert ready.stream_url == "http://new-vnc"


@pytest.mark.asyncio
async def test_ensure_session_ready_skips_invalid_paused_sandbox_id() -> None:
    sandbox = MagicMock()
    sandbox.is_alive = False
    sandbox.create.return_value = {"sandbox_id": "new-id", "stream_url": "http://new-vnc"}

    manager = SessionManager()
    session = _session_with_sandbox(sandbox)
    session.sandbox_id = "True"
    manager._local_sessions[session.id] = session

    ready = await manager.ensure_session_ready(session.id)

    sandbox.resume.assert_not_called()
    sandbox.create.assert_called_once()
    assert ready.sandbox_id == "new-id"


@pytest.mark.asyncio
async def test_idle_pause_keeps_session_and_activate_finds_it() -> None:
    sandbox = MagicMock()
    sandbox.is_alive = True

    def _pause() -> str:
        sandbox.is_alive = False
        return "paused-id"

    sandbox.pause.side_effect = _pause
    sandbox.resume.return_value = {"sandbox_id": "paused-id", "stream_url": "http://resumed"}
    sandbox.extend_timeout.return_value = True

    repo = MagicMock()
    repo.save_paused_sandbox = AsyncMock()
    repo.refresh_session_handoff = AsyncMock()
    repo.upsert_session = AsyncMock()

    manager = SessionManager(history_repository=repo)
    session = _session_with_sandbox(sandbox)
    manager._local_sessions[session.id] = session

    await manager.pause_idle_sandbox(session.id)

    assert manager._local_sessions.get(session.id) is session
    assert session.status == "paused"
    assert session.sandbox_id == "paused-id"
    repo.save_paused_sandbox.assert_awaited()

    sandbox.is_alive = False
    sandbox.stream_url = None
    session.stream_url = ""
    activated = await manager.activate_session(session.id)
    sandbox.resume.assert_called()
    assert activated.status == "active"
    assert manager._local_sessions.get(session.id) is session


@pytest.mark.asyncio
async def test_normalized_tool_retries_once_after_sandbox_dead() -> None:
    calls: list[str] = []

    async def fake_ensure():
        calls.append("ensure")
        return SimpleNamespace()

    @normalized_tool(needs_sandbox=True)
    def ping() -> dict:
        calls.append("run")
        if calls.count("run") == 1:
            raise SandboxDeadError()
        return {"ok": True}

    with patch("nexus.tools._context.ensure_sandbox", fake_ensure):
        result = await ping()

    assert calls == ["ensure", "run", "ensure", "run"]
    assert result["status"] == "success"
    assert result["detail"]["ok"] is True


@pytest.mark.asyncio
async def test_normalized_tool_reconnect_failed_is_retryable() -> None:
    async def fake_ensure():
        return SimpleNamespace()

    @normalized_tool(needs_sandbox=True)
    def ping() -> dict:
        raise SandboxDeadError()

    with patch("nexus.tools._context.ensure_sandbox", fake_ensure):
        result = await ping()

    assert result["status"] == "error"
    assert result["error_code"] == "SANDBOX_RECONNECT_FAILED"
    assert result["retryable"] is True


def _orchestrator(session, ws, **kwargs):
    with (
        patch.object(orchestrator_module, "create_planner_agent", return_value=object()),
        patch.object(orchestrator_module, "create_runner", return_value=(object(), object())),
    ):
        return orchestrator_module.NexusOrchestrator(session=session, ws=ws, **kwargs)


@pytest.mark.asyncio
async def test_ensure_sandbox_ready_reconnects_when_callback_leaves_dead() -> None:
    sandbox = MagicMock()
    sandbox.is_alive = True
    sandbox.extend_timeout.return_value = False
    sandbox.stream_url = None
    sandbox.create.return_value = {"sandbox_id": "new-id", "stream_url": "http://new-vnc"}
    sandbox.ensure_directory = MagicMock()

    session = SimpleNamespace(
        id="session-1",
        owner_id="user-1",
        runtime_config=SimpleNamespace(gemini_available=False),
        sandbox=sandbox,
        sandbox_id="old-id",
        stream_url="http://old-vnc",
        current_run_id="run-1",
        seed_context="",
        task_id="session-1",
    )
    ws = SimpleNamespace(send_json=AsyncMock())
    repo = MagicMock()
    callback = AsyncMock()

    def _leave_dead():
        sandbox.is_alive = False
        session.stream_url = ""

    callback.side_effect = _leave_dead

    orch = _orchestrator(session, ws, ensure_sandbox_ready=callback, history_repository=repo)
    orch._send_json = AsyncMock()
    orch._ensure_session_workspace_root = AsyncMock(return_value=True)
    orch._sync_skills_into_sandbox = AsyncMock()
    orch._bind_workspace_context = MagicMock()

    rehydrate = AsyncMock()
    with patch("nexus.session._rehydrate_workspace_from_gcs", rehydrate):
        ok = await orch._ensure_sandbox_ready("tool_use")

    assert ok is True
    callback.assert_awaited()
    sandbox.create.assert_called_once()
    rehydrate.assert_awaited()
    assert session.stream_url == "http://new-vnc"


@pytest.mark.asyncio
async def test_reconnect_sandbox_invokes_gcs_rehydrate() -> None:
    sandbox = MagicMock()
    sandbox.create.return_value = {"sandbox_id": "new-id", "stream_url": "http://new-vnc"}
    sandbox.ensure_directory = MagicMock()

    session = SimpleNamespace(
        id="session-1",
        owner_id="user-1",
        runtime_config=SimpleNamespace(gemini_available=False),
        sandbox=sandbox,
        sandbox_id="old-id",
        stream_url="",
        current_run_id="run-1",
        seed_context="",
        task_id="session-1",
    )
    ws = SimpleNamespace(send_json=AsyncMock())
    repo = MagicMock()

    orch = _orchestrator(session, ws, history_repository=repo)
    orch._send_json = AsyncMock()
    orch._ensure_session_workspace_root = AsyncMock(return_value=True)
    orch._bind_workspace_context = MagicMock()

    rehydrate = AsyncMock()
    with patch("nexus.session._rehydrate_workspace_from_gcs", rehydrate):
        ok = await orch._reconnect_sandbox()

    assert ok is True
    rehydrate.assert_awaited_once()
    sandbox.create.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_sandbox_callback_keyerror_falls_back_to_reconnect() -> None:
    sandbox = MagicMock()
    sandbox.is_alive = False
    sandbox.stream_url = None
    sandbox.create.return_value = {"sandbox_id": "new-id", "stream_url": "http://new-vnc"}

    session = SimpleNamespace(
        id="session-1",
        owner_id="user-1",
        runtime_config=SimpleNamespace(gemini_available=False),
        sandbox=sandbox,
        sandbox_id="old-id",
        stream_url="",
        current_run_id="run-1",
        seed_context="",
        task_id="session-1",
    )
    ws = SimpleNamespace(send_json=AsyncMock())

    async def missing_session():
        raise KeyError("session-1")

    orch = _orchestrator(session, ws, ensure_sandbox_ready=missing_session)
    orch._send_json = AsyncMock()
    orch._ensure_session_workspace_root = AsyncMock(return_value=True)
    orch._sync_skills_into_sandbox = AsyncMock()
    orch._bind_workspace_context = MagicMock()

    with patch("nexus.session._rehydrate_workspace_from_gcs", AsyncMock()):
        ok = await orch._ensure_sandbox_ready("tool_use")

    assert ok is True
    sandbox.create.assert_called_once()


@pytest.mark.asyncio
async def test_restart_sandbox_republishes_preview(monkeypatch) -> None:
    sandbox = MagicMock()
    sandbox.is_alive = True
    sandbox.probe_listening_port.side_effect = [False, True]
    sandbox.get_preview_url.return_value = "https://8000-new.e2b.app"

    session = SimpleNamespace(
        id="session-1",
        owner_id="user-1",
        runtime_config=SimpleNamespace(gemini_available=False),
        sandbox=sandbox,
        sandbox_id="old-id",
        stream_url="http://old-vnc",
        current_run_id="run-1",
        seed_context="",
        task_id="session-1",
    )
    ws = SimpleNamespace(send_json=AsyncMock())
    orch = _orchestrator(session, ws)
    orch._send_json = AsyncMock()
    orch._ensure_sandbox_ready = AsyncMock(return_value=True)
    orch._bind_workspace_context = MagicMock()
    monkeypatch.setattr(orchestrator_module.asyncio, "sleep", AsyncMock())

    await orch.restart_sandbox(
        port=8000,
        title="Ember & Oak",
        workspace_path="/home/user/CoComputer/Workspaces/session-1/ember-and-oak",
    )

    sandbox.mark_dead.assert_called_once()
    orch._ensure_sandbox_ready.assert_awaited_once_with("preview_restart")
    sandbox.run_command.assert_called()
    payloads = [call.args[0] for call in orch._send_json.await_args_list]
    assert any(item.get("type") == "sandbox_status" and item.get("status") == "restarting" for item in payloads)
    preview = next(item for item in payloads if item.get("type") == "app_preview")
    assert preview["url"] == "https://8000-new.e2b.app"
    assert preview["port"] == 8000
    assert preview["title"] == "Ember & Oak"
