# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Tests for the orchestrator event sink fan-out."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

import nexus.orchestrator as orchestrator_module
from nexus.event_sink import (
    CompositeEventSink,
    DurableEventSink,
    EPHEMERAL_EVENT_TYPES,
    NullEventSink,
    WebSocketEventSink,
    build_session_event_sink,
)


@pytest.mark.asyncio
async def test_null_sink_drops_silently():
    sink = NullEventSink()
    await sink.send({"type": "anything", "x": 1})  # must not raise


@pytest.mark.asyncio
async def test_websocket_sink_forwards_to_callback():
    sent: list[dict[str, Any]] = []

    async def send_json(event: dict[str, Any]) -> None:
        sent.append(event)

    sink = WebSocketEventSink(send_json)
    await sink.send({"type": "transcript", "text": "hi"})
    assert sent == [{"type": "transcript", "text": "hi"}]


@pytest.mark.asyncio
async def test_websocket_sink_swallows_callback_errors():
    async def failing(event: dict[str, Any]) -> None:
        raise RuntimeError("ws is gone")

    sink = WebSocketEventSink(failing)
    # Must not raise; orchestrator's other sinks should keep working.
    await sink.send({"type": "transcript", "text": "hi"})


class _FakeRepo:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail = False

    async def append_event(self, **kwargs: Any) -> None:
        if self.fail:
            raise RuntimeError("firestore down")
        self.calls.append(kwargs)
        return SimpleNamespace(
            event_id=f"evt_{len(self.calls)}",
            seq=len(self.calls),
        )


@pytest.mark.asyncio
async def test_durable_sink_persists_visible_events():
    repo = _FakeRepo()
    sink = DurableEventSink(
        repo, task_id="task_1", owner_id="user_1", run_id="run_1"
    )
    await sink.send({"type": "agent_tool_call", "tool": "run_command", "args": {"command": "ls"}})
    assert len(repo.calls) == 1
    call = repo.calls[0]
    assert call["task_id"] == "task_1"
    assert call["owner_id"] == "user_1"
    assert call["run_id"] == "run_1"
    assert call["event_type"] == "agent_tool_call"
    assert call["payload"]["tool"] == "run_command"
    assert "type" not in call["payload"]
    assert "seq" not in call["payload"]
    assert "event_id" not in call["payload"]


@pytest.mark.asyncio
async def test_durable_sink_skips_ephemeral_events():
    repo = _FakeRepo()
    sink = DurableEventSink(repo, task_id="task_1", owner_id="user_1")
    for event_type in EPHEMERAL_EVENT_TYPES:
        await sink.send({"type": event_type, "data": "x"})
    assert repo.calls == []


@pytest.mark.asyncio
async def test_durable_sink_is_no_op_without_task_id():
    repo = _FakeRepo()
    sink = DurableEventSink(repo, task_id="", owner_id="user_1")
    assert sink.is_active is False
    await sink.send({"type": "agent_thinking", "content": "..."})
    assert repo.calls == []


@pytest.mark.asyncio
async def test_durable_sink_swallows_repository_errors():
    repo = _FakeRepo()
    repo.fail = True
    sink = DurableEventSink(repo, task_id="task_1", owner_id="user_1")
    # Must not raise so the WS sink can still deliver.
    await sink.send({"type": "transcript", "text": "hi"})


@pytest.mark.asyncio
async def test_durable_sink_update_run_id_changes_run_binding():
    repo = _FakeRepo()
    sink = DurableEventSink(repo, task_id="task_1", owner_id="user_1", run_id="run_1")
    await sink.send({"type": "agent_thinking", "content": "first"})
    sink.update_run_id("run_2")
    await sink.send({"type": "agent_thinking", "content": "second"})
    assert repo.calls[0]["run_id"] == "run_1"
    assert repo.calls[1]["run_id"] == "run_2"


@pytest.mark.asyncio
async def test_composite_sink_fans_out_in_order():
    log: list[tuple[str, str]] = []

    class _NamedSink:
        def __init__(self, name: str) -> None:
            self.name = name

        async def send(self, event: dict[str, Any]) -> None:
            log.append((self.name, str(event.get("type"))))

    composite = CompositeEventSink([_NamedSink("ws"), _NamedSink("durable")])
    await composite.send({"type": "agent_tool_call"})
    assert log == [("ws", "agent_tool_call"), ("durable", "agent_tool_call")]


