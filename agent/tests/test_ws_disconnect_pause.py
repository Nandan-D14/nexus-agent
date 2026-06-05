# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

sys.modules.setdefault(
    "redis",
    SimpleNamespace(Redis=object, from_url=lambda *args, **kwargs: None),
)

from nexus import ws_handler
from nexus.routers import tasks as tasks_router


class FakeWebSocket:
    def __init__(self, messages: list[dict] | None = None) -> None:
        self.accept = AsyncMock()
        self.send_json = AsyncMock()
        self.close = AsyncMock()
        self._messages = messages or [{"type": "websocket.disconnect"}]

    async def receive(self) -> dict:
        await asyncio.sleep(0)
        if not self._messages:
            pytest.fail("handler should stop after websocket.disconnect")
        return self._messages.pop(0)


class FakeOrchestrator:
    active_on_disconnect = False

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.initialize = AsyncMock()
        self.start_desktop = AsyncMock()
        self.close = AsyncMock()
        self.disconnect_marked = False

    async def run_voice_receive_loop(self) -> None:
        await asyncio.Event().wait()

    async def handle_text_input(self, *args, **kwargs) -> None:
        await asyncio.Event().wait()

    def mark_ws_disconnected(self) -> None:
        self.disconnect_marked = True

    def has_active_agent_turn(self) -> bool:
        return self.active_on_disconnect


class InMemoryProductionRepo:
    def __init__(self, *, task_id: str, owner_id: str) -> None:
        self.task_id = task_id
        self.owner_id = owner_id
        self.events: list[SimpleNamespace] = []

    async def append_event(self, **kwargs):
        seq = len(self.events) + 1
        event = SimpleNamespace(
            event_id=f"evt_{seq}",
            task_id=kwargs["task_id"],
            owner_id=kwargs["owner_id"],
            run_id=kwargs.get("run_id"),
            event_type=kwargs["event_type"],
            created_at=datetime.now(timezone.utc),
            payload=kwargs.get("payload") or {},
            seq=seq,
        )
        self.events.append(event)
        return event

    async def get_task(self, task_id: str):
        if task_id != self.task_id:
            return None
        return SimpleNamespace(task_id=self.task_id, owner_id=self.owner_id)

    async def list_events(
        self,
        *,
        task_id: str,
        owner_id: str,
        after_event_id=None,
        after_seq=None,
        run_id=None,
        limit=100,
    ):
        if task_id != self.task_id or owner_id != self.owner_id:
            return []
        min_seq = int(after_seq or 0)
        events = [event for event in self.events if event.seq > min_seq]
        if run_id:
            events = [event for event in events if event.run_id == run_id]
        return events[:limit]


class QueuedProductionRepo:
    def __init__(self) -> None:
        self.task = None
        self.run = None
        self.events: list[SimpleNamespace] = []
        self.create_run_kwargs: dict | None = None

    async def create_task(self, **kwargs):
        self.task = SimpleNamespace(
            task_id="task_ws",
            owner_id=kwargs["owner_id"],
            status="queued",
            title=kwargs["title"],
            input_text=kwargs["input_text"],
            session_id=kwargs.get("session_id"),
        )
        return self.task

    async def get_task(self, task_id: str):
        if self.task and task_id == self.task.task_id:
            return self.task
        return None

    async def create_run(self, **kwargs):
        self.create_run_kwargs = kwargs
        self.run = SimpleNamespace(
            run_id="run_ws",
            task_id=kwargs["task_id"],
            owner_id=kwargs["owner_id"],
            status="queued",
            execution_payload={"input_text": kwargs["input_text"]},
        )
        return self.run

    async def append_event(self, **kwargs):
        seq = len(self.events) + 1
        event = SimpleNamespace(
            event_id=f"evt_ws_{seq}",
            task_id=kwargs["task_id"],
            owner_id=kwargs["owner_id"],
            run_id=kwargs.get("run_id"),
            event_type=kwargs["event_type"],
            created_at=datetime.now(timezone.utc),
            payload=kwargs.get("payload") or {},
            seq=seq,
        )
        self.events.append(event)
        return event

    async def list_events(self, *, task_id: str, owner_id: str, after_seq=None, run_id=None, limit=100, **kwargs):
        min_seq = int(after_seq or 0)
        events = [
            event
            for event in self.events
            if event.task_id == task_id
            and event.owner_id == owner_id
            and event.seq > min_seq
            and (not run_id or event.run_id == run_id)
        ]
        return events[:limit]


