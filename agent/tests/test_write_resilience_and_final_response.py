# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Tests for Firestore write resilience and guaranteed final responses.

Covers the Phase 1 concurrency helpers (per-key serialization + Aborted
backoff retry) and the Phase 2 forced-synthesis / robust-capture behavior in
run_agent_turn.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from google.api_core.exceptions import Aborted

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.config import settings
from nexus.firestore_concurrency import guarded_write, run_with_write_retry
from nexus.agent import run_agent_turn


# ---------------------------------------------------------------------------
# run_with_write_retry
# ---------------------------------------------------------------------------


class RunWithWriteRetryTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        # Keep backoff tiny so tests stay fast.
        self._patchers = [
            patch.object(settings, "firestore_write_max_retries", 3),
            patch.object(settings, "firestore_write_backoff_base_ms", 1),
            patch.object(settings, "firestore_write_backoff_max_ms", 2),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self) -> None:
        for p in self._patchers:
            p.stop()

    def test_retries_then_succeeds(self) -> None:
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            if calls["n"] < 3:
                raise Aborted("cross-transaction contention")
            return 42

        result = run_with_write_retry(fn, description="unit")
        self.assertEqual(result, 42)
        self.assertEqual(calls["n"], 3)

    def test_exhausts_and_raises_aborted(self) -> None:
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            raise Aborted("still contended")

        with self.assertRaises(Aborted):
            run_with_write_retry(fn, description="unit")
        self.assertEqual(calls["n"], 3)

    def test_non_retryable_propagates_immediately(self) -> None:
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            run_with_write_retry(fn, description="unit")
        self.assertEqual(calls["n"], 1)


# ---------------------------------------------------------------------------
# guarded_write
# ---------------------------------------------------------------------------


class GuardedWriteTests(IsolatedAsyncioTestCase):
    async def test_same_key_serializes(self) -> None:
        order: list[str] = []

        async def worker(n: int) -> None:
            async with guarded_write("session-A"):
                order.append(f"start{n}")
                await asyncio.sleep(0.01)
                order.append(f"end{n}")

        with patch.object(settings, "serialize_session_writes", True):
            await asyncio.gather(worker(1), worker(2))

        # Each start must be immediately followed by its own end (no interleave).
        for i in range(0, len(order), 2):
            start = order[i]
            end = order[i + 1]
            self.assertEqual(start.replace("start", ""), end.replace("end", ""))

    async def test_different_keys_run_concurrently(self) -> None:
        started = asyncio.Event()

        async def hold_a() -> None:
            async with guarded_write("A"):
                started.set()
                await asyncio.sleep(0.05)

        async def run_b() -> bool:
            await started.wait()
            async with guarded_write("B"):
                return True

        with patch.object(settings, "serialize_session_writes", True):
            _, ok = await asyncio.gather(hold_a(), run_b())
        self.assertTrue(ok)


# ---------------------------------------------------------------------------
# run_agent_turn forced synthesis + robust capture
# ---------------------------------------------------------------------------


def _part(function_call=None, function_response=None, text=None):
    return SimpleNamespace(
        function_call=function_call,
        function_response=function_response,
        text=text,
    )


class _FakeEvent:
    def __init__(self, parts, final):
        self.content = SimpleNamespace(parts=parts)
        self._final = final

    def is_final_response(self) -> bool:
        return self._final


class _FakeRunner:
    """Yields a scripted list of events per run_async call."""

    def __init__(self, scripts):
        self._scripts = scripts
        self.calls = 0

    async def run_async(self, *, user_id, session_id, new_message):
        events = self._scripts[self.calls]
        self.calls += 1
        for event in events:
            yield event


def _fake_session_service():
    return SimpleNamespace(
        get_session=AsyncMock(return_value=object()),
        create_session=AsyncMock(),
    )


