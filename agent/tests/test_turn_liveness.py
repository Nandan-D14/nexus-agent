# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Every agent turn must reach a terminal state the client can observe.

The failure this guards against: the first prompt works, then every later
prompt in the same session is silently dropped and the UI shows a permanent
thinking indicator. Two causes are covered here — a sticky WebSocket-disconnect
latch, and turns that end without emitting a terminal run status.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from starlette.websockets import WebSocketState

from nexus.config import settings
from nexus.orchestrator import NexusOrchestrator, _AgentStopped
from nexus.tracing import TraceContext


def _orchestrator(*, client_state=WebSocketState.CONNECTED):
    """Minimal orchestrator wired only for turn-lifecycle assertions."""
    orch = NexusOrchestrator.__new__(NexusOrchestrator)
    orch.session = SimpleNamespace(
        id="session-1",
        owner_id="user-1",
        run_status="idle",
        task_id=None,
        current_run_id=None,
        sandbox=None,
        sandbox_id=None,
        artifact_count=0,
        initial_title="Test turn",
        resume_source_session_id=None,
        touch=lambda: None,
    )
    orch.ws = SimpleNamespace(
        client_state=client_state,
        application_state=client_state,
    )
    orch.history_repository = None
    orch._current_run_id = None
    orch._event_sink = None
    orch._ws_send_lock = asyncio.Lock()
    orch._ws_connected = True
    orch._stop_requested = False
    orch._turn_lock = asyncio.Lock()
    orch._turn_status_settled = True
    orch._agent_task = None
    orch._trace_context = TraceContext(
        trace_id="trace-1",
        run_id="",
        provider="test",
        model="test-model",
    )
    orch._integration_tools = []
    orch._current_turn_step_id = None
    orch._tool_step_ids = {}
    orch._tool_trace_steps = {}
    orch._pending_tool_calls = {}
    orch._turn_tool_summaries = []
    orch._active_agent = "nexus_orchestrator"
    orch._resume_checkpoint = {}
    orch.last_turn_result = None
    orch._current_thinking = ""
    orch._reasoning_status_emitted = False
    orch._budget_stop_requested = False
    orch._budget_stop_reason = ""
    orch._turn_screenshot_count = 0
    orch._turn_started_monotonic = 0.0
    orch.production_task_repository = None
    orch._durable_task_id = None
    orch._durable_run_id = None

    sent: list[dict] = []

    async def _send_json(payload: dict) -> None:
        sent.append(payload)

    orch._send_json = _send_json  # type: ignore[method-assign]
    return orch, sent


def _statuses(sent: list[dict]) -> list[str]:
    return [
        str(event["run"].get("status"))
        for event in sent
        if event.get("type") == "run_status" and isinstance(event.get("run"), dict)
    ]


@pytest.mark.asyncio
async def test_stale_disconnect_latch_is_rearmed_for_a_new_turn(monkeypatch) -> None:
    """A leftover disconnect flag must not silence the next prompt.

    `_ws_connected` doubles as a cooperative stop latch, so one failed send
    leaves it false for the rest of the connection. As long as the socket is
    really open, a new turn has to run anyway.
    """
    orch, sent = _orchestrator()
    # Simulate a transient send failure during the previous turn.
    orch.mark_ws_disconnected()
    assert orch._ws_connected is False

    ran: list[str] = []

    async def fake_locked(message, **kwargs):
        ran.append(message)
        orch._turn_status_settled = True

    monkeypatch.setattr(orch, "_run_agent_turn_locked", fake_locked)

    await orch._run_agent_tracked("second prompt", source="typed")

    assert ran == ["second prompt"]
    assert orch._ws_connected is True


@pytest.mark.asyncio
async def test_closed_socket_still_settles_the_run() -> None:
    """A genuinely dead socket must not leave the run open forever."""
    orch, sent = _orchestrator(client_state=WebSocketState.DISCONNECTED)
    orch.mark_ws_disconnected()

    await orch._run_agent_tracked("prompt", source="typed")

    assert _statuses(sent) == ["cancelled"]
    assert orch.session.run_status == "cancelled"


@pytest.mark.asyncio
async def test_turns_are_serialized_on_one_session(monkeypatch) -> None:
    """Two prompts must not drive two concurrent ADK runs on one session."""
    orch, _sent = _orchestrator()
    concurrent = 0
    peak = 0
    release = asyncio.Event()

    async def fake_locked(message, **kwargs):
        nonlocal concurrent, peak
        concurrent += 1
        peak = max(peak, concurrent)
        await release.wait()
        concurrent -= 1
        orch._turn_status_settled = True

    monkeypatch.setattr(orch, "_run_agent_turn_locked", fake_locked)

    first = asyncio.create_task(orch._run_agent_tracked("one", source="typed"))
    second = asyncio.create_task(orch._run_agent_tracked("two", source="typed"))
    await asyncio.sleep(0.05)
    release.set()
    await asyncio.gather(first, second)

    assert peak == 1


