# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Durable turns must outlive the socket without ever running twice.

Two properties matter here and they pull in opposite directions:

* a run keeps executing while the browser is away, and a new socket re-attaches
  to it instead of starting over (this is what makes refresh survivable), and
* a second prompt never starts a competing worker on the same session, because
  ``create_run`` happily repoints ``currentRunId`` at a fresh run.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

sys.modules.setdefault(
    "redis",
    SimpleNamespace(Redis=object, from_url=lambda *args, **kwargs: None),
)

from nexus import ws_handler
from nexus.config import settings
from nexus.ws_handler import DurableTurnOutcome


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

    def sent_types(self) -> list[str]:
        return [call.args[0]["type"] for call in self.send_json.call_args_list]

    def sent(self, frame_type: str) -> list[dict]:
        return [
            call.args[0]
            for call in self.send_json.call_args_list
            if call.args[0].get("type") == frame_type
        ]


class FakeOrchestrator:
    instances: list["FakeOrchestrator"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.initialize = AsyncMock()
        self.close = AsyncMock()
        self.bind_durable_run = Mock()
        self.handle_text_input = AsyncMock()
        self.stop_agent = AsyncMock()
        self.history_repository = kwargs.get("history_repository")
        FakeOrchestrator.instances.append(self)

    async def run_voice_receive_loop(self) -> None:
        await asyncio.Event().wait()

    def mark_ws_disconnected(self) -> None:
        return None

    def has_active_agent_turn(self) -> bool:
        return False


class DurableRepo:
    """Minimal durable repository with one task and a run registry."""

    def __init__(self, *, owner_id: str = "owner_1") -> None:
        self.owner_id = owner_id
        self.task = SimpleNamespace(
            task_id="task_1",
            owner_id=owner_id,
            status="running",
            title="t",
            input_text="hi",
            session_id="session-1",
            current_run_id=None,
            cancel_requested=False,
        )
        self.runs: dict[str, SimpleNamespace] = {}
        self.events: list[SimpleNamespace] = []
        self.created_runs = 0
        self.cancel_requests = 0
        self.cleared_cancels = 0

    def add_run(self, run_id: str, status: str) -> SimpleNamespace:
        now = datetime.now(timezone.utc)
        run = SimpleNamespace(
            run_id=run_id,
            task_id=self.task.task_id,
            owner_id=self.owner_id,
            status=status,
            execution_payload={"input_text": "hi"},
            claim_token=f"claim_{run_id}",
            created_at=now,
            updated_at=now,
            lease_owner=None,
            lease_expires_at=None,
        )
        self.runs[run_id] = run
        self.task.current_run_id = run_id
        return run

    def age_run(self, run_id: str, seconds: float) -> SimpleNamespace:
        run = self.runs[run_id]
        run.updated_at = datetime.now(timezone.utc) - timedelta(seconds=seconds)
        run.created_at = run.updated_at
        return run

    async def get_task(self, task_id: str):
        return self.task if task_id == self.task.task_id else None

    async def get_run(self, *, task_id: str, run_id: str, owner_id: str):
        run = self.runs.get(run_id)
        if run is None or run.task_id != task_id or owner_id != self.owner_id:
            return None
        return run

    async def create_task(self, **kwargs):
        return self.task

    async def create_run(self, **kwargs):
        self.created_runs += 1
        # Mirrors the store: a new run is new intent, so a stale cancel is dropped.
        self.task.cancel_requested = False
        return self.add_run(f"run_new_{self.created_runs}", "queued")

    async def finish_run(self, **kwargs):
        run = self.runs.get(kwargs["run_id"])
        if run is not None:
            run.status = kwargs.get("status") or "failed"

    async def request_cancel(self, *, task_id: str, owner_id: str) -> bool:
        if task_id != self.task.task_id or owner_id != self.owner_id:
            return False
        self.cancel_requests += 1
        self.task.cancel_requested = True
        self.task.status = "cancelling"
        run = self.runs.get(self.task.current_run_id or "")
        if run is not None and run.status not in {"completed", "failed", "cancelled"}:
            run.status = "cancelling"
        return True

    async def clear_cancel_request(self, *, task_id: str, owner_id: str) -> bool:
        if task_id != self.task.task_id or owner_id != self.owner_id:
            return False
        if not self.task.cancel_requested:
            return False
        run = self.runs.get(self.task.current_run_id or "")
        if run is not None and run.status not in {"completed", "failed", "cancelled"}:
            return False
        self.cleared_cancels += 1
        self.task.cancel_requested = False
        return True

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

    async def list_events(
        self,
        *,
        task_id: str,
        owner_id: str,
        after_seq=None,
        run_id=None,
        limit=100,
        **kwargs,
    ):
        min_seq = int(after_seq or 0)
        return [
            event
            for event in self.events
            if event.task_id == task_id
            and event.owner_id == owner_id
            and event.seq > min_seq
            and (not run_id or event.run_id == run_id)
        ][:limit]


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[dict] = []

    def is_configured(self) -> bool:
        return True

    async def enqueue_task_run(self, **kwargs):
        self.enqueued.append(kwargs)
        return SimpleNamespace(queued=True, provider="local", name="q", reason="")


def _session(repo: DurableRepo, *, current_run_id: str | None = None):
    return SimpleNamespace(
        id="session-1",
        owner_id=repo.owner_id,
        task_id=repo.task.task_id,
        current_run_id=current_run_id,
        runtime_config=None,
        touch=lambda: None,
    )


def _session_manager():
    return SimpleNamespace(
        history_repository=None,
        activate_session=AsyncMock(),
        destroy_session=AsyncMock(),
        cancel_idle_pause=Mock(),
        schedule_idle_pause=Mock(),
    )


# ── Finding a run that is still executing ─────────────────────────────


@pytest.mark.asyncio
async def test_running_durable_run_is_discoverable(monkeypatch) -> None:
    repo = DurableRepo()
    repo.add_run("run_live", "running")
    monkeypatch.setattr(ws_handler, "get_production_task_repository", lambda: repo)

    found = await ws_handler._find_inflight_durable_run(_session(repo))

    assert found == ("task_1", "run_live")


@pytest.mark.asyncio
async def test_finished_durable_run_is_not_inflight(monkeypatch) -> None:
    repo = DurableRepo()
    repo.add_run("run_done", "completed")
    monkeypatch.setattr(ws_handler, "get_production_task_repository", lambda: repo)

    assert await ws_handler._find_inflight_durable_run(_session(repo)) is None


@pytest.mark.asyncio
async def test_queued_run_is_inflight_during_its_grace_window(monkeypatch) -> None:
    """A just-enqueued run has no lease yet, but a worker is on its way."""
    repo = DurableRepo()
    run = repo.add_run("run_fresh", "queued")
    run.updated_at = datetime.now(timezone.utc)
    monkeypatch.setattr(ws_handler, "get_production_task_repository", lambda: repo)

    assert await ws_handler._find_inflight_durable_run(_session(repo)) == (
        "task_1",
        "run_fresh",
    )
    assert run.status == "queued"


@pytest.mark.asyncio
async def test_never_claimed_run_is_failed_instead_of_blocking_forever(
    monkeypatch,
) -> None:
    """The stale sweeper ignores queued runs, so this guard must self-heal.

    Otherwise a run that no worker ever claimed would make every later prompt on
    the session fail with RUN_IN_PROGRESS for good.
    """
    repo = DurableRepo()
    run = repo.add_run("run_orphan", "queued")
    repo.age_run("run_orphan", settings.abandoned_run_grace_seconds + 120)
    monkeypatch.setattr(ws_handler, "get_production_task_repository", lambda: repo)

    assert await ws_handler._find_inflight_durable_run(_session(repo)) is None
    assert run.status == "failed"
    assert repo.events[-1].event_type == "worker_failed"
    assert repo.events[-1].payload["error_code"] == "RUN_ABANDONED"


@pytest.mark.asyncio
async def test_running_run_with_a_dead_lease_is_failed(monkeypatch) -> None:
    """The sweeper owns this case, but it silently no-ops without its index.

    A connecting client is the only recovery path the user can rely on, so a
    `running` run that nothing has touched for the grace window is settled here.
    """
    repo = DurableRepo()
    run = repo.add_run("run_zombie", "running")
    repo.age_run("run_zombie", settings.abandoned_run_grace_seconds + 60)
    monkeypatch.setattr(ws_handler, "get_production_task_repository", lambda: repo)

    assert await ws_handler._find_inflight_durable_run(_session(repo)) is None
    assert run.status == "failed"
    assert repo.events[-1].payload["error_code"] == "RUN_LEASE_LOST"


@pytest.mark.asyncio
async def test_cancelling_run_without_a_worker_is_settled(monkeypatch) -> None:
    """Stop was pressed with no worker alive to honor it.

    `cancelRequested` blocks claim_run and requeue_run, so leaving this run open
    would make the whole task permanently unusable.
    """
    repo = DurableRepo()
    run = repo.add_run("run_cancelling", "cancelling")
    repo.task.cancel_requested = True
    repo.age_run("run_cancelling", 300)
    monkeypatch.setattr(ws_handler, "get_production_task_repository", lambda: repo)

    assert await ws_handler._find_inflight_durable_run(_session(repo)) is None
    assert run.status == "failed"
    assert repo.events[-1].payload["error_code"] == "RUN_CANCEL_ORPHANED"
    # The tombstone is released, otherwise every future run stays unclaimable.
    assert repo.task.cancel_requested is False
    assert repo.cleared_cancels == 1


@pytest.mark.asyncio
async def test_expired_waiting_approval_is_settled(monkeypatch) -> None:
    """The approval prompt expires client- and server-side; the run must too."""
    repo = DurableRepo()
    run = repo.add_run("run_wait", "waiting_approval")
    repo.age_run("run_wait", settings.abandoned_approval_grace_seconds + 60)
    monkeypatch.setattr(ws_handler, "get_production_task_repository", lambda: repo)

    assert await ws_handler._find_inflight_durable_run(_session(repo)) is None
    assert run.status == "failed"
    assert repo.events[-1].payload["error_code"] == "APPROVAL_EXPIRED"


@pytest.mark.asyncio
async def test_stale_cancel_flag_is_cleared_when_the_run_is_terminal(
    monkeypatch,
) -> None:
    """Nothing else clears `cancelRequested`, and it blocks every future claim."""
    repo = DurableRepo()
    repo.add_run("run_done", "completed")
    repo.task.cancel_requested = True
    monkeypatch.setattr(ws_handler, "get_production_task_repository", lambda: repo)

    assert await ws_handler._find_inflight_durable_run(_session(repo)) is None
    assert repo.task.cancel_requested is False


@pytest.mark.asyncio
async def test_stale_queued_run_with_a_live_lease_is_left_alone(monkeypatch) -> None:
    """A claimed run mid-transition to running still belongs to its worker."""
    repo = DurableRepo()
    run = repo.add_run("run_claimed", "queued")
    run.updated_at = datetime.now(timezone.utc) - timedelta(hours=2)
    run.lease_owner = "worker_a"
    run.lease_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    monkeypatch.setattr(ws_handler, "get_production_task_repository", lambda: repo)

    assert await ws_handler._find_inflight_durable_run(_session(repo)) == (
        "task_1",
        "run_claimed",
    )
    assert run.status == "queued"


@pytest.mark.asyncio
async def test_another_owners_task_is_never_adopted(monkeypatch) -> None:
    repo = DurableRepo()
    repo.add_run("run_live", "running")
    monkeypatch.setattr(ws_handler, "get_production_task_repository", lambda: repo)

    stranger = _session(repo)
    stranger.owner_id = "someone_else"

    assert await ws_handler._find_inflight_durable_run(stranger) is None


# ── One run at a time ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_second_prompt_does_not_start_a_competing_run(monkeypatch) -> None:
    """A follow-up prompt must not become a rival worker.

    It also must not be a dead end: the client is attached to the run that is
    still executing so its progress stays visible.
    """
    repo = DurableRepo()
    repo.add_run("run_live", "running")
    queue = FakeQueue()
    monkeypatch.setattr(ws_handler, "get_production_task_repository", lambda: repo)
    monkeypatch.setattr(ws_handler, "get_task_queue", lambda: queue)
    monkeypatch.setattr(ws_handler.settings, "task_worker_enabled", True)

    sent: list[dict] = []

    async def send_json(frame: dict) -> bool:
        sent.append(frame)
        return True

    session = _session(repo, current_run_id="run_live")
    bind = Mock()
    outcome = await ws_handler._try_start_durable_text_run(
        session=session,
        orchestrator=SimpleNamespace(bind_durable_run=bind),
        text="follow-up",
        connector_ids=[],
        tool_ids=[],
        uploaded_files=[],
        send_json=send_json,
    )

    assert outcome is DurableTurnOutcome.ATTACHED
    assert repo.created_runs == 0
    assert queue.enqueued == []
    # The user must be told why, otherwise this is just another silent drop.
    assert sent and sent[0]["type"] == "run_busy"
    assert sent[0]["code"] == "RUN_IN_PROGRESS"
    assert sent[0]["run_id"] == "run_live"
    # Attached, so events from the live run reach this socket.
    bind.assert_called_once_with(task_id="task_1", run_id="run_live")
    assert session.current_run_id == "run_live"


@pytest.mark.asyncio
async def test_prompt_after_paused_run_is_queued(monkeypatch) -> None:
    """A paused run is not executing; a new prompt must replace it, not RUN_IN_PROGRESS."""
    repo = DurableRepo()
    repo.add_run("run_paused", "paused")
    queue = FakeQueue()
    monkeypatch.setattr(ws_handler, "get_production_task_repository", lambda: repo)
    monkeypatch.setattr(ws_handler, "get_task_queue", lambda: queue)
    monkeypatch.setattr(ws_handler.settings, "task_worker_enabled", True)

    outcome = await ws_handler._try_start_durable_text_run(
        session=_session(repo, current_run_id="run_paused"),
        orchestrator=SimpleNamespace(bind_durable_run=Mock()),
        text="next",
        connector_ids=[],
        tool_ids=[],
        uploaded_files=[],
        send_json=AsyncMock(return_value=True),
    )

    assert outcome is DurableTurnOutcome.STARTED
    assert repo.runs["run_paused"].status == "cancelled"
    assert repo.created_runs == 1
    assert len(queue.enqueued) == 1
    assert any(
        event.payload.get("error_code") == "RUN_SUPERSEDED" for event in repo.events
    )


@pytest.mark.asyncio
async def test_fresh_waiting_approval_attaches_instead_of_erroring(monkeypatch) -> None:
    """A live approval still owns the turn, but the user must see it, not an error."""
    repo = DurableRepo()
    repo.add_run("run_wait", "waiting_approval")
    queue = FakeQueue()
    monkeypatch.setattr(ws_handler, "get_production_task_repository", lambda: repo)
    monkeypatch.setattr(ws_handler, "get_task_queue", lambda: queue)
    monkeypatch.setattr(ws_handler.settings, "task_worker_enabled", True)

    sent: list[dict] = []

    async def send_json(frame: dict) -> bool:
        sent.append(frame)
        return True

    outcome = await ws_handler._try_start_durable_text_run(
        session=_session(repo, current_run_id="run_wait"),
        orchestrator=SimpleNamespace(bind_durable_run=Mock()),
        text="follow-up",
        connector_ids=[],
        tool_ids=[],
        uploaded_files=[],
        send_json=send_json,
    )

    assert outcome is DurableTurnOutcome.ATTACHED
    assert repo.created_runs == 0
    assert sent and sent[0]["type"] == "run_busy"
    assert sent[0]["run_status"] == "waiting_approval"


@pytest.mark.asyncio
async def test_prompt_after_the_previous_run_finished_is_queued(monkeypatch) -> None:
    repo = DurableRepo()
    repo.add_run("run_done", "completed")
    queue = FakeQueue()
    monkeypatch.setattr(ws_handler, "get_production_task_repository", lambda: repo)
    monkeypatch.setattr(ws_handler, "get_task_queue", lambda: queue)
    monkeypatch.setattr(ws_handler.settings, "task_worker_enabled", True)

    outcome = await ws_handler._try_start_durable_text_run(
        session=_session(repo, current_run_id="run_done"),
        orchestrator=SimpleNamespace(bind_durable_run=Mock()),
        text="next",
        connector_ids=[],
        tool_ids=[],
        uploaded_files=[],
        send_json=AsyncMock(return_value=True),
    )

    assert outcome is DurableTurnOutcome.STARTED
    assert repo.created_runs == 1
    assert len(queue.enqueued) == 1


@pytest.mark.asyncio
async def test_rejected_turn_does_not_fall_back_to_live_execution(monkeypatch) -> None:
    """The busy rejection must not spawn a live agent alongside the worker."""
    repo = DurableRepo()
    repo.add_run("run_live", "running")
    FakeOrchestrator.instances = []
    ws = FakeWebSocket(
        [
            {"text": json.dumps({"type": "text_input", "text": "second prompt"})},
            {"type": "websocket.disconnect"},
        ]
    )
    monkeypatch.setattr(ws_handler, "NexusOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(ws_handler, "get_production_task_repository", lambda: repo)
    monkeypatch.setattr(ws_handler, "get_task_queue", lambda: FakeQueue())
    monkeypatch.setattr(ws_handler.settings, "task_worker_enabled", True)

    await ws_handler.handle_websocket(
        ws, _session(repo, current_run_id="run_live"), _session_manager()
    )

    orchestrator = FakeOrchestrator.instances[0]
    orchestrator.handle_text_input.assert_not_awaited()
    assert repo.created_runs == 0
    busy = ws.sent("run_busy")
    assert busy and busy[0]["code"] == "RUN_IN_PROGRESS"


@pytest.mark.asyncio
async def test_stop_settles_a_run_no_worker_owns(monkeypatch) -> None:
    """Stop must not leave a cancel tombstone that bricks the task.

    `request_cancel` only raises a flag; with no live lease nothing would ever
    observe it, and the flag alone makes every future run unclaimable.
    """
    repo = DurableRepo()
    run = repo.add_run("run_live", "running")
    FakeOrchestrator.instances = []
    ws = FakeWebSocket(
        [
            {"text": json.dumps({"type": "stop_agent"})},
            {"type": "websocket.disconnect"},
        ]
    )
    monkeypatch.setattr(ws_handler, "NexusOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(ws_handler, "get_production_task_repository", lambda: repo)
    monkeypatch.setattr(ws_handler, "get_task_queue", lambda: FakeQueue())
    monkeypatch.setattr(ws_handler.settings, "task_worker_enabled", True)

    await ws_handler.handle_websocket(
        ws, _session(repo, current_run_id="run_live"), _session_manager()
    )

    assert repo.cancel_requests == 1
    assert run.status == "failed"
    assert repo.task.cancel_requested is False
    finished = ws.sent("worker_finished")
    assert finished and finished[0]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_stop_leaves_a_live_worker_to_honor_the_cancel(monkeypatch) -> None:
    """A worker holding the lease runs its own cancel watcher; do not race it."""
    repo = DurableRepo()
    run = repo.add_run("run_live", "running")
    run.lease_owner = "worker_a"
    run.lease_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    FakeOrchestrator.instances = []
    ws = FakeWebSocket(
        [
            {"text": json.dumps({"type": "stop_agent"})},
            {"type": "websocket.disconnect"},
        ]
    )
    monkeypatch.setattr(ws_handler, "NexusOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(ws_handler, "get_production_task_repository", lambda: repo)
    monkeypatch.setattr(ws_handler, "get_task_queue", lambda: FakeQueue())
    monkeypatch.setattr(ws_handler.settings, "task_worker_enabled", True)

    await ws_handler.handle_websocket(
        ws, _session(repo, current_run_id="run_live"), _session_manager()
    )

    assert repo.cancel_requests == 1
    assert run.status == "cancelling"
    assert repo.task.cancel_requested is True
    assert ws.sent("worker_finished") == []


# ── Re-attaching after a refresh ──────────────────────────────────────


@pytest.mark.asyncio
async def test_reconnect_reattaches_to_the_running_worker(monkeypatch) -> None:
    """A fresh socket adopts the in-flight run instead of ignoring it."""
    repo = DurableRepo()
    repo.add_run("run_live", "running")
    await repo.append_event(
        task_id="task_1",
        owner_id=repo.owner_id,
        run_id="run_live",
        event_type="agent_thinking",
        payload={"text": "still going"},
    )
    FakeOrchestrator.instances = []
    monkeypatch.setattr(ws_handler, "NexusOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(ws_handler, "get_production_task_repository", lambda: repo)
    monkeypatch.setattr(ws_handler, "get_task_queue", lambda: FakeQueue())
    monkeypatch.setattr(ws_handler.settings, "task_worker_enabled", True)

    ws = FakeWebSocket()
    await ws_handler.handle_websocket(
        ws, _session(repo, current_run_id="run_live"), _session_manager()
    )

    orchestrator = FakeOrchestrator.instances[0]
    orchestrator.bind_durable_run.assert_called_once_with(
        task_id="task_1", run_id="run_live"
    )
    claims = ws.sent("worker_claimed")
    assert claims and claims[0]["reattached"] is True


@pytest.mark.asyncio
async def test_reconnect_without_an_active_run_changes_nothing(monkeypatch) -> None:
    repo = DurableRepo()
    repo.add_run("run_done", "completed")
    FakeOrchestrator.instances = []
    monkeypatch.setattr(ws_handler, "NexusOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(ws_handler, "get_production_task_repository", lambda: repo)
    monkeypatch.setattr(ws_handler, "get_task_queue", lambda: FakeQueue())
    monkeypatch.setattr(ws_handler.settings, "task_worker_enabled", True)

    ws = FakeWebSocket()
    await ws_handler.handle_websocket(
        ws, _session(repo, current_run_id="run_done"), _session_manager()
    )

    FakeOrchestrator.instances[0].bind_durable_run.assert_not_called()
    assert ws.sent("worker_claimed") == []


@pytest.mark.asyncio
async def test_durable_lookup_failure_still_lets_the_client_connect(
    monkeypatch,
) -> None:
    """A Firestore hiccup at connect time must not break the session."""

    class ExplodingRepo(DurableRepo):
        async def get_task(self, task_id: str):
            raise RuntimeError("firestore unavailable")

    repo = ExplodingRepo()
    FakeOrchestrator.instances = []
    monkeypatch.setattr(ws_handler, "NexusOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(ws_handler, "get_production_task_repository", lambda: repo)
    monkeypatch.setattr(ws_handler, "get_task_queue", lambda: FakeQueue())
    monkeypatch.setattr(ws_handler.settings, "task_worker_enabled", True)

    ws = FakeWebSocket()
    await ws_handler.handle_websocket(ws, _session(repo), _session_manager())

    ws.accept.assert_awaited_once()
    assert "error" not in ws.sent_types()
