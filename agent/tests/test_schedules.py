# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from nexus.policy import evaluate_tool_policy
from nexus.schedule_ticker import ScheduleTicker
from nexus.schedules import compute_next_run, next_run_at, sanitize_unattended_tools
from nexus.tools.parallel import is_parallelizable


def test_next_run_weekday_in_kolkata() -> None:
    after = datetime(2026, 9, 3, 18, 0, tzinfo=timezone.utc)  # Thursday evening UTC
    nxt = next_run_at(
        freq="weekdays",
        timezone_name="Asia/Kolkata",
        time_of_day="09:00",
        after=after,
    )
    assert nxt is not None
    local = nxt.astimezone(timezone.utc)
    assert nxt.tzinfo is not None
    assert local.hour == 3 or nxt.astimezone().utcoffset() is not None
    from zoneinfo import ZoneInfo

    local_time = nxt.astimezone(ZoneInfo("Asia/Kolkata"))
    assert local_time.hour == 9
    assert local_time.weekday() < 5


def test_next_run_monthly_and_once() -> None:
    after = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    monthly = next_run_at(
        freq="monthly",
        timezone_name="UTC",
        time_of_day="09:00",
        day_of_month=1,
        after=after,
    )
    assert monthly is not None
    assert monthly.day == 1
    assert monthly.month == 2

    past = next_run_at(
        freq="once",
        timezone_name="UTC",
        once_at=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc),
        after=after,
    )
    assert past is None

    future = next_run_at(
        freq="once",
        timezone_name="UTC",
        once_at=datetime(2026, 2, 1, 9, 0, tzinfo=timezone.utc),
        after=after,
    )
    assert future == datetime(2026, 2, 1, 9, 0, tzinfo=timezone.utc)


def test_sanitize_unattended_tools_drops_dangerous_names() -> None:
    assert sanitize_unattended_tools(["gmail_send", "github_push", "gmail_send", "nope"]) == [
        "gmail_send"
    ]


def test_gmail_send_stays_gated_without_allowlist() -> None:
    decision = evaluate_tool_policy("gmail_send", {}, autonomy_mode="auto")
    assert decision.action == "require_approval"


def test_gmail_send_allowed_with_unattended_allowlist() -> None:
    decision = evaluate_tool_policy(
        "gmail_send",
        {},
        autonomy_mode="auto",
        allowed_unattended_tools={"gmail_send"},
    )
    assert decision.action == "allow"


def test_github_push_never_unattended() -> None:
    decision = evaluate_tool_policy(
        "github_push",
        {},
        autonomy_mode="auto",
        allowed_unattended_tools={"github_push", "gmail_send"},
    )
    assert decision.action == "require_approval"


def test_schedules_create_requires_approval() -> None:
    decision = evaluate_tool_policy("schedules_create", {"title": "x"}, autonomy_mode="auto")
    assert decision.action == "require_approval"


def test_schedule_tools_parallel_flags() -> None:
    assert is_parallelizable("schedules_list") is True
    assert is_parallelizable("schedules_create") is False
    assert is_parallelizable("schedules_pause") is False


@pytest.mark.asyncio
async def test_tick_is_idempotent_for_locked_schedule(monkeypatch) -> None:
    from nexus import schedule_dispatch

    now = datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc)
    schedule = SimpleNamespace(
        schedule_id="sched_1",
        owner_id="user-1",
        title="Digest",
        prompt="Summarize news",
        status="active",
        freq="daily",
        time_of_day="09:00",
        timezone="UTC",
        days_of_week=[],
        once_at=None,
        day_of_month=1,
        next_run_at=now,
        last_run_at=None,
        run_mode="new_task",
        continue_task_id=None,
        connector_ids=[],
        tool_ids=[],
        autonomy_mode="manual",
        skip_confirmations=False,
        allowed_unattended_tools=[],
        current_run_id=None,
        last_task_id=None,
        last_session_id=None,
        dispatch_lock_until=now,
        metadata={},
    )

    store = MagicMock()
    store.list_due = AsyncMock(return_value=[schedule])
    store.get_schedule = AsyncMock(return_value=schedule)
    store.claim_due = AsyncMock(return_value=None)
    store.release_lock = AsyncMock()
    store.append_firing = AsyncMock()
    store.save_schedule = AsyncMock()

    monkeypatch.setattr(schedule_dispatch, "get_schedule_store", lambda: store)
    monkeypatch.setattr(schedule_dispatch, "get_production_task_repository", lambda: MagicMock())
    monkeypatch.setattr(schedule_dispatch, "get_task_queue", lambda: MagicMock())
    monkeypatch.setattr(schedule_dispatch, "utcnow", lambda: now)

    first = await schedule_dispatch.tick_due_schedules()
    second = await schedule_dispatch.tick_due_schedules()
    assert first["fired"] == 0
    assert first["skipped"] == 1
    assert second["skipped"] == 1
    store.save_schedule.assert_not_called()


