"""Phase D: flagged live answer streaming (partials are display-only)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from nexus.config import settings
from nexus.output_normalization import sanitize_stream_delta


def _part(text=None, *, thought=False, function_call=None, function_response=None):
    return SimpleNamespace(text=text, thought=thought, function_call=function_call, function_response=function_response)


class _Event:
    def __init__(self, parts, *, final=False, partial=False):
        self.content = SimpleNamespace(parts=parts)
        self.partial = partial
        self._final = final

    def is_final_response(self):
        return self._final


def test_stream_answer_deltas_is_off_by_default():
    assert settings.stream_answer_deltas is False


def test_delta_sanitizer_keeps_boundary_spaces():
    assert sanitize_stream_delta(" world") == " world"
    assert "[object Object]" not in sanitize_stream_delta("a [object Object] b")


def test_partials_are_display_only_and_usage_counts_once():
    from nexus.agent import run_agent_turn

    seen_run_config = []
    usage_calls = []

    class Runner:
        async def run_async(self, *, user_id, session_id, new_message, **kwargs):
            seen_run_config.append(kwargs.get("run_config"))
            yield _Event([_part("Hel")], partial=True)
            yield _Event([_part("lo")], partial=True)
            yield _Event([_part("Hello")], final=True)

    callback_events = []

    async def _callback(event):
        callback_events.append(event)

    def _usage(event, **_kwargs):
        usage_calls.append(event)
        return []

    async def _run():
        with patch("nexus.agent.get_agent_usage_source", return_value=("agent", "m")), \
             patch("nexus.agent.extract_token_usage_records", side_effect=_usage), \
             patch.object(settings, "stream_answer_deltas", True):
            return await run_agent_turn(
                runner=Runner(),
                session_service=SimpleNamespace(get_session=AsyncMock(return_value=object()), create_session=AsyncMock()),
                session_id="s",
                user_id="u",
                message="hi",
                runtime_config=SimpleNamespace(),
                event_callback=_callback,
                max_turns=5,
            )

    result = asyncio.run(_run())
    assert result.response == "Hello"
    assert len(callback_events) == 3  # UI sees every chunk
    assert len(usage_calls) == 1  # usage read from the aggregated event only
    from google.adk.agents.run_config import StreamingMode

    assert seen_run_config[0].streaming_mode == StreamingMode.SSE


@pytest.mark.asyncio
async def test_orchestrator_streams_partials_then_does_not_repeat_text():
    from test_turn_liveness import _orchestrator

    orch, sent = _orchestrator()
    orch._streaming_active = False
    orch._partial_stream_seen = False
    orch._outstanding_task = ""
    orch._html_dump_buffer = ""
    orch._current_run_id = "run_1"
    orch._is_final_response = lambda event: event.is_final_response()  # type: ignore[method-assign]
    orch._extract_function_calls = lambda event: []  # type: ignore[method-assign]

    with patch("nexus.orchestrator.run_progress"):
        await orch._on_agent_event(_Event([_part("Hel")], partial=True))
        await orch._on_agent_event(_Event([_part("lo")], partial=True))
        await orch._on_agent_event(_Event([_part("Hello")], final=True))

    deltas = [e["delta"] for e in sent if e.get("type") == "agent_delta"]
    assert deltas == ["Hel", "lo"]
