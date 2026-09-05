# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Tools for creating and managing scheduled agent jobs."""

from __future__ import annotations

from typing import Any

from nexus.dependencies import get_schedule_store
from nexus.production_tasks import utcnow
from nexus.repositories.schedule_store import build_schedule_from_input
from nexus.schedules import compute_next_run, schedule_payload
from nexus.tools._context import get_owner_id
from nexus.tools.base import normalized_tool, tool_error, tool_success


def _owner_or_error() -> str | dict[str, Any]:
    try:
        return get_owner_id()
    except Exception:
        return tool_error(
            "No authenticated user in the current tool context.",
            error_code="AUTH_REQUIRED",
        )


@normalized_tool
async def schedules_create(
    title: str,
    prompt: str,
    freq: str = "daily",
    time_of_day: str = "09:00",
    timezone: str = "UTC",
    days_of_week: str = "",
    once_at: str | None = None,
    day_of_month: int = 1,
    run_mode: str = "new_task",
    continue_task_id: str = "",
    skip_confirmations: bool = False,
    allowed_unattended_tools: str = "",
) -> dict[str, Any]:
    """Create a standing scheduled agent job.

    Use this for recurring or delayed CoComputer work such as "every weekday at
    9 AM, summarize AI news". Do not use Google Calendar for this.

    Args:
        title: Short name for the schedule.
        prompt: Standing instruction the agent should follow on each run.
        freq: once, daily, weekdays, weekly, monthly, or custom.
        time_of_day: Local time HH:MM (ignored for one-shot when once_at is set).
        timezone: IANA timezone, e.g. Asia/Kolkata.
        days_of_week: Comma-separated Python weekdays 0=Monday ... 6=Sunday.
        once_at: RFC 3339 timestamp for a one-time run.
        day_of_month: Day of month for monthly schedules.
        run_mode: new_task or continue_task.
        continue_task_id: Durable task id when run_mode is continue_task.
        skip_confirmations: If true, allow the listed unattended tools.
        allowed_unattended_tools: Comma-separated tools from
            gmail_send,create_drive_doc,create_drive_sheet,upload_drive_file,tasks_create,slack_post.
    """
    owner = _owner_or_error()
    if isinstance(owner, dict):
        return owner
    days = [int(part.strip()) for part in days_of_week.split(",") if part.strip().isdigit()]
    allowed = [part.strip() for part in allowed_unattended_tools.split(",") if part.strip()]
    store = get_schedule_store()
    try:
        from nexus.config import settings

        active = await store.count_active(owner)
        if active >= settings.max_active_schedules:
            return tool_error(
                f"Active schedule limit reached ({settings.max_active_schedules}).",
                error_code="INVALID_INPUT",
            )
        schedule = build_schedule_from_input(
            owner_id=owner,
            title=title,
            prompt=prompt,
            timezone_name=timezone,
            freq=freq,
            time_of_day=time_of_day,
            days_of_week=days,
            once_at=once_at,
            day_of_month=day_of_month,
            run_mode=run_mode,
            continue_task_id=continue_task_id or None,
            skip_confirmations=skip_confirmations,
            allowed_unattended_tools=allowed,
        )
        created = await store.create_schedule(schedule)
    except ValueError as exc:
        return tool_error(str(exc), error_code="INVALID_INPUT")
    except Exception as exc:
        return tool_error(f"Failed to create schedule: {exc}")
    payload = schedule_payload(created)
    return tool_success(
        f"Scheduled '{created.title}' ({created.freq}) next {payload.get('next_run_at')}",
        schedule=payload,
    )


@normalized_tool
async def schedules_list() -> dict[str, Any]:
    """List the current user's scheduled agent jobs."""
    owner = _owner_or_error()
    if isinstance(owner, dict):
        return owner
    store = get_schedule_store()
    rows = await store.list_schedules(owner, limit=100)
    payloads = [schedule_payload(item) for item in rows]
    return tool_success(
        f"Listed {len(payloads)} schedules",
        schedules=payloads,
        schedule_count=len(payloads),
    )


@normalized_tool
async def schedules_pause(schedule_id: str, resume: bool = False) -> dict[str, Any]:
    """Pause or resume a scheduled agent job.

    Args:
        schedule_id: The schedule to update.
        resume: If true, resume the schedule instead of pausing it.
    """
    owner = _owner_or_error()
    if isinstance(owner, dict):
        return owner
    store = get_schedule_store()
    schedule = await store.get_schedule(schedule_id)
    if not schedule or schedule.owner_id != owner:
        return tool_error("Schedule not found.", error_code="NOT_FOUND")
    if resume:
        schedule.status = "active"
        nxt = compute_next_run(schedule, after=utcnow())
        if nxt is None:
            return tool_error("Schedule has no upcoming run time.", error_code="INVALID_INPUT")
        schedule.next_run_at = nxt
        saved = await store.save_schedule(schedule)
        return tool_success(f"Resumed '{saved.title}'", schedule=schedule_payload(saved))
    schedule.status = "paused"
    saved = await store.save_schedule(schedule)
    return tool_success(f"Paused '{saved.title}'", schedule=schedule_payload(saved))
