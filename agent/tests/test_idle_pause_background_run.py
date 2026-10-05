# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

sys.modules.setdefault(
    "redis",
    SimpleNamespace(Redis=object, from_url=lambda *args, **kwargs: None),
)

from nexus.session import SessionManager


def _manager_with(session) -> SessionManager:
    manager = SessionManager.__new__(SessionManager)
    manager._local_sessions = {session.id: session}
    manager._idle_pause_tasks = {}
    manager.pause_idle_sandbox = AsyncMock()
    return manager


def _session(run_status: str):
    return SimpleNamespace(
        id="s1",
        status="active",
        run_status=run_status,
        sandbox=SimpleNamespace(is_alive=True),
        last_active=datetime.now(timezone.utc) - timedelta(hours=1),
    )


@pytest.mark.asyncio
async def test_idle_pause_waits_for_background_run(monkeypatch) -> None:
    """Closing the browser must not pause the VM under a running durable turn."""
    session = _session("running")
    manager = _manager_with(session)
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == 3:
            session.run_status = "completed"

    monkeypatch.setattr("nexus.session.asyncio.sleep", fake_sleep)
    await manager._idle_pause_after_delay("s1", 0)

    assert len(sleeps) == 3  # initial delay + two waits while the run was busy
    manager.pause_idle_sandbox.assert_awaited_once_with("s1")


@pytest.mark.asyncio
async def test_idle_pause_wait_is_bounded_for_stale_status(monkeypatch) -> None:
    session = _session("running")  # never settles (crashed run)
    manager = _manager_with(session)
    monkeypatch.setattr("nexus.session.settings.agent_turn_timeout_seconds", 60)

    async def fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr("nexus.session.asyncio.sleep", fake_sleep)
    await manager._idle_pause_after_delay("s1", 0)

    manager.pause_idle_sandbox.assert_awaited_once_with("s1")
