# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import logging
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from google.api_core.exceptions import FailedPrecondition

import nexus.production_tasks as production_tasks_module
import nexus.task_worker as task_worker_module
from nexus.config import settings
from nexus.policy import evaluate_tool_policy
from nexus.production_tasks import (
    ProductionTaskRepository,
    approval_action_hash,
    utcnow,
)
from nexus.task_budget import TaskBudgetGuard
from nexus.task_queue import TaskQueue
from nexus.task_recovery import StaleRunSweeper
from nexus.task_worker import TaskWorker, WorkerRunResult


class _Snapshot:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data or {})


class _Document:
    def __init__(self, document_id: str) -> None:
        self.id = document_id
        self.data = None
        self.collections = {}

    def get(self, transaction=None):
        return _Snapshot(self.data)

    def set(self, data, merge=False):
        if merge and self.data:
            self.data.update(data)
        else:
            self.data = dict(data)

    def collection(self, name):
        return self.collections.setdefault(name, _Collection())


class _Collection:
    def __init__(self) -> None:
        self.docs = {}

    def document(self, document_id):
        return self.docs.setdefault(document_id, _Document(document_id))


class _Transaction:
    def set(self, ref, data, merge=False):
        ref.set(data, merge=merge)


class _Batch:
    """Collects writes and applies them on commit, like a Firestore batch."""

    def __init__(self) -> None:
        self._writes = []

    def set(self, ref, data, merge=False):
        self._writes.append((ref, data, merge))

    def commit(self):
        for ref, data, merge in self._writes:
            ref.set(data, merge=merge)
        self._writes = []


class _Firestore:
    def __init__(self) -> None:
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, _Collection())

    def transaction(self):
        return _Transaction()

    def batch(self):
        return _Batch()


class _MissingStaleRunsIndexQuery:
    def where(self, *, filter):
        return self

    def limit(self, limit):
        return self

    def stream(self):
        raise FailedPrecondition(
            'The query requires a COLLECTION_GROUP_ASC index for collection "runs" '
            'and field "leaseExpiresAt".'
        )


class _MissingStaleRunsIndexFirestore(_Firestore):
    def collection_group(self, name):
        assert name == "runs"
        return _MissingStaleRunsIndexQuery()


def _repository(monkeypatch) -> ProductionTaskRepository:
    monkeypatch.setattr(
        production_tasks_module.firestore,
        "transactional",
        lambda fn: fn,
    )
    repo = ProductionTaskRepository.__new__(ProductionTaskRepository)
    repo._db = _Firestore()
    repo._has_seq_cache = set()
    repo._stale_runs_index_warning_emitted = False
    return repo


def test_list_stale_runs_logs_missing_index_only_once(monkeypatch, caplog) -> None:
    repo = _repository(monkeypatch)
    repo._db = _MissingStaleRunsIndexFirestore()

    with caplog.at_level(logging.WARNING, logger=production_tasks_module.__name__):
        assert repo._list_stale_runs_sync(limit=100) == []
        assert repo._list_stale_runs_sync(limit=100) == []

    warnings = [
        record
        for record in caplog.records
        if "Skipping stale durable-run cleanup" in record.getMessage()
    ]
    assert len(warnings) == 1
    assert all(record.exc_info is None for record in warnings)


def _seed_run(repo: ProductionTaskRepository) -> tuple[_Document, _Document]:
    now = utcnow()
    task_ref = repo._task_ref("task_1")
    task_ref.set(
        {
            "taskId": "task_1",
            "ownerId": "user_1",
            "title": "Test",
            "status": "queued",
            "cancelRequested": False,
            "createdAt": now,
        }
    )
    run_ref = repo._run_ref("task_1", "run_1")
    run_ref.set(
        {
            "runId": "run_1",
            "taskId": "task_1",
            "ownerId": "user_1",
            "status": "queued",
            "attempt": 1,
            "claimToken": "claim_exact",
            "claimGeneration": 0,
            "createdAt": now,
        }
    )
    return task_ref, run_ref


