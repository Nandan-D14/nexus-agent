# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Durable runs must always reach a terminal state.

A queued run that produces no events leaves the client waiting forever, which
is indistinguishable from a hung agent. These tests cover the two paths that
previously ended in silence: a rejected claim and a crashed local worker task.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

sys.modules.setdefault(
    "redis",
    SimpleNamespace(Redis=object, from_url=lambda *args, **kwargs: None),
)

from nexus import task_queue as task_queue_module
from nexus import task_worker as task_worker_module
from nexus.production_tasks import DurableTask, DurableTaskRun
from nexus.task_worker import TaskWorker


def _task(**overrides) -> DurableTask:
    now = datetime.now(timezone.utc)
    defaults = dict(
        task_id="task_1",
        owner_id="user_1",
        title="Durable work",
        status="queued",
        created_at=now,
        updated_at=now,
        session_id="session_1",
        current_run_id="run_1",
    )
    defaults.update(overrides)
    return DurableTask(**defaults)


def _run(**overrides) -> DurableTaskRun:
    now = datetime.now(timezone.utc)
    defaults = dict(
        run_id="run_1",
        task_id="task_1",
        owner_id="user_1",
        status="running",
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return DurableTaskRun(**defaults)


class _RecordingRepo:
    def __init__(self, *, task=None, run=None, claim=None):
        self._task = task
        self._run = run
        self._claim = claim
        self.finished: list[dict] = []
        self.events: list[dict] = []

    async def claim_run(self, **kwargs):
        return self._claim

    async def get_task(self, task_id):
        return self._task

    async def get_run(self, *, task_id, run_id, owner_id):
        if self._run is None or self._run.owner_id != owner_id:
            return None
        return self._run

    async def finish_run(self, **kwargs):
        self.finished.append(kwargs)

    async def append_event(self, **kwargs):
        self.events.append(kwargs)


@pytest.mark.asyncio
async def test_rejected_claim_logs_run_state(monkeypatch, caplog) -> None:
    lease_expiry = datetime.now(timezone.utc) + timedelta(seconds=600)
    repo = _RecordingRepo(
        task=_task(),
        run=_run(
            status="running",
            lease_owner="other-worker",
            lease_expires_at=lease_expiry,
            claim_generation=3,
        ),
        claim=None,
    )
    monkeypatch.setattr(
        task_worker_module, "get_production_task_repository", lambda: repo
    )

    with caplog.at_level(logging.WARNING, logger="nexus.task_worker"):
        result = await TaskWorker(worker_id="worker_1").run_once(
            task_id="task_1", run_id="run_1"
        )

    assert result.status == "skipped"
    message = caplog.text
    assert "could not claim task_1/run_1" in message
    assert "other-worker" in message
    assert "claim_generation=3" in message


@pytest.mark.asyncio
async def test_unclaimable_run_is_failed_so_the_client_stops_waiting(
    monkeypatch,
) -> None:
    """An orphaned queued run must be settled, not left polling forever."""
    repo = _RecordingRepo(
        task=_task(),
        # Queued with an expired lease: no worker owns it and none ever will.
        run=_run(
            status="queued",
            lease_owner="dead-worker",
            lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=30),
        ),
        claim=None,
    )
    monkeypatch.setattr(
        task_worker_module, "get_production_task_repository", lambda: repo
    )

    result = await TaskWorker(worker_id="worker_1").run_once(
        task_id="task_1", run_id="run_1"
    )

    assert result.status == "skipped"
    assert repo.finished and repo.finished[0]["status"] == "failed"
    assert repo.events and repo.events[0]["event_type"] == "worker_failed"
    assert repo.events[0]["payload"]["error_code"] == "RUN_NOT_CLAIMABLE"


@pytest.mark.asyncio
async def test_live_lease_owner_is_left_alone(monkeypatch) -> None:
    """Another worker's healthy run must not be failed out from under it."""
    repo = _RecordingRepo(
        task=_task(),
        run=_run(
            status="running",
            lease_owner="other-worker",
            lease_expires_at=datetime.now(timezone.utc) + timedelta(seconds=600),
        ),
        claim=None,
    )
    monkeypatch.setattr(
        task_worker_module, "get_production_task_repository", lambda: repo
    )

    await TaskWorker(worker_id="worker_1").run_once(task_id="task_1", run_id="run_1")

    assert repo.finished == []
    assert repo.events == []


@pytest.mark.asyncio
async def test_rejected_claim_diagnostics_survive_repo_errors(monkeypatch) -> None:
    class ExplodingRepo(_RecordingRepo):
        async def get_task(self, task_id):
            raise RuntimeError("firestore unavailable")

    repo = ExplodingRepo(claim=None)
    monkeypatch.setattr(
        task_worker_module, "get_production_task_repository", lambda: repo
    )

    result = await TaskWorker(worker_id="worker_1").run_once(
        task_id="task_1", run_id="run_1"
    )

    assert result.status == "skipped"


@pytest.mark.asyncio
async def test_crashed_local_worker_marks_run_failed(monkeypatch) -> None:
    repo = _RecordingRepo(task=_task(), run=_run(status="running"))
    monkeypatch.setattr(
        "nexus.dependencies.get_production_task_repository", lambda: repo
    )

    await task_queue_module._fail_unstarted_local_run(
        "task_1", "run_1", RuntimeError("worker blew up")
    )

    assert repo.finished and repo.finished[0]["status"] == "failed"
    assert "worker blew up" in repo.finished[0]["error"]
    assert repo.events and repo.events[0]["event_type"] == "worker_failed"
    assert repo.events[0]["payload"]["origin"] == "local_queue"


@pytest.mark.asyncio
async def test_terminal_run_is_not_failed_again(monkeypatch) -> None:
    repo = _RecordingRepo(task=_task(), run=_run(status="completed"))
    monkeypatch.setattr(
        "nexus.dependencies.get_production_task_repository", lambda: repo
    )

    await task_queue_module._fail_unstarted_local_run(
        "task_1", "run_1", RuntimeError("late crash")
    )

    assert repo.finished == []
    assert repo.events == []


@pytest.mark.asyncio
async def test_local_worker_crash_is_reported(monkeypatch) -> None:
    reported: list[tuple[str, str, str]] = []

    async def fake_fail(task_id, run_id, exc):
        reported.append((task_id, run_id, str(exc)))

    async def exploding_run_once(**kwargs):
        raise RuntimeError("claim exploded")

    monkeypatch.setattr(task_queue_module, "_fail_unstarted_local_run", fake_fail)
    monkeypatch.setattr(
        task_worker_module.task_worker, "run_once", exploding_run_once
    )
    monkeypatch.setattr(task_queue_module.settings, "task_worker_enabled", True)
    monkeypatch.setattr(task_queue_module.settings, "task_queue_local_fallback", True)
    monkeypatch.setattr(task_queue_module.settings, "app_env", "development")

    queue = task_queue_module.TaskQueue()
    result = await queue.enqueue_task_run(task_id="task_1", run_id="run_1")
    assert result.queued is True
    assert result.provider == "local"

    # Let the detached worker task run to completion.
    for _ in range(20):
        await asyncio.sleep(0)
        if reported:
            break

    assert reported == [("task_1", "run_1", "claim exploded")]
