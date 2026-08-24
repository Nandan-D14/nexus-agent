# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Production stack tests: local durable queue, context builder, memory, retrieval."""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

sys.modules.setdefault(
    "redis",
    SimpleNamespace(Redis=object, from_url=lambda *args, **kwargs: None),
)

from nexus.config import settings
from nexus.context_builder import (
    PRIORITY_MEMORY,
    PRIORITY_RESUME,
    PRIORITY_TURN,
    TurnContextBuilder,
)
from nexus.memory import MemoryFact, format_memory_block
from nexus.task_queue import TaskQueue


# ── Layer 6: local durable queue ─────────────────────────────


@pytest.mark.asyncio
async def test_local_fallback_enqueues_in_process_worker(monkeypatch) -> None:
    monkeypatch.setattr(settings, "task_worker_enabled", True)
    monkeypatch.setattr(settings, "task_queue_local_fallback", True)
    monkeypatch.setattr(settings, "gcp_tasks_project_id", "")

    import nexus.task_worker as task_worker_module

    run_once = AsyncMock(return_value=SimpleNamespace(status="completed", summary="ok"))
    monkeypatch.setattr(task_worker_module.task_worker, "run_once", run_once)

    result = await TaskQueue().enqueue_task_run(task_id="task_x", run_id="run_y")

    assert result.queued is True
    assert result.provider == "local"

    # The worker runs detached; give the loop a beat to execute it.
    for _ in range(20):
        await asyncio.sleep(0.01)
        if run_once.await_count:
            break
    run_once.assert_awaited_once_with(task_id="task_x", run_id="run_y")


@pytest.mark.asyncio
async def test_local_fallback_disabled_returns_noop(monkeypatch) -> None:
    monkeypatch.setattr(settings, "task_worker_enabled", True)
    monkeypatch.setattr(settings, "task_queue_local_fallback", False)
    monkeypatch.setattr(settings, "gcp_tasks_project_id", "")

    result = await TaskQueue().enqueue_task_run(task_id="task_x", run_id="run_y")

    assert result.queued is False
    assert "not configured" in result.reason.lower()


def test_is_configured_respects_local_fallback(monkeypatch) -> None:
    monkeypatch.setattr(settings, "gcp_tasks_project_id", "")
    monkeypatch.setattr(settings, "task_queue_local_fallback", True)
    assert TaskQueue().is_configured() is True

    monkeypatch.setattr(settings, "task_queue_local_fallback", False)
    assert TaskQueue().is_configured() is False


@pytest.mark.asyncio
async def test_worker_disabled_never_spawns_local(monkeypatch) -> None:
    monkeypatch.setattr(settings, "task_worker_enabled", False)
    monkeypatch.setattr(settings, "task_queue_local_fallback", True)

    result = await TaskQueue().enqueue_task_run(task_id="task_x", run_id="run_y")

    assert result.queued is False
    assert "disabled" in result.reason.lower()


# ── Layer 6: durable cancel watcher ──────────────────────────


@pytest.mark.asyncio
async def test_cancel_watcher_stops_run_when_cancel_requested(monkeypatch) -> None:
    import nexus.agent_turn_runner as runner_module
    from nexus.agent_turn_runner import AgentTurnRunner

    monkeypatch.setattr(runner_module, "_CANCEL_POLL_SECONDS", 0.01)

    repo = SimpleNamespace(
        get_task=AsyncMock(
            return_value=SimpleNamespace(
                owner_id="user-1", cancel_requested=True, status="cancelling"
            )
        )
    )
    orchestrator = SimpleNamespace(stop_agent=AsyncMock())
    runner = AgentTurnRunner(session_manager=None, production_task_repository=repo)

    await asyncio.wait_for(
        runner._watch_for_cancel(orchestrator, "task_1", "user-1"), timeout=2.0
    )

    orchestrator.stop_agent.assert_awaited_once()


