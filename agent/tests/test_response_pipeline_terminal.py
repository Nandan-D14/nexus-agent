"""Phase A (response redesign): finalize/redaction parity and the terminal
lifecycle contract (every run ends with final | error | aborted)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nexus.orchestrator import _AgentStopped
from test_turn_liveness import _async_none, _orchestrator


def _types(sent):
    return [event.get("type") for event in sent]


def _patch_turn_steps(monkeypatch, orch):
    monkeypatch.setattr(orch, "_create_step", _async_none)
    monkeypatch.setattr(orch, "_fail_unfinished_tool_steps", _async_none)
    monkeypatch.setattr(orch, "_fail_step", _async_none)
    monkeypatch.setattr(orch, "_complete_step", _async_none)
    monkeypatch.setattr(orch, "_bind_workspace_context", lambda: None)


@pytest.mark.asyncio
async def test_sent_and_persisted_answer_are_the_same_redacted_string():
    orch, sent = _orchestrator()
    orch._streaming_active = False
    repo = SimpleNamespace(append_message=AsyncMock())
    orch.history_repository = repo
    secret = "ghp_" + "A" * 30

    delivered = await orch._deliver_agent_answer(f"Your token is {secret}")

    final_events = [e for e in sent if e.get("type") == "agent_message_final"]
    assert len(final_events) == 1
    assert secret not in final_events[0]["text"]
    assert final_events[0]["text"] == delivered
    persisted = repo.append_message.await_args.kwargs["text"]
    assert persisted == delivered


@pytest.mark.asyncio
async def test_caveat_rides_on_the_final_message():
    orch, sent = _orchestrator()
    orch._streaming_active = False
    await orch._deliver_agent_answer("Answer.", caveat="Not verified.")
    final = next(e for e in sent if e.get("type") == "agent_message_final")
    assert final["caveat"] == "Not verified."


@pytest.mark.asyncio
async def test_stopped_turn_ends_with_aborted_and_lifecycle_end(monkeypatch):
    orch, sent = _orchestrator()
    _patch_turn_steps(monkeypatch, orch)

    async def boom(*_args, **_kwargs):
        raise _AgentStopped()

    monkeypatch.setattr(orch, "_run_agent", boom)
    await orch._run_agent_tracked("prompt", source="typed")

    types = _types(sent)
    assert "aborted" in types
    lifecycle = [e for e in sent if e.get("type") == "turn_lifecycle"]
    assert [e["phase"] for e in lifecycle] == ["start", "error"]
    assert lifecycle[-1]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_run_without_reply_gets_a_terminal_error(monkeypatch):
    orch, sent = _orchestrator()
    _patch_turn_steps(monkeypatch, orch)

    async def silent(*_args, **_kwargs):
        return {"status": "failed", "summary": "Nothing happened."}

    monkeypatch.setattr(orch, "_run_agent", silent)
    await orch._run_agent_tracked("prompt", source="typed")

    errors = [e for e in sent if e.get("type") == "error"]
    assert any(e.get("code") == "NO_TERMINAL_REPLY" for e in errors)
    assert sent[-1]["type"] == "turn_lifecycle"


@pytest.mark.asyncio
async def test_partial_run_waiting_on_children_gets_no_fake_error(monkeypatch):
    orch, sent = _orchestrator()
    _patch_turn_steps(monkeypatch, orch)

    async def partial(*_args, **_kwargs):
        return {"status": "partial", "summary": "Waiting on subagents."}

    monkeypatch.setattr(orch, "_run_agent", partial)
    await orch._run_agent_tracked("prompt", source="typed")

    assert not any(e.get("code") == "NO_TERMINAL_REPLY" for e in sent)
    assert sent[-1] == {
        "type": "turn_lifecycle",
        "phase": "end",
        "run_id": "",
        "status": "partial",
    }


@pytest.mark.asyncio
async def test_terminal_send_is_tracked_by_send_json():
    from nexus.orchestrator import NexusOrchestrator

    orch = NexusOrchestrator.__new__(NexusOrchestrator)
    orch._terminal_event_sent = False
    messenger = SimpleNamespace(_send_json=AsyncMock())
    orch._messenger = lambda: messenger  # type: ignore[method-assign]
    await orch._send_json({"type": "agent_thinking", "content": "x"})
    assert orch._terminal_event_sent is False
    await orch._send_json({"type": "agent_message_final", "text": "y"})
    assert orch._terminal_event_sent is True