def test_claim_token_generation_lease_and_stale_requeue(monkeypatch) -> None:
    repo = _repository(monkeypatch)
    _, run_ref = _seed_run(repo)

    assert repo._claim_run_sync(
        "task_1",
        "run_1",
        "worker_1",
        "wrong",
    ) is None
    claimed = repo._claim_run_sync(
        "task_1",
        "run_1",
        "worker_1",
        "claim_exact",
    )
    assert claimed is not None
    assert claimed.claim_generation == 1
    assert claimed.lease_owner == "worker_1"
    assert repo._renew_lease_sync(
        "task_1",
        "run_1",
        "worker_1",
        99,
    ) is False
    assert repo._renew_lease_sync(
        "task_1",
        "run_1",
        "worker_1",
        1,
    ) is True

    run_ref.data["leaseExpiresAt"] = utcnow() - timedelta(seconds=1)
    old_token = run_ref.data["claimToken"]
    requeued = repo._requeue_run_sync(
        "task_1",
        "run_1",
        "expired",
        1,
        None,
    )
    assert requeued is not None
    assert requeued.status == "queued"
    assert requeued.attempt == 2
    assert requeued.claim_token != old_token


def test_cancel_request_is_cleared_once_its_run_is_terminal(monkeypatch) -> None:
    """`cancelRequested` blocks claim_run/requeue_run, so it must not outlive its run."""
    repo = _repository(monkeypatch)
    task_ref, run_ref = _seed_run(repo)
    task_ref.data.update(
        {
            "cancelRequested": True,
            "status": "cancelling",
            "currentRunId": "run_1",
        }
    )

    # Still executing: the flag is the only way a live worker learns to stop.
    run_ref.data["status"] = "running"
    assert repo._clear_cancel_request_sync("task_1", "user_1") is False
    assert task_ref.data["cancelRequested"] is True

    run_ref.data["status"] = "cancelled"
    assert repo._clear_cancel_request_sync("task_1", "user_1") is True
    assert task_ref.data["cancelRequested"] is False
    assert task_ref.data["status"] == "cancelled"

    # Idempotent, and never touches another owner's task.
    assert repo._clear_cancel_request_sync("task_1", "user_1") is False
    task_ref.data["cancelRequested"] = True
    assert repo._clear_cancel_request_sync("task_1", "someone_else") is False
    assert task_ref.data["cancelRequested"] is True


def test_new_run_drops_a_cancel_aimed_at_the_previous_run(monkeypatch) -> None:
    """A fresh run is new intent; inheriting the flag makes it unclaimable."""
    repo = _repository(monkeypatch)
    task_ref, _ = _seed_run(repo)
    task_ref.data.update({"cancelRequested": True, "status": "cancelling"})

    run = repo._create_run_sync(
        "task_1",
        "user_1",
        "session-1",
        "hello",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )

    assert task_ref.data["cancelRequested"] is False
    assert repo._claim_run_sync(
        "task_1",
        run.run_id,
        "worker_1",
        run.claim_token,
    ) is not None


def test_budget_guard_enforces_tools_credits_and_runtime(monkeypatch) -> None:
    guard = TaskBudgetGuard.from_budget(
        {"maxRuntimeMinutes": 1, "maxToolCalls": 1, "credits": 2}
    )
    assert guard.before_tool_call("web_search") is True
    assert guard.before_tool_call("web_search") is False
    assert guard.exhausted_code == "BUDGET_TOOL_CALLS_EXHAUSTED"

    credit_guard = TaskBudgetGuard.from_budget(
        {"maxRuntimeMinutes": 1, "maxToolCalls": 10, "credits": 2}
    )
    assert credit_guard.consume_credits(2) is True
    assert credit_guard.consume_credits(1) is False
    assert credit_guard.exhausted_code == "BUDGET_CREDITS_EXHAUSTED"