# ── Layer 1: turn context builder ────────────────────────────


def test_builder_orders_blocks_and_appends_user_text() -> None:
    builder = TurnContextBuilder(max_chars=10_000)
    builder.add("resume", "RESUME BLOCK", priority=PRIORITY_RESUME)
    builder.add("turn", "TURN BLOCK", priority=PRIORITY_TURN)
    builder.add("memory", "MEMORY BLOCK", priority=PRIORITY_MEMORY)

    built = builder.build("hello agent")

    assert built.text == "RESUME BLOCK\n\nTURN BLOCK\n\nMEMORY BLOCK\n\nUser: hello agent"
    assert built.dropped_labels == []


def test_builder_drops_lowest_priority_blocks_first() -> None:
    builder = TurnContextBuilder(max_chars=60)
    builder.add("resume", "R" * 30, priority=PRIORITY_RESUME)
    builder.add("memory", "M" * 30, priority=PRIORITY_MEMORY)

    built = builder.build("hi")

    assert "R" * 30 in built.text
    assert "M" not in built.text
    assert built.dropped_labels == ["memory"]
    assert built.text.endswith("User: hi")


def test_builder_without_blocks_returns_plain_user_text() -> None:
    built = TurnContextBuilder(max_chars=100).build("just this")
    assert built.text == "just this"


def test_builder_never_drops_user_text() -> None:
    builder = TurnContextBuilder(max_chars=10)
    builder.add("resume", "R" * 50, priority=PRIORITY_RESUME)
    built = builder.build("very long user question here")
    assert "very long user question here" in built.text


# ── Layer 4: memory formatting + tools ───────────────────────


def _fact(text: str, category: str = "general") -> MemoryFact:
    return MemoryFact(
        fact_id="fact_1",
        owner_id="user-1",
        text=text,
        category=category,
        created_at=datetime.now(timezone.utc),
    )


def test_format_memory_block_renders_facts() -> None:
    block = format_memory_block([_fact("Deploys on Cloud Run", "project")])
    assert block.startswith("[USER MEMORY]")
    assert "- (project) Deploys on Cloud Run" in block
    assert block.endswith("[END USER MEMORY]")


def test_format_memory_block_empty_when_no_facts() -> None:
    assert format_memory_block([]) == ""


def test_format_memory_block_respects_budget() -> None:
    facts = [_fact("x" * 100) for _ in range(50)]
    block = format_memory_block(facts, max_chars=300)
    assert len(block) < 400


@pytest.mark.asyncio
async def test_remember_fact_requires_owner(monkeypatch) -> None:
    from nexus.tools import memory as memory_tools
    from nexus.tools._context import set_owner_id

    monkeypatch.setattr(settings, "memory_enabled", True)
    set_owner_id("")
    result = await memory_tools.remember_fact("user likes dark mode")
    assert result["status"] == "error"
    assert result["error_code"] == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_remember_and_recall_roundtrip(monkeypatch) -> None:
    from nexus.tools import memory as memory_tools
    from nexus.tools._context import set_owner_id, set_session_id

    monkeypatch.setattr(settings, "memory_enabled", True)
    set_owner_id("user-1")
    set_session_id("session-1")

    saved: list[dict] = []

    class FakeStore:
        async def add_fact(self, *, owner_id, text, category, session_id):
            saved.append({"owner_id": owner_id, "text": text})
            return MemoryFact(
                fact_id="fact_abc",
                owner_id=owner_id,
                text=text,
                category=category,
                created_at=datetime.now(timezone.utc),
                session_id=session_id,
            )

        async def list_facts(self, *, owner_id, limit):
            return [_fact("Deploys on Cloud Run", "project")]

    monkeypatch.setattr(memory_tools, "get_memory_store", lambda: FakeStore())

    write = await memory_tools.remember_fact("Deploys on Cloud Run", category="project")
    assert write["status"] == "success"
    assert saved[0]["owner_id"] == "user-1"

    read = await memory_tools.recall_facts(limit=5)
    assert read["status"] == "success"
    assert read["metadata"]["facts"][0]["text"] == "Deploys on Cloud Run"