class QueuedTaskQueue:
    def __init__(self) -> None:
        self.enqueue_kwargs: dict | None = None

    async def enqueue_task_run(self, **kwargs):
        self.enqueue_kwargs = kwargs
        return SimpleNamespace(queued=True, provider="test", name="queued", reason="")


@pytest.mark.asyncio
async def test_idle_disconnect_schedules_sandbox_pause(monkeypatch) -> None:
    FakeOrchestrator.active_on_disconnect = False
    session = SimpleNamespace(id="session-123", owner_id="firebase-uid")
    session_manager = SimpleNamespace(
        history_repository=None,
        activate_session=AsyncMock(),
        destroy_session=AsyncMock(),
        cancel_idle_pause=Mock(),
        schedule_idle_pause=Mock(),
    )

    monkeypatch.setattr(ws_handler, "NexusOrchestrator", FakeOrchestrator)

    await ws_handler.handle_websocket(FakeWebSocket(), session, session_manager)

    session_manager.activate_session.assert_not_awaited()
    session_manager.cancel_idle_pause.assert_called_once_with("session-123")
    session_manager.schedule_idle_pause.assert_called_once_with("session-123")
    session_manager.destroy_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_disconnect_does_not_pause_sandbox(monkeypatch) -> None:
    FakeOrchestrator.active_on_disconnect = True
    session = SimpleNamespace(id="session-123", owner_id="firebase-uid")
    session_manager = SimpleNamespace(
        history_repository=None,
        activate_session=AsyncMock(),
        destroy_session=AsyncMock(),
        cancel_idle_pause=Mock(),
        schedule_idle_pause=Mock(),
    )

    monkeypatch.setattr(ws_handler, "NexusOrchestrator", FakeOrchestrator)

    await ws_handler.handle_websocket(FakeWebSocket(), session, session_manager)

    session_manager.activate_session.assert_not_awaited()
    session_manager.destroy_session.assert_not_awaited()
    session_manager.schedule_idle_pause.assert_not_called()


@pytest.mark.asyncio
async def test_start_desktop_command_starts_orchestrator_desktop(monkeypatch) -> None:
    FakeOrchestrator.active_on_disconnect = False
    session = SimpleNamespace(id="session-123", owner_id="firebase-uid")
    session_manager = SimpleNamespace(
        history_repository=None,
        activate_session=AsyncMock(),
        destroy_session=AsyncMock(),
        cancel_idle_pause=Mock(),
        schedule_idle_pause=Mock(),
    )
    ws = FakeWebSocket(
        [
            {"text": json.dumps({"type": "start_desktop"})},
            {"type": "websocket.disconnect"},
        ]
    )
    created: list[FakeOrchestrator] = []

    class CapturingOrchestrator(FakeOrchestrator):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            created.append(self)

    monkeypatch.setattr(ws_handler, "NexusOrchestrator", CapturingOrchestrator)

    await ws_handler.handle_websocket(ws, session, session_manager)

    created[0].start_desktop.assert_awaited_once()


@pytest.mark.asyncio
async def test_disconnect_during_background_turn_does_not_pause_sandbox(monkeypatch) -> None:
    FakeOrchestrator.active_on_disconnect = False
    session = SimpleNamespace(id="session-123", owner_id="firebase-uid")
    session_manager = SimpleNamespace(
        history_repository=None,
        activate_session=AsyncMock(),
        destroy_session=AsyncMock(),
        cancel_idle_pause=Mock(),
        schedule_idle_pause=Mock(),
    )
    ws = FakeWebSocket(
        [
            {"text": json.dumps({"type": "text_input", "text": "work"})},
            {"type": "websocket.disconnect"},
        ]
    )

    monkeypatch.setattr(ws_handler, "NexusOrchestrator", FakeOrchestrator)

    await ws_handler.handle_websocket(ws, session, session_manager)

    session_manager.destroy_session.assert_not_awaited()
    session_manager.schedule_idle_pause.assert_not_called()


