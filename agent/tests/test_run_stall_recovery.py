# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""A wedged run must release its grip on the session.

Every recovery path treats a live Firestore lease as proof that a worker is
making progress, so a heartbeat that renews unconditionally lets a hung worker
hold a session hostage: each new prompt comes back as ``run_busy`` until the
process dies. These tests pin the signals that break that deadlock — the
progress beacon, the heartbeat that consults it, the stop button that stops
trusting a lease, and sandbox death escaping a tool body so reconnect can run.
"""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.modules.setdefault(
    "redis",
    SimpleNamespace(Redis=object, from_url=lambda *args, **kwargs: None),
)

from nexus import run_progress
from nexus import task_worker as task_worker_module
from nexus import ws_handler as ws_handler_module
from nexus.production_tasks import DurableTask, DurableTaskRun
from nexus.sandbox import SandboxDeadError
from nexus.task_worker import TaskWorker


@pytest.fixture(autouse=True)
def _clean_progress_registry():
    run_progress._last_progress.clear()
    run_progress._tools_in_flight.clear()
    yield
    run_progress._last_progress.clear()
    run_progress._tools_in_flight.clear()


# --------------------------------------------------------------------------
# Progress beacon
# --------------------------------------------------------------------------


def test_untracked_run_is_never_stalled() -> None:
    """An unknown run must not be reported as stalled, or every non-durable
    turn would look dead to the heartbeat."""
    assert run_progress.is_stalled("run_unknown", 1.0) is False


def test_silence_past_the_timeout_is_a_stall() -> None:
    run_progress.start_tracking("run_1")
    run_progress._last_progress["run_1"] = time.monotonic() - 120.0

    assert run_progress.is_stalled("run_1", 60.0) is True


def test_progress_clears_a_stall() -> None:
    run_progress.start_tracking("run_1")
    run_progress._last_progress["run_1"] = time.monotonic() - 120.0
    run_progress.mark_progress("run_1")

    assert run_progress.is_stalled("run_1", 60.0) is False


def test_a_long_tool_call_is_not_a_stall() -> None:
    """Sandbox provisioning and playwright installs run for minutes without
    emitting an agent event; that must not look like a hung model."""
    run_progress.start_tracking("run_1")
    run_progress.tool_started("run_1")
    run_progress._last_progress["run_1"] = time.monotonic() - 600.0

    assert run_progress.is_stalled("run_1", 60.0) is False

    run_progress.tool_finished("run_1")
    assert run_progress.is_stalled("run_1", 60.0) is False  # finishing is progress


def test_nested_tool_calls_only_resume_the_check_once_all_finish() -> None:
    run_progress.start_tracking("run_1")
    run_progress.tool_started("run_1")
    run_progress.tool_started("run_1")
    run_progress.tool_finished("run_1")
    run_progress._last_progress["run_1"] = time.monotonic() - 600.0

    assert run_progress.is_stalled("run_1", 60.0) is False

    run_progress.tool_finished("run_1")
    run_progress._last_progress["run_1"] = time.monotonic() - 600.0
    assert run_progress.is_stalled("run_1", 60.0) is True


def test_progress_does_not_resurrect_an_untracked_run() -> None:
    run_progress.mark_progress("run_gone")

    assert run_progress.seconds_since_progress("run_gone") is None


def test_stop_tracking_clears_in_flight_tools() -> None:
    run_progress.start_tracking("run_1")
    run_progress.tool_started("run_1")
    run_progress.stop_tracking("run_1")

    assert run_progress.seconds_since_progress("run_1") is None
    assert "run_1" not in run_progress._tools_in_flight


# --------------------------------------------------------------------------
# Lease heartbeat
# --------------------------------------------------------------------------


class _LeaseRepo:
    def __init__(self) -> None:
        self.renewals = 0

    async def renew_lease(self, **kwargs) -> bool:
        self.renewals += 1
        return True


@pytest.mark.asyncio
async def test_heartbeat_releases_the_lease_when_the_agent_goes_quiet(
    monkeypatch,
) -> None:
    """Renewing asserts progress. A stalled run must stop asserting it so the
    stale-run sweeper and abandoned-run settle can finally act."""
    repo = _LeaseRepo()
    monkeypatch.setattr(
        task_worker_module.settings, "task_worker_heartbeat_interval_seconds", 1
    )
    monkeypatch.setattr(task_worker_module.settings, "task_worker_lease_seconds", 600)
    monkeypatch.setattr(run_progress, "is_stalled", lambda run_id, timeout: True)

    with pytest.raises(RuntimeError, match="no progress"):
        await asyncio.wait_for(
            TaskWorker(worker_id="worker_1")._lease_heartbeat(
                repo=repo, task_id="task_1", run_id="run_1", claim_generation=1
            ),
            timeout=5,
        )

    assert repo.renewals == 0


@pytest.mark.asyncio
async def test_heartbeat_renews_while_the_agent_is_working(monkeypatch) -> None:
    repo = _LeaseRepo()
    monkeypatch.setattr(
        task_worker_module.settings, "task_worker_heartbeat_interval_seconds", 1
    )
    monkeypatch.setattr(task_worker_module.settings, "task_worker_lease_seconds", 600)
    monkeypatch.setattr(run_progress, "is_stalled", lambda run_id, timeout: False)

    heartbeat = asyncio.create_task(
        TaskWorker(worker_id="worker_1")._lease_heartbeat(
            repo=repo, task_id="task_1", run_id="run_1", claim_generation=1
        )
    )
    await asyncio.sleep(1.2)
    heartbeat.cancel()
    await asyncio.gather(heartbeat, return_exceptions=True)

    assert repo.renewals >= 1
    # The registry must not leak once the heartbeat is gone.
    assert run_progress.seconds_since_progress("run_1") is None


@pytest.mark.asyncio
async def test_heartbeat_tracks_the_run_so_progress_can_be_recorded(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        task_worker_module.settings, "task_worker_heartbeat_interval_seconds", 60
    )
    monkeypatch.setattr(task_worker_module.settings, "task_worker_lease_seconds", 600)

    heartbeat = asyncio.create_task(
        TaskWorker(worker_id="worker_1")._lease_heartbeat(
            repo=_LeaseRepo(), task_id="task_1", run_id="run_1", claim_generation=1
        )
    )
    await asyncio.sleep(0)
    tracked = run_progress.seconds_since_progress("run_1")
    heartbeat.cancel()
    await asyncio.gather(heartbeat, return_exceptions=True)

    assert tracked is not None


# --------------------------------------------------------------------------
# Stop button vs a leased worker that never acks
# --------------------------------------------------------------------------


def _run(**overrides) -> DurableTaskRun:
    now = datetime.now(timezone.utc)
    defaults = dict(
        run_id="run_1",
        task_id="task_1",
        owner_id="user_1",
        status="running",
        created_at=now,
        updated_at=now,
        lease_expires_at=now + timedelta(seconds=600),
    )
    defaults.update(overrides)
    return DurableTaskRun(**defaults)


class _StopRepo:
    def __init__(self, run) -> None:
        self._run = run
        self.finished: list[dict] = []
        self.events: list[dict] = []
        self.cancel_cleared = False

    async def get_run(self, *, task_id, run_id, owner_id):
        return self._run

    async def finish_run(self, **kwargs):
        self.finished.append(kwargs)

    async def append_event(self, **kwargs):
        self.events.append(kwargs)

    async def clear_cancel_request(self, **kwargs):
        self.cancel_cleared = True


@pytest.mark.asyncio
async def test_stop_settles_a_leased_run_that_ignores_the_cancel(
    monkeypatch,
) -> None:
    """The wedged worker keeps heartbeating, so trusting the lease would leave
    the session refusing every later prompt as busy."""
    repo = _StopRepo(_run(status="running"))
    monkeypatch.setattr(
        ws_handler_module, "get_production_task_repository", lambda: repo
    )
    monkeypatch.setattr(ws_handler_module.settings, "durable_stop_grace_seconds", 1)
    sent: list[dict] = []

    await ws_handler_module._enforce_durable_stop(
        session=SimpleNamespace(id="session_1", owner_id="user_1"),
        task_id="task_1",
        run_id="run_1",
        send_json=lambda payload: sent.append(payload) or asyncio.sleep(0),
    )

    assert repo.finished and repo.finished[0]["status"] == "failed"
    assert repo.cancel_cleared is True
    assert sent and sent[0]["type"] == "worker_finished"
    assert sent[0]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_stop_enforcement_leaves_a_worker_that_did_ack_alone(
    monkeypatch,
) -> None:
    repo = _StopRepo(_run(status="cancelled"))
    monkeypatch.setattr(
        ws_handler_module, "get_production_task_repository", lambda: repo
    )
    monkeypatch.setattr(ws_handler_module.settings, "durable_stop_grace_seconds", 1)
    sent: list[dict] = []

    await ws_handler_module._enforce_durable_stop(
        session=SimpleNamespace(id="session_1", owner_id="user_1"),
        task_id="task_1",
        run_id="run_1",
        send_json=lambda payload: sent.append(payload) or asyncio.sleep(0),
    )

    assert repo.finished == []
    # The stale flag still has to go, or claim_run refuses every future run.
    assert repo.cancel_cleared is True
    assert sent == []


# --------------------------------------------------------------------------
# Sandbox death must escape tool bodies
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_command_lets_sandbox_death_reach_the_reconnect_path() -> None:
    """`run_command` catches bare Exception; without an explicit re-raise the
    decorator's reconnect never fires and the agent talks to a dead machine."""
    from nexus.tools.bash import run_command

    attempts: list[str] = []

    class _DeadSandbox:
        def run_command(self, *args, **kwargs):
            attempts.append("run")
            raise SandboxDeadError()

    async def fake_ensure():
        return _DeadSandbox()

    with (
        patch("nexus.tools._context.ensure_sandbox", fake_ensure),
        patch("nexus.tools._context.get_sandbox", lambda: _DeadSandbox()),
    ):
        result = await run_command("echo hi")

    # Two attempts: the original plus the decorator's single reconnect retry.
    assert len(attempts) == 2
    assert result["status"] == "error"
    assert result["error_code"] == "SANDBOX_RECONNECT_FAILED"
    assert result["retryable"] is True


@pytest.mark.asyncio
async def test_ordinary_command_failure_still_returns_a_tool_error() -> None:
    from nexus.tools.bash import run_command

    class _BrokenSandbox:
        def run_command(self, *args, **kwargs):
            raise RuntimeError("command blew up")

    async def fake_ensure():
        return _BrokenSandbox()

    with (
        patch("nexus.tools._context.ensure_sandbox", fake_ensure),
        patch("nexus.tools._context.get_sandbox", lambda: _BrokenSandbox()),
    ):
        result = await run_command("echo hi")

    assert result["status"] == "error"
    assert result["error_code"] == "COMMAND_EXCEPTION"


def test_input_calls_convert_a_remote_gone_fault_into_sandbox_death() -> None:
    """Clicks go straight to the SDK, so without this a 404 is just an opaque
    error and nothing ever rebuilds the sandbox."""
    from nexus.sandbox import SandboxManager

    manager = SandboxManager()

    class _DeadClient:
        def left_click(self, x, y):
            raise RuntimeError("sandbox not found")

    manager._sandbox = _DeadClient()

    with pytest.raises(SandboxDeadError):
        manager.left_click(1, 2)

    assert manager.is_alive is False