@pytest.mark.asyncio
async def test_composite_sink_isolates_failures():
    delivered: list[str] = []

    class _Boom:
        async def send(self, event: dict[str, Any]) -> None:
            raise RuntimeError("boom")

    class _Good:
        async def send(self, event: dict[str, Any]) -> None:
            delivered.append(str(event.get("type")))

    composite = CompositeEventSink([_Boom(), _Good()])
    await composite.send({"type": "transcript"})
    # Even though the first sink raised, the second still received the event.
    assert delivered == ["transcript"]


@pytest.mark.asyncio
async def test_composite_sink_propagates_cancellation():
    class _Cancel:
        async def send(self, event: dict[str, Any]) -> None:
            raise asyncio.CancelledError()

    composite = CompositeEventSink([_Cancel()])
    with pytest.raises(asyncio.CancelledError):
        await composite.send({"type": "transcript"})


@pytest.mark.asyncio
async def test_build_session_event_sink_includes_both_when_configured():
    repo = _FakeRepo()
    sent: list[dict[str, Any]] = []

    async def send_json(event: dict[str, Any]) -> None:
        sent.append(event)

    composite = build_session_event_sink(
        repository=repo,
        send_json=send_json,
        task_id="task_1",
        owner_id="user_1",
        run_id="run_1",
    )
    assert len(composite.sinks) == 2
    await composite.send({"type": "agent_tool_call", "tool": "ls"})
    assert sent and sent[0]["type"] == "agent_tool_call"
    assert sent[0]["task_id"] == "task_1"
    assert sent[0]["run_id"] == "run_1"
    assert sent[0]["seq"] == 1
    assert sent[0]["event_id"] == "evt_1"
    assert repo.calls and repo.calls[0]["event_type"] == "agent_tool_call"


@pytest.mark.asyncio
async def test_build_session_event_sink_handles_missing_pieces():
    # No durable side: empty task id
    sent: list[dict[str, Any]] = []

    async def send_json(event: dict[str, Any]) -> None:
        sent.append(event)

    composite = build_session_event_sink(
        repository=None,
        send_json=send_json,
        task_id="",
        owner_id="",
    )
    assert len(composite.sinks) == 1
    await composite.send({"type": "transcript", "text": "ok"})
    assert sent == [{"type": "transcript", "text": "ok"}]


@pytest.mark.asyncio
async def test_orchestrator_event_sink_binds_durable_task(monkeypatch):
    monkeypatch.setattr(orchestrator_module, "create_agent", lambda runtime_config: object())
    monkeypatch.setattr(orchestrator_module, "create_multi_agent", lambda runtime_config: object())
    monkeypatch.setattr(orchestrator_module, "create_runner", lambda agent: (object(), object()))

    repo = _FakeRepo()
    ws = SimpleNamespace(send_json=AsyncMock())
    session = SimpleNamespace(
        id="session_1",
        owner_id="user_1",
        runtime_config=SimpleNamespace(gemini_available=False),
        task_id="task_1",
        current_run_id="run_1",
        stream_url="",
        seed_context="",
    )

    orchestrator = orchestrator_module.NexusOrchestrator(
        session=session,
        ws=ws,
        production_task_repository=repo,
    )

    await orchestrator._send_json({"type": "agent_thinking", "content": "working"})

    assert repo.calls[0]["task_id"] == "task_1"
    assert repo.calls[0]["run_id"] == "run_1"
    ws.send_json.assert_awaited_once()
    live_event = ws.send_json.await_args.args[0]
    assert live_event["task_id"] == "task_1"
    assert live_event["run_id"] == "run_1"
    assert live_event["seq"] == 1


@pytest.mark.asyncio
async def test_orchestrator_event_sink_skips_legacy_session_task_ids(monkeypatch):
    monkeypatch.setattr(orchestrator_module, "create_agent", lambda runtime_config: object())
    monkeypatch.setattr(orchestrator_module, "create_multi_agent", lambda runtime_config: object())
    monkeypatch.setattr(orchestrator_module, "create_runner", lambda agent: (object(), object()))

    repo = _FakeRepo()
    ws = SimpleNamespace(send_json=AsyncMock())
    session = SimpleNamespace(
        id="session_1",
        owner_id="user_1",
        runtime_config=SimpleNamespace(gemini_available=False),
        task_id="session_1",
        current_run_id="legacy_run_1",
        stream_url="",
        seed_context="",
    )

    orchestrator = orchestrator_module.NexusOrchestrator(
        session=session,
        ws=ws,
        production_task_repository=repo,
    )

    await orchestrator._send_json({"type": "agent_thinking", "content": "working"})

    assert repo.calls == []
    ws.send_json.assert_awaited_once_with({"type": "agent_thinking", "content": "working"})