# ── Layer 1: retrieval scoring helpers ───────────────────────


def test_retrieval_chunking_and_scoring() -> None:
    from nexus.tools.retrieval import _chunk_text, _score_chunk, _tokenize

    text = "Alpha pricing details.\n\nBeta feature list.\n\nGamma roadmap."
    chunks = _chunk_text(text)
    assert len(chunks) >= 1

    terms = _tokenize("alpha pricing")
    scores = [_score_chunk(terms, chunk) for chunk in chunks]
    assert max(scores) > 0
    assert _score_chunk(_tokenize("unrelated zebra"), chunks[0]) == 0


# ── Durable event streamer resilience ────────────────────────


@pytest.mark.asyncio
async def test_stream_survives_firestore_index_errors(monkeypatch) -> None:
    import nexus.ws_handler as ws_handler

    class FlakyRepo:
        def __init__(self) -> None:
            self.list_calls = 0
            self.delivered_once = False

        async def list_events(self, **kwargs):
            self.list_calls += 1
            if self.list_calls < 3:
                raise RuntimeError("FAILED_PRECONDITION: query requires an index")
            if self.delivered_once:
                return []
            self.delivered_once = True
            return [
                SimpleNamespace(
                    event_id="evt_1",
                    task_id=kwargs["task_id"],
                    run_id=kwargs.get("run_id"),
                    event_type="agent_complete",
                    seq=1,
                    payload={"summary": "done"},
                )
            ]

        async def get_task(self, task_id):
            return SimpleNamespace(status="completed")

    repo = FlakyRepo()
    delivered: list[dict] = []

    async def _send(frame):
        delivered.append(frame)
        return True

    # Speed up the exponential back-off so the test finishes quickly.
    original_sleep = asyncio.sleep

    async def _fast_sleep(_seconds):
        await original_sleep(0)

    monkeypatch.setattr(ws_handler.asyncio, "sleep", _fast_sleep)

    await asyncio.wait_for(
        ws_handler._stream_durable_task_events(
            repo=repo,
            task_id="task_1",
            owner_id="user-1",
            run_id="run_1",
            send_json=_send,
        ),
        timeout=5.0,
    )

    assert repo.list_calls >= 3
    assert any(frame.get("type") == "agent_complete" for frame in delivered)


@pytest.mark.asyncio
async def test_stream_gives_up_after_too_many_errors(monkeypatch) -> None:
    import nexus.ws_handler as ws_handler

    class BrokenRepo:
        def __init__(self) -> None:
            self.list_calls = 0

        async def list_events(self, **kwargs):
            self.list_calls += 1
            raise RuntimeError("persistent Firestore failure")

        async def get_task(self, task_id):
            return SimpleNamespace(status="completed")

    repo = BrokenRepo()

    async def _send(frame):
        return True

    original_sleep = asyncio.sleep

    async def _fast_sleep(_seconds):
        await original_sleep(0)

    monkeypatch.setattr(ws_handler.asyncio, "sleep", _fast_sleep)

    # Must complete (return) instead of hanging or raising.
    await asyncio.wait_for(
        ws_handler._stream_durable_task_events(
            repo=repo,
            task_id="task_broken",
            owner_id="user-1",
            run_id="run_broken",
            send_json=_send,
        ),
        timeout=5.0,
    )
    assert repo.list_calls == 20


# ── Firestore event query shape (no composite index required) ────