@pytest.mark.asyncio
async def test_text_input_queues_durable_run_when_worker_available(monkeypatch) -> None:
    repo = QueuedProductionRepo()
    queue = QueuedTaskQueue()
    session = SimpleNamespace(
        id="session-123",
        owner_id="firebase-uid",
        task_id=None,
        current_run_id=None,
        runtime_config=None,
    )
    session_manager = SimpleNamespace(
        history_repository=None,
        activate_session=AsyncMock(),
        destroy_session=AsyncMock(),
        cancel_idle_pause=Mock(),
        schedule_idle_pause=Mock(),
    )
    ws = FakeWebSocket(
        [
            {
                "text": json.dumps(
                    {
                        "type": "text_input",
                        "text": "work",
                        "connector_ids": ["github"],
                        "uploaded_files": [{"name": "a.txt"}],
                    }
                )
            },
            {"type": "websocket.disconnect"},
        ]
    )
    created: list[FakeOrchestrator] = []

    class QueuedFakeOrchestrator(FakeOrchestrator):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self.handle_text_input = AsyncMock()
            self.bind_durable_run = Mock()
            created.append(self)

    monkeypatch.setattr(ws_handler, "NexusOrchestrator", QueuedFakeOrchestrator)
    monkeypatch.setattr(ws_handler, "get_production_task_repository", lambda: repo)
    monkeypatch.setattr(ws_handler, "get_task_queue", lambda: queue)
    monkeypatch.setattr(ws_handler.settings, "task_worker_enabled", True)

    await ws_handler.handle_websocket(ws, session, session_manager)

    assert repo.create_run_kwargs["connector_ids"] == ["github"]
    assert repo.create_run_kwargs["uploaded_files"] == [{"name": "a.txt"}]
    assert repo.create_run_kwargs["metadata"]["user_transcript_recorded"] is True
    assert queue.enqueue_kwargs == {"task_id": "task_ws", "run_id": "run_ws"}
    created[0].bind_durable_run.assert_called_once_with(task_id="task_ws", run_id="run_ws")
    created[0].handle_text_input.assert_not_awaited()
    sent_types = [call.args[0]["type"] for call in ws.send_json.call_args_list]
    assert "run_queued" in sent_types
    assert "transcript" in sent_types
    session_manager.schedule_idle_pause.assert_not_called()


@pytest.mark.asyncio
async def test_disconnect_mid_turn_can_replay_durable_events(monkeypatch) -> None:
    repo = InMemoryProductionRepo(task_id="task_123", owner_id="firebase-uid")
    session = SimpleNamespace(id="session-123", owner_id="firebase-uid", task_id="task_123")
    session_manager = SimpleNamespace(
        history_repository=None,
        activate_session=AsyncMock(),
        destroy_session=AsyncMock(),
        cancel_idle_pause=Mock(),
        schedule_idle_pause=Mock(),
    )
    ws = FakeWebSocket(
        [
            {"text": json.dumps({"type": "text_input", "text": "work"})},
            {"type": "websocket.disconnect"},
        ]
    )

    class DurableFakeOrchestrator(FakeOrchestrator):
        async def handle_text_input(self, *args, **kwargs) -> None:
            await self.kwargs["production_task_repository"].append_event(
                task_id=self.kwargs["session"].task_id,
                owner_id=self.kwargs["session"].owner_id,
                run_id="run_123",
                event_type="agent_thinking",
                payload={"content": "still working"},
            )
            await asyncio.Event().wait()

    monkeypatch.setattr(ws_handler, "NexusOrchestrator", DurableFakeOrchestrator)
    monkeypatch.setattr(ws_handler, "get_production_task_repository", lambda: repo)
    monkeypatch.setattr(tasks_router, "get_production_task_repository", lambda: repo)

    await ws_handler.handle_websocket(ws, session, session_manager)

    replay = await tasks_router.list_durable_task_events(
        task_id="task_123",
        after_event_id=None,
        after_seq=0,
        run_id=None,
        limit=50,
        user=SimpleNamespace(uid="firebase-uid"),
    )

    assert replay["last_seq"] == 1
    assert replay["events"] == [
        {
            "event_id": "evt_1",
            "task_id": "task_123",
            "run_id": "run_123",
            "type": "agent_thinking",
            "created_at": repo.events[0].created_at.isoformat(),
            "payload": {"content": "still working"},
            "seq": 1,
        }
    ]