class RunAgentTurnTests(IsolatedAsyncioTestCase):
    async def _run(self, runner, **kwargs):
        with patch("nexus.agent.get_agent_usage_source", return_value=("agent", "m")), \
             patch("nexus.agent.extract_token_usage_records", return_value=[]):
            return await run_agent_turn(
                runner=runner,
                session_service=_fake_session_service(),
                session_id="sess-1",
                user_id="user-1",
                message="summarize my emails",
                runtime_config=SimpleNamespace(),
                max_turns=30,
                **kwargs,
            )

    async def test_forced_synthesis_when_tools_ran_without_text(self) -> None:
        scripts = [
            # Main turn: one tool-call round then a final event carrying no text.
            [
                _FakeEvent([_part(function_call=object())], final=False),
                _FakeEvent([_part(function_response=object())], final=True),
            ],
            # Forced synthesis pass: final event with the summary text.
            [_FakeEvent([_part(text="Here is your summary.")], final=True)],
        ]
        runner = _FakeRunner(scripts)
        with patch.object(settings, "force_final_synthesis", True):
            result = await self._run(runner)
        self.assertEqual(result.response, "Here is your summary.")
        self.assertEqual(runner.calls, 2)

    async def test_happy_path_is_unchanged(self) -> None:
        scripts = [[_FakeEvent([_part(text="Direct answer.")], final=True)]]
        runner = _FakeRunner(scripts)
        with patch.object(settings, "force_final_synthesis", True):
            result = await self._run(runner)
        self.assertEqual(result.response, "Direct answer.")
        self.assertEqual(runner.calls, 1)

    async def test_robust_capture_uses_last_text_when_not_flagged_final(self) -> None:
        # Text arrives on a non-final event; final event has no text.
        scripts = [
            [
                _FakeEvent([_part(text="streamed answer")], final=False),
                _FakeEvent([_part(function_response=object())], final=True),
            ]
        ]
        runner = _FakeRunner(scripts)
        with patch.object(settings, "force_final_synthesis", True):
            result = await self._run(runner)
        self.assertEqual(result.response, "streamed answer")
        # Fallback capture avoided the need for a synthesis pass.
        self.assertEqual(runner.calls, 1)

    async def test_worker_envelope_last_text_triggers_synthesis(self) -> None:
        envelope = (
            '{"status":"success","summary":"Generated PDF report.",'
            '"evidence":["File exists"],"artifacts":[{"path":"outputs/a.pdf","kind":"pdf"}],'
            '"sources":[],"remaining_work":[],"retryable":false,"error_code":""}'
        )
        scripts = [
            [
                _FakeEvent([_part(function_call=object())], final=False),
                _FakeEvent([_part(text=envelope)], final=False),
                _FakeEvent([_part(function_response=object())], final=True),
            ],
            [_FakeEvent([_part(text="I generated the PDF report for you.")], final=True)],
        ]
        runner = _FakeRunner(scripts)
        with patch.object(settings, "force_final_synthesis", True):
            result = await self._run(runner)
        self.assertEqual(result.response, "I generated the PDF report for you.")
        self.assertEqual(runner.calls, 2)

    async def test_synthesis_disabled_returns_empty(self) -> None:
        scripts = [
            [
                _FakeEvent([_part(function_call=object())], final=False),
                _FakeEvent([_part(function_response=object())], final=True),
            ]
        ]
        runner = _FakeRunner(scripts)
        with patch.object(settings, "force_final_synthesis", False):
            result = await self._run(runner)
        self.assertIsNone(result.response)
        self.assertEqual(runner.calls, 1)


class _RaisingRunner:
    """Runner whose run_async raises a scripted exception on first iteration."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.calls = 0

    async def run_async(self, *, user_id, session_id, new_message):
        self.calls += 1
        if False:  # pragma: no cover - makes this an async generator
            yield None
        raise self._exc


class RunAgentTurnUnknownToolTests(IsolatedAsyncioTestCase):
    async def _run(self, runner):
        with patch("nexus.agent.get_agent_usage_source", return_value=("agent", "m")), \
             patch("nexus.agent.extract_token_usage_records", return_value=[]):
            return await run_agent_turn(
                runner=runner,
                session_service=_fake_session_service(),
                session_id="sess-1",
                user_id="user-1",
                message="click that button",
                runtime_config=SimpleNamespace(),
                max_turns=30,
            )

    async def test_unknown_tool_valueerror_is_non_fatal(self) -> None:
        # ADK raises a bare ValueError when the model calls an unregistered tool.
        runner = _RaisingRunner(ValueError("Tool 'triple_click' not found"))
        with patch.object(settings, "force_final_synthesis", False):
            result = await self._run(runner)
        # The turn recovers with a note instead of crashing.
        self.assertIsNotNone(result.response)
        self.assertIn("unavailable", result.response.lower())

    async def test_unrelated_valueerror_still_propagates(self) -> None:
        runner = _RaisingRunner(ValueError("totally unrelated failure"))
        with patch.object(settings, "force_final_synthesis", False):
            with self.assertRaises(ValueError):
                await self._run(runner)
