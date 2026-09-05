# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import asyncio
import contextlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.runtime_config import SessionRuntimeConfig
from nexus.subagent_resources import ToolResourceLocks
from nexus.subagents import SubagentSupervisor


def _runtime_config() -> SessionRuntimeConfig:
    return SessionRuntimeConfig(
        e2b_api_key="test-e2b",
        gemini_provider="apiKey",
        gemini_api_key="test-gemini",
        google_project_id="",
        google_cloud_region="global",
        gemini_agent_model="gemini-test",
        gemini_agent_fallback_models=(),
        gemini_light_model="gemini-light-test",
        gemini_live_model="gemini-live-test",
        gemini_live_region="us-central1",
        gemini_vision_model="gemini-vision-test",
        gemini_vision_fallback_models=("gemini-vision-fallback",),
        use_kilo=False,
        kilo_api_key="",
        kilo_model_id="",
        kilo_gateway_url="",
    )


def _turn_result(text: str):
    return SimpleNamespace(response=text, usage_records=[], error=None)


class FakeHistoryRepository:
    def __init__(self) -> None:
        self.steps: dict[str, SimpleNamespace] = {}
        self.created: list[SimpleNamespace] = []
        self.completed: list[SimpleNamespace] = []
        self.failed: list[SimpleNamespace] = []
        self._counter = 0

    async def create_step(self, **kwargs):
        self._counter += 1
        now = datetime.now(timezone.utc)
        step = SimpleNamespace(
            step_id=f"step-{self._counter}",
            run_id=kwargs["run_id"],
            session_id=kwargs["session_id"],
            task_id=kwargs["session_id"],
            step_type=kwargs["step_type"],
            status=kwargs.get("status", "running"),
            title=kwargs.get("title", ""),
            detail=kwargs.get("detail", ""),
            created_at=now,
            updated_at=now,
            completed_at=None,
            step_index=self._counter,
            source=kwargs.get("source"),
            error=None,
            external_ref=kwargs.get("external_ref"),
            metadata=kwargs.get("metadata") or {},
        )
        self.steps[step.step_id] = step
        self.created.append(step)
        return step

    async def complete_step(self, *, step_id: str, detail: str | None = None, metadata=None, **_kwargs):
        step = self.steps[step_id]
        step.status = "completed"
        if detail is not None:
            step.detail = detail
        step.metadata = {**(step.metadata or {}), **(metadata or {})}
        step.completed_at = datetime.now(timezone.utc)
        step.updated_at = step.completed_at
        self.completed.append(step)
        return step

    async def fail_step(
        self,
        *,
        step_id: str,
        detail: str | None = None,
        error: str | None = None,
        metadata=None,
        status: str = "failed",
        **_kwargs,
    ):
        step = self.steps[step_id]
        step.status = status
        if detail is not None:
            step.detail = detail
        step.error = error
        step.metadata = {**(step.metadata or {}), **(metadata or {})}
        step.completed_at = datetime.now(timezone.utc)
        step.updated_at = step.completed_at
        self.failed.append(step)
        return step


def _supervisor(history=None, send_json=None) -> SubagentSupervisor:
    return SubagentSupervisor(
        runtime_config=_runtime_config(),
        session_service=object(),
        owner_id="user-1",
        parent_session_id="parent-session",
        parent_run_id="run-1",
        history_repository=history,
        send_json=send_json,
    )


class SubagentSupervisorTests(IsolatedAsyncioTestCase):
    async def test_spawn_returns_before_background_turn_finishes(self) -> None:
        release = asyncio.Event()
        started = asyncio.Event()
        supervisor = _supervisor()

        async def blocked_turn(_record, _message):
            started.set()
            await release.wait()
            return _turn_result("done")

        supervisor._run_turn = AsyncMock(side_effect=blocked_turn)  # type: ignore[method-assign]

        record = await supervisor.spawn(prompt="work", role="researcher", type_name="research")

        await asyncio.wait_for(started.wait(), timeout=0.5)
        self.assertEqual(record.status, "running")
        self.assertFalse(record.task.done())
        release.set()
        await asyncio.wait_for(record.task, timeout=0.5)
        self.assertEqual(record.status, "completed")
        self.assertEqual(record.result, "done")

    async def test_send_message_restarts_completed_subagent_mailbox(self) -> None:
        supervisor = _supervisor()
        supervisor._run_turn = AsyncMock(  # type: ignore[method-assign]
            side_effect=[_turn_result("first"), _turn_result("second")]
        )

        record = await supervisor.spawn(prompt="first prompt", role="coder", type_name="code")
        await asyncio.wait_for(record.task, timeout=0.5)

        await supervisor.send_message(record.subagent_id, "second prompt")
        await asyncio.wait_for(record.task, timeout=0.5)

        self.assertEqual(supervisor._run_turn.await_count, 2)
        self.assertEqual(record.result, "second")

    async def test_completion_creates_parent_steps_and_live_step_events(self) -> None:
        history = FakeHistoryRepository()
        events: list[dict] = []
        supervisor = _supervisor(history=history, send_json=lambda payload: _append_event(events, payload))
        supervisor._run_turn = AsyncMock(return_value=_turn_result("final answer"))  # type: ignore[method-assign]

        record = await supervisor.spawn(prompt="do work", role="writer", type_name="writer")
        await asyncio.wait_for(record.task, timeout=0.5)

        self.assertEqual(history.created[0].step_type, "subagent_started")
        self.assertEqual(history.completed[0].step_id, record.step_id)
        self.assertEqual(history.completed[0].detail, "final answer")
        self.assertIn("step_started", [event["type"] for event in events])
        self.assertIn("step_completed", [event["type"] for event in events])
        self.assertIn("subagent_completed", [event["type"] for event in events])

    async def test_cancel_stops_task_and_marks_step_cancelled(self) -> None:
        history = FakeHistoryRepository()
        release = asyncio.Event()
        supervisor = _supervisor(history=history)

        async def blocked_turn(_record, _message):
            await release.wait()
            return _turn_result("late")

        supervisor._run_turn = AsyncMock(side_effect=blocked_turn)  # type: ignore[method-assign]

        record = await supervisor.spawn(prompt="long work", role="worker", type_name="general")
        await supervisor.cancel(record.subagent_id)
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.wait_for(record.task, timeout=0.5)

        self.assertEqual(record.status, "cancelled")
        self.assertEqual(history.failed[-1].status, "cancelled")
        self.assertTrue(record.task.done())

    async def test_resource_locks_serialize_workspace_mutation_tools(self) -> None:
        locks = ToolResourceLocks()
        order: list[str] = []

        async def worker(label: str) -> None:
            async with locks.async_lock("write_workspace_file"):
                order.append(f"start-{label}")
                await asyncio.sleep(0.01)
                order.append(f"end-{label}")

        await asyncio.gather(worker("a"), worker("b"))

        self.assertIn(
            order,
            [
                ["start-a", "end-a", "start-b", "end-b"],
                ["start-b", "end-b", "start-a", "end-a"],
            ],
        )

    async def test_read_only_tools_do_not_share_mutation_lock(self) -> None:
        locks = ToolResourceLocks()
        entered = 0
        both_inside = asyncio.Event()

        async def worker() -> None:
            nonlocal entered
            async with locks.async_lock("read_workspace_file"):
                entered += 1
                if entered == 2:
                    both_inside.set()
                await asyncio.wait_for(both_inside.wait(), timeout=0.5)

        await asyncio.gather(worker(), worker())


async def _append_event(events: list[dict], payload: dict) -> None:
    events.append(payload)