def test_list_events_query_uses_single_field_indexes() -> None:
    """Regression: query must be single-field so Firestore auto-indexes it.

    An earlier version chained ``where(visible) + where(runId) + order_by(seq)``
    which requires a manual composite index and caused a FAILED_PRECONDITION
    crash on the first WS poll.
    """
    from nexus.production_tasks import ProductionTaskRepository

    class TrackingQuery:
        def __init__(self) -> None:
            self.where_calls: list[tuple[str, str]] = []
            self.order_by_fields: list[str] = []
            self.limit_value: int | None = None
            self.streamed = False

        def where(self, *, filter):  # noqa: A002 - mirrors Firestore SDK
            self.where_calls.append((filter.field_path, filter.op_string))
            return self

        def order_by(self, field):
            self.order_by_fields.append(field)
            return self

        def limit(self, value):
            self.limit_value = value
            return self

        def stream(self):
            self.streamed = True
            return iter([])

    tracking = TrackingQuery()

    class Collection:
        def order_by(self, field):
            return tracking.order_by(field)

    class TaskRef:
        def collection(self, name):
            assert name == "events"
            return Collection()

    repo = ProductionTaskRepository.__new__(ProductionTaskRepository)
    repo._task_ref = lambda task_id: TaskRef()  # type: ignore[method-assign]
    repo._get_task_sync = lambda task_id: SimpleNamespace(owner_id="user-1")  # type: ignore[method-assign]
    repo._task_has_seq_field = lambda task_id: True  # type: ignore[method-assign]

    events = repo._list_events_sync(
        task_id="task_1",
        owner_id="user-1",
        after_event_id=None,
        after_seq=5,
        run_id="run_1",
        limit=10,
    )
    assert events == []
    # Only the seq range filter should hit Firestore; visible/runId must be
    # applied client-side.
    assert tracking.where_calls == [("seq", ">")]
    assert tracking.order_by_fields == ["seq"]
    assert tracking.streamed is True


# ── History run ensure (durable → history race) ──────────────


@pytest.mark.asyncio
async def test_ensure_run_creates_missing_history_run() -> None:
    from nexus.history_repository import FirestoreHistoryRepository

    class FakeDoc:
        def __init__(self, data=None, exists=False):
            self._data = data or {}
            self.exists = exists

        def to_dict(self):
            return dict(self._data)

    class FakeRef:
        def __init__(self, store, path):
            self.store = store
            self.path = path

        def collection(self, name):
            return FakeCollection(self.store, f"{self.path}/{name}")

        def document(self, doc_id):
            return FakeRef(self.store, f"{self.path}/{doc_id}")

        def get(self):
            data = self.store.get(self.path)
            return FakeDoc(data, exists=data is not None)

        def set(self, payload, merge=False):
            existing = self.store.get(self.path) or {}
            if merge:
                existing.update(payload)
                self.store[self.path] = existing
            else:
                self.store[self.path] = dict(payload)

    class FakeCollection:
        def __init__(self, store, path):
            self.store = store
            self.path = path

        def document(self, doc_id):
            return FakeRef(self.store, f"{self.path}/{doc_id}")

    class FakeBatch:
        def __init__(self, store):
            self.store = store
            self.ops = []

        def set(self, ref, payload, merge=False):
            self.ops.append((ref, payload, merge))

        def commit(self):
            for ref, payload, merge in self.ops:
                ref.set(payload, merge=merge)

    class FakeDB:
        def __init__(self):
            self.store = {
                "sessions/sess_1": {"ownerId": "user-1", "taskId": "task_abc"},
            }

        def collection(self, name):
            return FakeCollection(self.store, name)

        def batch(self):
            return FakeBatch(self.store)

    class RepoShim:
        def __init__(self):
            self._db = FakeDB()

        def _task_ref(self, owner_id, task_id):
            return FakeRef(self._db.store, f"users/{owner_id}/tasks/{task_id}")

        def _build_stored_run(self, session_id, run_id, payload):
            return SimpleNamespace(
                run_id=run_id,
                session_id=session_id,
                status=payload.get("status"),
                ownerId=payload.get("ownerId"),
                taskId=payload.get("taskId"),
                title=payload.get("title"),
            )

        def _ensure_run_sync(self, *args, **kwargs):
            return FirestoreHistoryRepository._ensure_run_sync(self, *args, **kwargs)

        async def ensure_run(self, **kwargs):
            return await asyncio.to_thread(
                self._ensure_run_sync,
                kwargs["session_id"],
                kwargs["run_id"],
                kwargs["owner_id"],
                kwargs.get("title", "Agent Turn"),
                kwargs.get("task_id"),
                kwargs.get("status", "queued"),
            )

    shim = RepoShim()
    run = await shim.ensure_run(
        session_id="sess_1",
        run_id="run_durable_1",
        owner_id="user-1",
        title="Work",
        task_id="task_abc",
        status="queued",
    )
    assert run.run_id == "run_durable_1"
    assert "sessions/sess_1/runs/run_durable_1" in shim._db.store

    again = await shim.ensure_run(
        session_id="sess_1",
        run_id="run_durable_1",
        owner_id="user-1",
    )
    assert again.run_id == "run_durable_1"