def test_mcp_side_effects_use_central_policy() -> None:
    destructive = evaluate_tool_policy(
        "mcp__github__publish_release",
        {"arguments": {"tag": "v1"}},
        autonomy_mode="auto",
    )
    read_auto = evaluate_tool_policy(
        "mcp__github__list_releases",
        {},
        autonomy_mode="auto",
    )
    read_manual = evaluate_tool_policy(
        "mcp__github__list_releases",
        {},
        autonomy_mode="manual",
    )

    assert destructive.action == "require_approval"
    assert destructive.risk == "high"
    assert read_auto.action == "allow"
    assert read_manual.action == "require_approval"


def test_action_approval_hash_is_exact_and_opaque() -> None:
    first = approval_action_hash("gmail_send", {"to": "a@example.com"})
    same = approval_action_hash("gmail_send", {"to": "a@example.com"})
    other = approval_action_hash("gmail_send", {"to": "b@example.com"})

    assert first == same
    assert first != other
    assert "example.com" not in first


@pytest.mark.asyncio
async def test_task_worker_persists_final_response_and_verification(
    monkeypatch,
) -> None:
    captured = {}
    claimed = SimpleNamespace(
        task_id="task_1",
        run_id="run_1",
        owner_id="user_1",
        attempt=1,
        claim_generation=1,
    )
    repo = SimpleNamespace(
        claim_run=AsyncMock(return_value=claimed),
        append_event=AsyncMock(),
        finish_run=AsyncMock(side_effect=lambda **kwargs: captured.update(kwargs)),
        pause_run=AsyncMock(),
        renew_lease=AsyncMock(return_value=True),
    )

    class _Worker(TaskWorker):
        async def _execute_claimed_run(self, **kwargs):
            return WorkerRunResult(
                "completed",
                "Verified complete.",
                final_response="Final answer",
                verification={"verified": True, "status": "completed"},
                checkpoint={"version": 1},
            )

    monkeypatch.setattr(
        task_worker_module,
        "get_production_task_repository",
        lambda: repo,
    )
    result = await _Worker(worker_id="worker_1").run_once(
        task_id="task_1",
        run_id="run_1",
        claim_token="claim_exact",
    )

    assert result.status == "completed"
    assert captured["final_response"] == "Final answer"
    assert captured["verification"]["verified"] is True
    repo.pause_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_task_worker_pauses_partial_result(monkeypatch) -> None:
    claimed = SimpleNamespace(
        task_id="task_1",
        run_id="run_1",
        owner_id="user_1",
        attempt=1,
        claim_generation=1,
    )
    repo = SimpleNamespace(
        claim_run=AsyncMock(return_value=claimed),
        append_event=AsyncMock(),
        finish_run=AsyncMock(),
        pause_run=AsyncMock(),
        renew_lease=AsyncMock(return_value=True),
    )

    class _Worker(TaskWorker):
        async def _execute_claimed_run(self, **kwargs):
            return WorkerRunResult(
                "partial",
                "Budget exhausted.",
                verification={"verified": False, "status": "partial"},
                checkpoint={"version": 1},
            )

    monkeypatch.setattr(
        task_worker_module,
        "get_production_task_repository",
        lambda: repo,
    )
    result = await _Worker(worker_id="worker_1").run_once(
        task_id="task_1",
        run_id="run_1",
    )

    assert result.status == "partial"
    assert repo.pause_run.await_args.kwargs["status"] == "paused"
    repo.finish_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_does_not_retry_after_durable_run_already_failed(
    monkeypatch,
) -> None:
    """A timeout that already finished the run must not re-enqueue it."""
    claimed = SimpleNamespace(
        task_id="task_1",
        run_id="run_1",
        owner_id="user_1",
        attempt=1,
        claim_generation=1,
    )
    repo = SimpleNamespace(
        claim_run=AsyncMock(return_value=claimed),
        append_event=AsyncMock(),
        finish_run=AsyncMock(),
        pause_run=AsyncMock(),
        renew_lease=AsyncMock(return_value=True),
        get_run=AsyncMock(
            return_value=SimpleNamespace(status="failed", summary="timed out")
        ),
        requeue_run=AsyncMock(),
    )

    class _Worker(TaskWorker):
        async def _execute_claimed_run(self, **kwargs):
            raise RuntimeError("504 Stream removed (Deadline Exceeded)")

    monkeypatch.setattr(
        task_worker_module,
        "get_production_task_repository",
        lambda: repo,
    )
    result = await _Worker(worker_id="worker_1").run_once(
        task_id="task_1",
        run_id="run_1",
    )

    assert result.status == "failed"
    repo.requeue_run.assert_not_awaited()
    repo.finish_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_run_sweeper_requeues_with_new_claim_token(
    monkeypatch,
) -> None:
    stale = SimpleNamespace(
        task_id="task_1",
        run_id="run_1",
        owner_id="user_1",
        attempt=1,
        claim_generation=3,
    )
    requeued = SimpleNamespace(
        task_id="task_1",
        run_id="run_1",
        owner_id="user_1",
        attempt=2,
        claim_generation=3,
        claim_token="claim_new",
    )
    repo = SimpleNamespace(
        list_stale_runs=AsyncMock(return_value=[stale]),
        requeue_run=AsyncMock(return_value=requeued),
        append_event=AsyncMock(),
        finish_run=AsyncMock(),
    )
    queue = SimpleNamespace(
        enqueue_task_run=AsyncMock(
            return_value=SimpleNamespace(
                queued=True,
                provider="cloud_tasks",
                reason="",
            )
        )
    )
    monkeypatch.setattr(settings, "task_worker_max_attempts", 3)

    recovered = await StaleRunSweeper(repo, queue).sweep()

    assert recovered == 1
    assert (
        queue.enqueue_task_run.await_args.kwargs["claim_token"]
        == "claim_new"
    )