@pytest.mark.asyncio
async def test_continue_task_skips_when_inflight(monkeypatch) -> None:
    from nexus import schedule_dispatch
    from nexus.schedules import Schedule

    now = datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc)
    schedule = Schedule(
        schedule_id="sched_2",
        owner_id="user-1",
        title="Follow-up",
        prompt="Continue the research",
        next_run_at=now,
        status="active",
        run_mode="continue_task",
        continue_task_id="task_abc",
    )
    store = MagicMock()
    store.get_schedule = AsyncMock(return_value=schedule)
    store.claim_due = AsyncMock(return_value=schedule)
    store.release_lock = AsyncMock()

    repo = MagicMock()
    repo.get_task = AsyncMock(
        return_value=SimpleNamespace(
            task_id="task_abc",
            owner_id="user-1",
            status="running",
            session_id="sess_1",
            current_run_id="run_live",
        )
    )
    repo.get_run = AsyncMock(return_value=SimpleNamespace(status="running"))

    monkeypatch.setattr(schedule_dispatch, "get_schedule_store", lambda: store)
    monkeypatch.setattr(schedule_dispatch, "get_production_task_repository", lambda: repo)
    monkeypatch.setattr(schedule_dispatch, "get_task_queue", lambda: MagicMock())
    monkeypatch.setattr(schedule_dispatch, "utcnow", lambda: now)

    result = await schedule_dispatch.fire_schedule("sched_2")
    assert result.status == "skipped"
    store.release_lock.assert_awaited()


@pytest.mark.asyncio
async def test_local_ticker_does_not_start_in_production(monkeypatch) -> None:
    from nexus.config import settings

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "task_worker_enabled", True)
    ticker = ScheduleTicker()
    await ticker.start()
    assert ticker._running is False
    assert ticker._task is None


@pytest.mark.asyncio
async def test_fire_new_task_enqueues_run(monkeypatch) -> None:
    from nexus import schedule_dispatch
    from nexus.schedules import Schedule

    now = datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc)
    schedule = Schedule(
        schedule_id="sched_fire",
        owner_id="user-1",
        title="Digest",
        prompt="Summarize news",
        next_run_at=now,
        status="active",
        freq="daily",
        timezone="UTC",
        time_of_day="09:00",
        skip_confirmations=True,
        allowed_unattended_tools=["gmail_send"],
    )
    store = MagicMock()
    store.get_schedule = AsyncMock(return_value=schedule)
    store.claim_due = AsyncMock(return_value=schedule)
    store.append_firing = AsyncMock()
    store.save_schedule = AsyncMock()

    created_task = SimpleNamespace(task_id="task_new", session_id="sess_new", owner_id="user-1")
    created_run = SimpleNamespace(run_id="run_new", session_id="sess_new", claim_token="claim_1")
    repo = MagicMock()
    repo.create_task = AsyncMock(return_value=created_task)
    repo.create_run = AsyncMock(return_value=created_run)
    repo.append_event = AsyncMock()
    repo.get_run = AsyncMock(return_value=None)

    queue = MagicMock()
    queue.enqueue_task_run = AsyncMock(return_value=SimpleNamespace(queued=True, reason=""))

    monkeypatch.setattr(schedule_dispatch, "get_schedule_store", lambda: store)
    monkeypatch.setattr(schedule_dispatch, "get_production_task_repository", lambda: repo)
    monkeypatch.setattr(schedule_dispatch, "get_task_queue", lambda: queue)
    monkeypatch.setattr(schedule_dispatch, "utcnow", lambda: now)

    result = await schedule_dispatch.fire_schedule("sched_fire")
    assert result.status == "fired"
    assert result.task_id == "task_new"
    metadata = repo.create_run.await_args.kwargs["metadata"]
    assert metadata["skip_confirmations"] is True
    assert metadata["allowed_unattended_tools"] == ["gmail_send"]
    queue.enqueue_task_run.assert_awaited()
    store.save_schedule.assert_awaited()
    saved = store.save_schedule.await_args.args[0]
    assert saved.last_task_id == "task_new"
    assert saved.status == "active"
    assert saved.next_run_at is not None
    assert saved.next_run_at > now


def test_slack_mcp_post_allowed_when_slack_post_unattended() -> None:
    decision = evaluate_tool_policy(
        "mcp__slack__chat_postMessage",
        {},
        autonomy_mode="auto",
        allowed_unattended_tools={"slack_post"},
    )
    assert decision.action == "allow"


def test_compute_next_run_defaults_weekly_day() -> None:
    from nexus.schedules import Schedule

    schedule = Schedule(
        schedule_id="sched_3",
        owner_id="u",
        title="Weekly",
        prompt="ping",
        freq="weekly",
        timezone="UTC",
        time_of_day="10:00",
        days_of_week=[],
    )
    after = datetime(2026, 9, 2, 0, 0, tzinfo=timezone.utc)  # Wednesday
    nxt = compute_next_run(schedule, after=after)
    assert nxt is not None
    assert nxt.weekday() == after.weekday()


def test_schedule_store_list_schedules_index_fallback() -> None:
    from nexus.repositories.schedule_store import ScheduleStore

    mock_db = MagicMock()
    ordered_query = MagicMock()
    ordered_query.stream.side_effect = Exception("400 The query requires an index.")

    doc1 = MagicMock()
    doc1.id = "s1"
    doc1.to_dict.return_value = {
        "scheduleId": "s1",
        "ownerId": "u1",
        "title": "S1",
        "prompt": "p1",
        "nextRunAt": datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc),
    }
    doc2 = MagicMock()
    doc2.id = "s2"
    doc2.to_dict.return_value = {
        "scheduleId": "s2",
        "ownerId": "u1",
        "title": "S2",
        "prompt": "p2",
        "nextRunAt": datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc),
    }

    query_mock = MagicMock()
    query_mock.order_by.return_value.limit.return_value = ordered_query
    query_mock.stream.return_value = [doc1, doc2]
    mock_db.collection.return_value.where.return_value = query_mock

    store = ScheduleStore(db=mock_db)
    results = store._list_schedules_sync("u1", 10)
    assert len(results) == 2
    # Should fall back to in-memory sort with s2 earlier than s1
    assert results[0].schedule_id == "s2"
    assert results[1].schedule_id == "s1"