def test_sandbox_resume_delegates_to_connect(monkeypatch) -> None:
    from nexus.sandbox import SandboxManager

    manager = SandboxManager(e2b_api_key="test")
    called = {}

    def fake_connect(sandbox_id):
        called["id"] = sandbox_id
        return {"sandbox_id": sandbox_id, "stream_url": "https://vnc.example"}

    monkeypatch.setattr(manager, "connect", fake_connect)
    result = manager.resume("sbx_123")
    assert called["id"] == "sbx_123"
    assert result["stream_url"] == "https://vnc.example"


def test_reserved_routing_models(monkeypatch) -> None:
    # Fast path was removed in the full-agent-only migration
    # (docs/FULL_AGENT_ONLY_MIGRATION_PLAN.md). These settings are reserved
    # for the optional Phase B turn-budget classifier.
    assert bool(settings.routing_model)
    assert bool(settings.routing_fallback_model)
    assert "gemini" not in settings.routing_model.lower()


def test_jwt_secret_at_least_32_bytes() -> None:
    assert len(settings.jwt_secret.encode("utf-8")) >= 32


# ── Durable ask_user answers ─────────────────────────────────


@pytest.mark.asyncio
async def test_await_question_answer_resolves_from_durable_events(monkeypatch) -> None:
    from nexus.orchestrator import NexusOrchestrator

    monkeypatch.setattr(settings, "ask_user_timeout_seconds", 5.0)

    class FakeRepo:
        async def list_events(self, *, task_id, owner_id, after_seq=0, limit=100, **kwargs):
            return [
                SimpleNamespace(
                    seq=1,
                    event_type="user_question_response",
                    payload={"question_id": "q_1", "answer": "blue"},
                )
            ]

    orchestrator = NexusOrchestrator.__new__(NexusOrchestrator)
    orchestrator._durable_task_id = "task_1"
    orchestrator.production_task_repository = FakeRepo()
    orchestrator.session = SimpleNamespace(owner_id="user-1", id="session-1")

    future: asyncio.Future = asyncio.get_running_loop().create_future()
    answer = await asyncio.wait_for(
        orchestrator._await_question_answer("q_1", future), timeout=4.0
    )
    assert answer == "blue"


@pytest.mark.asyncio
async def test_await_question_answer_uses_live_future_without_durable(monkeypatch) -> None:
    from nexus.orchestrator import NexusOrchestrator

    monkeypatch.setattr(settings, "ask_user_timeout_seconds", 2.0)

    orchestrator = NexusOrchestrator.__new__(NexusOrchestrator)
    orchestrator._durable_task_id = None
    orchestrator.production_task_repository = None
    orchestrator.session = SimpleNamespace(owner_id="user-1", id="session-1")

    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()
    loop.call_later(0.05, future.set_result, "green")

    answer = await orchestrator._await_question_answer("q_2", future)
    assert answer == "green"
