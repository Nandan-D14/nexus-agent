# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

sys.modules.setdefault(
    "redis",
    SimpleNamespace(Redis=object, from_url=lambda *args, **kwargs: None),
)

from nexus import ws_handler


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
