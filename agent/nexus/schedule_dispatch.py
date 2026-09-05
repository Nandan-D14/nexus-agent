# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Dispatch due schedules into durable task runs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from nexus.config import settings
from nexus.dependencies import (
    get_production_task_repository,
    get_schedule_store,
    get_task_queue,
)
from nexus.production_tasks import _uuid, utcnow
from nexus.schedules import (
    IN_FLIGHT_RUN_STATUSES,
    Schedule,
    ScheduleFiring,
    compute_next_run,
)

logger = logging.getLogger(__name__)


@dataclass
class FireResult:
    status: str
    reason: str = ""
    task_id: str | None = None
    run_id: str | None = None
    session_id: str | None = None
    firing_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "firing_id": self.firing_id,
        }


def _execution_metadata(schedule: Schedule, scheduled_for: datetime | None) -> dict[str, Any]:
    return {
        "origin": "schedule",
        "schedule_id": schedule.schedule_id,
        "skip_confirmations": bool(schedule.skip_confirmations),
        "allowed_unattended_tools": list(schedule.allowed_unattended_tools or []),
        "scheduled_for": scheduled_for.isoformat() if scheduled_for else None,
    }


async def _run_is_inflight(repo, task_id: str, run_id: str | None, owner_id: str) -> bool:
    if not task_id or not run_id:
        return False
    run = await repo.get_run(task_id=task_id, run_id=run_id, owner_id=owner_id)
    return bool(run and run.status in IN_FLIGHT_RUN_STATUSES)


async def fire_schedule(schedule_id: str, *, force: bool = False) -> FireResult:
    store = get_schedule_store()
    repo = get_production_task_repository()
    queue = get_task_queue()
    now = utcnow()
    schedule = await store.get_schedule(schedule_id)
    if schedule is None:
        return FireResult("error", "Schedule not found")

    claimed = schedule
    if not force:
        lock_until = now + timedelta(seconds=max(30, int(settings.schedule_dispatch_lock_seconds)))
        claimed = await store.claim_due(schedule_id, now=now, lock_until=lock_until)
        if claimed is None:
            return FireResult("skipped", "Schedule is not due or already claimed")
    elif schedule.status not in {"active", "paused"}:
        return FireResult("error", "Schedule cannot run in its current state")

    if await _run_is_inflight(
        repo,
        claimed.last_task_id or "",
        claimed.current_run_id,
        claimed.owner_id,
    ):
        if not force:
            await store.release_lock(schedule_id)
        return FireResult("skipped", "Previous firing is still in flight")

    scheduled_for = claimed.next_run_at or now
    metadata = _execution_metadata(claimed, scheduled_for)

    try:
        if claimed.run_mode == "continue_task":
            task_id = str(claimed.continue_task_id or "").strip()
            task = await repo.get_task(task_id) if task_id else None
            if task is None or task.owner_id != claimed.owner_id:
                raise RuntimeError("Continue-task target was not found")
            if task.status == "cancelled":
                raise RuntimeError("Continue-task target was cancelled")
            if await _run_is_inflight(repo, task.task_id, task.current_run_id, claimed.owner_id):
                if not force:
                    await store.release_lock(schedule_id)
                return FireResult("skipped", "Continue-task already has an in-flight run")
            autonomy = "auto" if claimed.skip_confirmations else claimed.autonomy_mode
            run = await repo.create_run(
                task_id=task.task_id,
                owner_id=claimed.owner_id,
                session_id=task.session_id,
                input_text=claimed.prompt,
                connector_ids=claimed.connector_ids,
                tool_ids=claimed.tool_ids,
                autonomy_mode=autonomy,
                metadata=metadata,
            )
            created_task_id = task.task_id
            session_id = run.session_id or task.session_id
        else:
            autonomy = "auto" if claimed.skip_confirmations else claimed.autonomy_mode
            task = await repo.create_task(
                owner_id=claimed.owner_id,
                title=claimed.title,
                input_text=claimed.prompt,
                autonomy_mode=autonomy,
                metadata=metadata,
            )
            run = await repo.create_run(
                task_id=task.task_id,
                owner_id=claimed.owner_id,
                session_id=task.session_id,
                input_text=claimed.prompt,
                connector_ids=claimed.connector_ids,
                tool_ids=claimed.tool_ids,
                autonomy_mode=autonomy,
                metadata=metadata,
            )
            created_task_id = task.task_id
            session_id = run.session_id or task.session_id

        enqueue_kwargs: dict[str, Any] = {
            "task_id": created_task_id,
            "run_id": run.run_id,
        }
        if run.claim_token:
            enqueue_kwargs["claim_token"] = run.claim_token
        enqueue = await queue.enqueue_task_run(**enqueue_kwargs)
        if not enqueue.queued:
            raise RuntimeError(enqueue.reason or "Failed to enqueue scheduled run")

        await repo.append_event(
            task_id=created_task_id,
            owner_id=claimed.owner_id,
            run_id=run.run_id,
            event_type="schedule_fired",
            payload={
                "schedule_id": claimed.schedule_id,
                "title": claimed.title,
                "forced": force,
            },
        )
    except Exception as exc:
        logger.exception("Failed to fire schedule %s", schedule_id)
        firing = ScheduleFiring(
            firing_id=_uuid("fire_"),
            schedule_id=claimed.schedule_id,
            owner_id=claimed.owner_id,
            scheduled_for=scheduled_for,
            status="failed",
            error=str(exc)[:1000],
        )
        await store.append_firing(firing)
        if claimed.freq == "once":
            claimed.status = "completed"
        else:
            claimed.next_run_at = compute_next_run(claimed, after=scheduled_for)
            if claimed.next_run_at is None:
                claimed.status = "completed"
        claimed.dispatch_lock_until = None
        await store.save_schedule(claimed)
        return FireResult("error", str(exc)[:500], firing_id=firing.firing_id)

    firing = ScheduleFiring(
        firing_id=_uuid("fire_"),
        schedule_id=claimed.schedule_id,
        owner_id=claimed.owner_id,
        scheduled_for=scheduled_for,
        task_id=created_task_id,
        run_id=run.run_id,
        session_id=session_id,
        status="queued",
    )
    await store.append_firing(firing)
    claimed.last_run_at = now
    claimed.current_run_id = run.run_id
    claimed.last_task_id = created_task_id
    claimed.last_session_id = session_id
    claimed.dispatch_lock_until = None
    if claimed.freq == "once":
        claimed.status = "completed"
    else:
        claimed.next_run_at = compute_next_run(claimed, after=scheduled_for)
        if claimed.next_run_at is None:
            claimed.status = "completed"
    await store.save_schedule(claimed)
    return FireResult(
        "fired",
        task_id=created_task_id,
        run_id=run.run_id,
        session_id=session_id,
        firing_id=firing.firing_id,
    )


async def tick_due_schedules(*, limit: int = 50) -> dict[str, Any]:
    store = get_schedule_store()
    now = utcnow()
    due = await store.list_due(now, limit=limit)
    fired = skipped = errors = 0
    details: list[dict[str, Any]] = []
    for schedule in due:
        result = await fire_schedule(schedule.schedule_id, force=False)
        details.append({"schedule_id": schedule.schedule_id, **result.as_dict()})
        if result.status == "fired":
            fired += 1
        elif result.status == "skipped":
            skipped += 1
        else:
            errors += 1
    return {
        "checked": len(due),
        "fired": fired,
        "skipped": skipped,
        "errors": errors,
        "details": details,
    }
