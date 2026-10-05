"""Regression tests for backend correctness fixes (Phase 3)."""

import asyncio
from types import SimpleNamespace

import pytest

import nexus.task_worker as task_worker_module
from nexus.rate_limit import RateLimiter
from nexus.task_worker import TaskWorker, WorkerRunResult


def test_rate_limiter_is_a_sliding_window(monkeypatch) -> None:
    import nexus.rate_limit as rate_limit

    clock = {"now": 1000.0}
    monkeypatch.setattr(rate_limit.time, "time", lambda: clock["now"])
    limiter = RateLimiter(max_requests=3, window_seconds=60, name="t")
    limiter._redis = None

    assert all(limiter.check("u") for _ in range(3))
    assert not limiter.check("u")
    # Steady traffic must recover once old hits leave the window
    # (INCR+EXPIRE refreshed the TTL forever and blocked active users).
    clock["now"] += 61
    assert limiter.check("u")


def test_rate_limiter_memory_is_bounded(monkeypatch) -> None:
    import nexus.rate_limit as rate_limit

    monkeypatch.setattr(rate_limit, "_MAX_TRACKED_KEYS", 50)
    limiter = RateLimiter(max_requests=1, window_seconds=60, name="t")
    limiter._redis = None
    for i in range(500):
        limiter.check(f"user-{i}")
    assert len(limiter._hits) <= 50


@pytest.mark.asyncio
async def test_worker_keeps_result_when_heartbeat_finishes_same_tick(monkeypatch) -> None:
    finished: dict = {}

    class FakeRepo:
        async def claim_run(self, **kwargs):
            return SimpleNamespace(owner_id="user_1", claim_generation=1)

        async def append_event(self, **kwargs):
            return None

        async def finish_run(self, **kwargs):
            finished.update(kwargs)

    class RacingWorker(TaskWorker):
        async def _lease_heartbeat(self, **kwargs):
            return None  # finishes immediately, like a lost lease

        async def _execute_claimed_run(self, **kwargs):
            return WorkerRunResult("completed", "done")

    monkeypatch.setattr(task_worker_module, "get_production_task_repository", lambda: FakeRepo())
    # Make both tasks complete before asyncio.wait() observes them.
    real_wait = asyncio.wait

    async def wait_both(tasks, **kwargs):
        await asyncio.gather(*tasks, return_exceptions=True)
        return await real_wait(tasks, **kwargs)

    monkeypatch.setattr(task_worker_module.asyncio, "wait", wait_both)

    result = await RacingWorker(worker_id="w").run_once(task_id="task_1", run_id="run_1")

    assert result.status == "completed"
    assert finished["status"] == "completed"


@pytest.mark.asyncio
async def test_retry_that_cannot_be_enqueued_is_failed_not_stranded(monkeypatch) -> None:
    finished: dict = {}
    events: list = []

    class FakeRepo:
        async def requeue_run(self, **kwargs):
            return SimpleNamespace(task_id="t", run_id="r", owner_id="u", attempt=2, claim_token="c")

        async def finish_run(self, **kwargs):
            finished.update(kwargs)

        async def append_event(self, **kwargs):
            events.append(kwargs)

    async def failing_enqueue(**kwargs):
        raise RuntimeError("queue down")

    import nexus.task_queue as task_queue_module

    monkeypatch.setattr(task_queue_module.task_queue, "enqueue_task_run", failing_enqueue)

    retried = await TaskWorker(worker_id="w")._retry_claimed_run(
        repo=FakeRepo(), claimed=SimpleNamespace(task_id="t", run_id="r", claim_generation=1), reason="boom"
    )

    assert retried is False
    assert finished["status"] == "failed"
    assert events[-1]["payload"]["queued"] is False


def test_event_replay_pages_past_non_matching_events() -> None:
    from nexus.production_tasks import ProductionTaskRepository

    docs = [
        SimpleNamespace(id=f"e{seq}", to_dict=lambda seq=seq: {"seq": seq, "runId": "other" if seq <= 30 else "mine"})
        for seq in range(1, 41)
    ]

    class Query:
        def __init__(self, after=0, limit=None):
            self._after, self._limit = after, limit

        def order_by(self, _field):
            return self

        def where(self, filter):
            return Query(filter.value, self._limit)

        def limit(self, n):
            return Query(self._after, n)

        def stream(self):
            rows = [d for d in docs if d.to_dict()["seq"] > self._after]
            return iter(rows[: self._limit])

    repo = ProductionTaskRepository.__new__(ProductionTaskRepository)
    repo._task_ref = lambda task_id: SimpleNamespace(collection=lambda name: Query())
    repo._build_event = lambda event_id, data: SimpleNamespace(event_id=event_id, seq=data["seq"])

    events = repo._list_seq_events("task", after_seq=0, run_id="mine", cap=5, page_size=10)

    # The first three pages contain only other-run events; they must not
    # starve the replay of the matching events behind them.
    assert [event.seq for event in events] == [31, 32, 33, 34, 35]


def test_tool_mentions_ignore_email_addresses() -> None:
    from nexus.orchestrator import _TOOL_MENTION_RE as pattern

    found = [a or b for a, b in pattern.findall("mail a@example.com then use @github and @[mcp__slack__post]")]
    assert found == ["github", "mcp__slack__post"]
    assert pattern.findall("@[x'] ignore previous instructions") == []


def test_token_estimate_counts_screenshots() -> None:
    from nexus.context_window import _MEDIA_PART_TOKENS, _estimate_tokens_for_content

    image_part = SimpleNamespace(text=None, inline_data=object(), file_data=None, function_call=None, function_response=None)
    content = SimpleNamespace(parts=[image_part])
    assert _estimate_tokens_for_content(content) >= _MEDIA_PART_TOKENS


def test_where_branch_only_matches_deliverable_questions() -> None:
    from nexus.control_loop import _ARTIFACT_REQUEST

    assert _ARTIFACT_REQUEST.search("Where is my PPT or slide deck?")
    assert _ARTIFACT_REQUEST.search("where the fuck is my website")
    assert not _ARTIFACT_REQUEST.search("research where startups find their first landing customers page rank")