@pytest.mark.asyncio
async def test_stale_run_sweeper_fails_a_run_it_cannot_requeue(monkeypatch) -> None:
    """A refused requeue must not loop forever.

    ``requeue_run`` returns None while the task carries a cancel request, and it
    does not bump ``attempt``, so the exhausted branch is never reached. Skipping
    the run would leave it ``running`` for good and block every later prompt.
    """
    stale = SimpleNamespace(
        task_id="task_1",
        run_id="run_1",
        owner_id="user_1",
        attempt=1,
        claim_generation=3,
    )
    repo = SimpleNamespace(
        list_stale_runs=AsyncMock(return_value=[stale]),
        requeue_run=AsyncMock(return_value=None),
        fail_stale_run=AsyncMock(return_value=True),
        append_event=AsyncMock(),
        finish_run=AsyncMock(),
    )
    queue = SimpleNamespace(enqueue_task_run=AsyncMock())
    monkeypatch.setattr(settings, "task_worker_max_attempts", 3)

    recovered = await StaleRunSweeper(repo, queue).sweep()

    assert recovered == 1
    repo.fail_stale_run.assert_awaited_once()
    assert (
        repo.append_event.await_args.kwargs["event_type"]
        == "worker_recovery_abandoned"
    )
    queue.enqueue_task_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_production_queue_never_uses_local_fallback(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "task_worker_enabled", True)
    monkeypatch.setattr(settings, "task_queue_local_fallback", True)
    monkeypatch.setattr(settings, "gcp_tasks_project_id", "")
    monkeypatch.delenv("K_SERVICE", raising=False)

    result = await TaskQueue().enqueue_task_run(
        task_id="task_1",
        run_id="run_1",
    )

    assert result.queued is False
    assert result.provider == "none"