@pytest.mark.asyncio
async def test_queued_turn_reports_failure_instead_of_waiting_forever(
    monkeypatch,
) -> None:
    """A wedged previous turn must surface an error, not a silent hang."""
    orch, sent = _orchestrator()
    monkeypatch.setattr(settings, "turn_queue_wait_seconds", 0.05)

    await orch._turn_lock.acquire()
    try:
        await orch._run_agent_tracked("blocked prompt", source="typed")
    finally:
        orch._turn_lock.release()

    codes = [event.get("code") for event in sent if event.get("type") == "error"]
    assert "TURN_BUSY" in codes
    assert _statuses(sent)[-1] == "failed"


@pytest.mark.asyncio
async def test_agent_stopped_is_settled_as_cancelled(monkeypatch) -> None:
    """`_AgentStopped` used to escape the turn without a terminal status."""
    orch, sent = _orchestrator()

    async def boom(*_args, **_kwargs):
        raise _AgentStopped()

    monkeypatch.setattr(orch, "_create_step", _async_none)
    monkeypatch.setattr(orch, "_fail_unfinished_tool_steps", _async_none)
    monkeypatch.setattr(orch, "_fail_step", _async_none)
    monkeypatch.setattr(orch, "_bind_workspace_context", lambda: None)
    monkeypatch.setattr(orch, "_run_agent", boom)

    await orch._run_agent_tracked("prompt", source="typed")

    assert _statuses(sent)[-1] == "cancelled"


@pytest.mark.asyncio
async def test_unsettled_turn_is_forced_to_a_terminal_status(monkeypatch) -> None:
    """Any path that forgets to settle the run is caught by the final guard."""
    orch, sent = _orchestrator()

    async def never_settles(*_args, **_kwargs):
        return {"status": "unknown-status", "summary": ""}

    monkeypatch.setattr(orch, "_create_step", _async_none)
    monkeypatch.setattr(orch, "_fail_unfinished_tool_steps", _async_none)
    monkeypatch.setattr(orch, "_fail_step", _async_none)
    monkeypatch.setattr(orch, "_bind_workspace_context", lambda: None)
    monkeypatch.setattr(orch, "_run_agent", never_settles)

    await orch._run_agent_tracked("prompt", source="typed")

    # An unrecognized result status still maps to a terminal "failed".
    assert _statuses(sent)[-1] == "failed"


@pytest.mark.asyncio
async def test_turn_timeout_records_result_and_settles_durable_run(
    monkeypatch,
) -> None:
    """A timed-out turn must fail the durable run so the next prompt is not blocked."""
    orch, sent = _orchestrator()
    monkeypatch.setattr(settings, "agent_turn_timeout_seconds", 0.05)
    finished: list[dict] = []

    class Repo:
        async def finish_run(self, **kwargs):
            finished.append(kwargs)

    orch.production_task_repository = Repo()
    orch._durable_task_id = "task_1"
    orch._durable_run_id = "run_1"

    async def hang(*_args, **_kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(orch, "_create_step", _async_none)
    monkeypatch.setattr(orch, "_fail_unfinished_tool_steps", _async_none)
    monkeypatch.setattr(orch, "_fail_step", _async_none)
    monkeypatch.setattr(orch, "_bind_workspace_context", lambda: None)
    monkeypatch.setattr(orch, "_run_agent", hang)

    await orch._run_agent_tracked("long scrape", source="typed")

    assert orch.last_turn_result is not None
    assert orch.last_turn_result["status"] == "failed"
    assert orch.last_turn_result["verification"]["error_code"] == "TURN_TIMEOUT"
    assert _statuses(sent)[-1] == "failed"
    assert any(event.get("code") == "TURN_TIMEOUT" for event in sent)
    assert finished and finished[0]["status"] == "failed"
    assert finished[0]["task_id"] == "task_1"
    assert finished[0]["run_id"] == "run_1"


@pytest.mark.asyncio
async def test_blocked_waiting_approval_does_not_emit_turn_not_settled(
    monkeypatch,
) -> None:
    orch, sent = _orchestrator()

    async def blocked(*_args, **_kwargs):
        return {
            "status": "blocked",
            "summary": "github_push requires approval",
            "verification": {"error_code": "APPROVAL_REQUIRED"},
        }

    monkeypatch.setattr(orch, "_create_step", _async_none)
    monkeypatch.setattr(orch, "_fail_unfinished_tool_steps", _async_none)
    monkeypatch.setattr(orch, "_fail_step", _async_none)
    monkeypatch.setattr(orch, "_bind_workspace_context", lambda: None)
    monkeypatch.setattr(orch, "_run_agent", blocked)

    await orch._run_agent_tracked("prompt", source="typed")

    codes = [event.get("code") for event in sent if event.get("type") == "error"]
    assert "TURN_NOT_SETTLED" not in codes
    assert _statuses(sent)[-1] == "waiting_approval"


async def _async_none(*_args, **_kwargs):
    return None
