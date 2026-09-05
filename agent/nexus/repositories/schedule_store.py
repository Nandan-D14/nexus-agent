# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Firestore store for Manus-style schedule definitions and firings."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from firebase_admin import firestore
from google.cloud.firestore_v1 import FieldFilter

from nexus.firebase import get_firestore_client
from nexus.policy import normalize_autonomy_mode
from nexus.production_tasks import _uuid, utcnow
from nexus.schedules import (
    RUN_MODES,
    SCHEDULE_FREQS,
    SCHEDULE_STATUSES,
    Schedule,
    ScheduleFiring,
    compute_next_run,
    parse_datetime,
    resolve_zone,
    sanitize_unattended_tools,
)

logger = logging.getLogger(__name__)


def _clean_ids(values: list[Any] | None) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in values or []:
        val = str(item).strip()
        if not val or val in seen:
            continue
        seen.add(val)
        cleaned.append(val)
    return cleaned


def _clean_days(values: list[Any] | None) -> list[int]:
    days: list[int] = []
    seen: set[int] = set()
    for item in values or []:
        try:
            day = int(item)
        except (TypeError, ValueError):
            continue
        if day < 0 or day > 6 or day in seen:
            continue
        seen.add(day)
        days.append(day)
    return days


class ScheduleStore:
    def __init__(self, db: Any = None) -> None:
        self._custom_db = db

    @property
    def _db(self):
        if self._custom_db is not None:
            return self._custom_db
        return get_firestore_client()

    def _schedule_ref(self, schedule_id: str):
        return self._db.collection("schedules").document(schedule_id)

    def _firing_ref(self, schedule_id: str, firing_id: str):
        return self._schedule_ref(schedule_id).collection("firings").document(firing_id)

    @staticmethod
    def _build_schedule(schedule_id: str, data: dict[str, Any]) -> Schedule:
        freq = str(data.get("freq") or "daily").strip().lower()
        if freq not in SCHEDULE_FREQS:
            freq = "daily"
        status = str(data.get("status") or "active").strip().lower()
        if status not in SCHEDULE_STATUSES:
            status = "active"
        run_mode = str(data.get("runMode") or "new_task").strip().lower()
        if run_mode not in RUN_MODES:
            run_mode = "new_task"
        continue_task_id = data.get("continueTaskId")
        return Schedule(
            schedule_id=schedule_id,
            owner_id=str(data.get("ownerId") or ""),
            title=str(data.get("title") or "Untitled schedule"),
            prompt=str(data.get("prompt") or ""),
            timezone=str(data.get("timezone") or "UTC"),
            freq=freq,
            time_of_day=str(data.get("timeOfDay") or "09:00"),
            days_of_week=_clean_days(data.get("daysOfWeek") if isinstance(data.get("daysOfWeek"), list) else []),
            once_at=parse_datetime(data.get("onceAt")),
            day_of_month=int(data.get("dayOfMonth") or 1),
            next_run_at=parse_datetime(data.get("nextRunAt")),
            last_run_at=parse_datetime(data.get("lastRunAt")),
            status=status,
            run_mode=run_mode,
            continue_task_id=continue_task_id if isinstance(continue_task_id, str) and continue_task_id.strip() else None,
            connector_ids=_clean_ids(data.get("connectorIds") if isinstance(data.get("connectorIds"), list) else []),
            tool_ids=_clean_ids(data.get("toolIds") if isinstance(data.get("toolIds"), list) else []),
            autonomy_mode=normalize_autonomy_mode(str(data.get("autonomyMode") or "manual")),
            skip_confirmations=bool(data.get("skipConfirmations")),
            allowed_unattended_tools=sanitize_unattended_tools(
                data.get("allowedUnattendedTools") if isinstance(data.get("allowedUnattendedTools"), list) else []
            ),
            current_run_id=data.get("currentRunId") if isinstance(data.get("currentRunId"), str) else None,
            last_task_id=data.get("lastTaskId") if isinstance(data.get("lastTaskId"), str) else None,
            last_session_id=data.get("lastSessionId") if isinstance(data.get("lastSessionId"), str) else None,
            dispatch_lock_until=parse_datetime(data.get("dispatchLockUntil")),
            created_at=parse_datetime(data.get("createdAt")),
            updated_at=parse_datetime(data.get("updatedAt")),
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
        )

    @staticmethod
    def _build_firing(firing_id: str, data: dict[str, Any]) -> ScheduleFiring:
        return ScheduleFiring(
            firing_id=firing_id,
            schedule_id=str(data.get("scheduleId") or ""),
            owner_id=str(data.get("ownerId") or ""),
            scheduled_for=parse_datetime(data.get("scheduledFor")),
            task_id=data.get("taskId") if isinstance(data.get("taskId"), str) else None,
            run_id=data.get("runId") if isinstance(data.get("runId"), str) else None,
            session_id=data.get("sessionId") if isinstance(data.get("sessionId"), str) else None,
            status=str(data.get("status") or "queued"),
            error=data.get("error") if isinstance(data.get("error"), str) else None,
            created_at=parse_datetime(data.get("createdAt")),
        )

    def _to_doc(self, schedule: Schedule) -> dict[str, Any]:
        return {
            "scheduleId": schedule.schedule_id,
            "ownerId": schedule.owner_id,
            "title": schedule.title,
            "prompt": schedule.prompt,
            "timezone": schedule.timezone,
            "freq": schedule.freq,
            "timeOfDay": schedule.time_of_day,
            "daysOfWeek": list(schedule.days_of_week),
            "onceAt": schedule.once_at,
            "dayOfMonth": schedule.day_of_month,
            "nextRunAt": schedule.next_run_at,
            "lastRunAt": schedule.last_run_at,
            "status": schedule.status,
            "runMode": schedule.run_mode,
            "continueTaskId": schedule.continue_task_id,
            "connectorIds": list(schedule.connector_ids),
            "toolIds": list(schedule.tool_ids),
            "autonomyMode": schedule.autonomy_mode,
            "skipConfirmations": schedule.skip_confirmations,
            "allowedUnattendedTools": list(schedule.allowed_unattended_tools),
            "currentRunId": schedule.current_run_id,
            "lastTaskId": schedule.last_task_id,
            "lastSessionId": schedule.last_session_id,
            "dispatchLockUntil": schedule.dispatch_lock_until,
            "createdAt": schedule.created_at,
            "updatedAt": schedule.updated_at,
            "metadata": dict(schedule.metadata or {}),
        }

    async def create_schedule(self, schedule: Schedule) -> Schedule:
        return await asyncio.to_thread(self._create_schedule_sync, schedule)

    def _create_schedule_sync(self, schedule: Schedule) -> Schedule:
        now = utcnow()
        schedule.created_at = now
        schedule.updated_at = now
        if schedule.status == "active" and schedule.next_run_at is None:
            schedule.next_run_at = compute_next_run(schedule, after=now - timedelta(seconds=1))
        self._schedule_ref(schedule.schedule_id).set(self._to_doc(schedule))
        return schedule

    async def get_schedule(self, schedule_id: str) -> Schedule | None:
        return await asyncio.to_thread(self._get_schedule_sync, schedule_id)

    def _get_schedule_sync(self, schedule_id: str) -> Schedule | None:
        doc = self._schedule_ref(schedule_id).get()
        if not doc.exists:
            return None
        return self._build_schedule(schedule_id, doc.to_dict() or {})

    async def list_schedules(self, owner_id: str, *, limit: int = 100) -> list[Schedule]:
        return await asyncio.to_thread(self._list_schedules_sync, owner_id, limit)

    def _list_schedules_sync(self, owner_id: str, limit: int) -> list[Schedule]:
        clamped_limit = max(1, min(int(limit), 200))
        try:
            query = (
                self._db.collection("schedules")
                .where(filter=FieldFilter("ownerId", "==", owner_id))
                .order_by("nextRunAt")
                .limit(clamped_limit)
            )
            rows: list[Schedule] = []
            for doc in query.stream():
                rows.append(self._build_schedule(doc.id, doc.to_dict() or {}))
            return rows
        except Exception as exc:
            logger.warning(
                "Ordered query for schedules (ownerId=%s) failed: %s; falling back to in-memory sort",
                owner_id,
                exc,
            )
            fallback_query = (
                self._db.collection("schedules")
                .where(filter=FieldFilter("ownerId", "==", owner_id))
            )
            rows = []
            for doc in fallback_query.stream():
                rows.append(self._build_schedule(doc.id, doc.to_dict() or {}))
            rows.sort(
                key=lambda s: (
                    s.next_run_at is None,
                    s.next_run_at or datetime.max.replace(tzinfo=timezone.utc),
                )
            )
            return rows[:clamped_limit]

    async def count_active(self, owner_id: str) -> int:
        rows = await self.list_schedules(owner_id, limit=200)
        return sum(1 for row in rows if row.status == "active")

    async def list_due(self, now: datetime, *, limit: int = 50) -> list[Schedule]:
        return await asyncio.to_thread(self._list_due_sync, now, limit)

    def _list_due_sync(self, now: datetime, limit: int) -> list[Schedule]:
        clamped_limit = max(1, min(int(limit), 100))
        try:
            query = (
                self._db.collection("schedules")
                .where(filter=FieldFilter("status", "==", "active"))
                .where(filter=FieldFilter("nextRunAt", "<=", now))
                .order_by("nextRunAt")
                .limit(clamped_limit)
            )
            return [self._build_schedule(doc.id, doc.to_dict() or {}) for doc in query.stream()]
        except Exception as exc:
            logger.warning(
                "Composite query for list_due failed: %s; falling back to in-memory filter and sort",
                exc,
            )
            fallback_query = (
                self._db.collection("schedules")
                .where(filter=FieldFilter("status", "==", "active"))
            )
            due: list[Schedule] = []
            for doc in fallback_query.stream():
                sched = self._build_schedule(doc.id, doc.to_dict() or {})
                if sched.next_run_at is not None and sched.next_run_at <= now:
                    due.append(sched)
            due.sort(
                key=lambda s: (
                    s.next_run_at is None,
                    s.next_run_at or datetime.max.replace(tzinfo=timezone.utc),
                )
            )
            return due[:clamped_limit]

    async def claim_due(
        self,
        schedule_id: str,
        *,
        now: datetime,
        lock_until: datetime,
    ) -> Schedule | None:
        return await asyncio.to_thread(self._claim_due_sync, schedule_id, now, lock_until)

    def _claim_due_sync(
        self,
        schedule_id: str,
        now: datetime,
        lock_until: datetime,
    ) -> Schedule | None:
        ref = self._schedule_ref(schedule_id)
        transaction = self._db.transaction()

        @firestore.transactional
        def _txn(txn) -> Schedule | None:
            snapshot = ref.get(transaction=txn)
            if not snapshot.exists:
                return None
            schedule = self._build_schedule(schedule_id, snapshot.to_dict() or {})
            if schedule.status != "active":
                return None
            if schedule.next_run_at is None or schedule.next_run_at > now:
                return None
            lock = schedule.dispatch_lock_until
            if lock is not None and lock > now:
                return None
            txn.update(
                ref,
                {
                    "dispatchLockUntil": lock_until,
                    "updatedAt": now,
                },
            )
            schedule.dispatch_lock_until = lock_until
            schedule.updated_at = now
            return schedule

        return _txn(transaction)

    async def release_lock(self, schedule_id: str) -> None:
        await asyncio.to_thread(self._release_lock_sync, schedule_id)

    def _release_lock_sync(self, schedule_id: str) -> None:
        self._schedule_ref(schedule_id).set(
            {"dispatchLockUntil": None, "updatedAt": utcnow()},
            merge=True,
        )

    async def save_schedule(self, schedule: Schedule) -> Schedule:
        return await asyncio.to_thread(self._save_schedule_sync, schedule)

    def _save_schedule_sync(self, schedule: Schedule) -> Schedule:
        schedule.updated_at = utcnow()
        self._schedule_ref(schedule.schedule_id).set(self._to_doc(schedule), merge=True)
        return schedule

    async def delete_schedule(self, schedule_id: str) -> None:
        await asyncio.to_thread(self._delete_schedule_sync, schedule_id)

    def _delete_schedule_sync(self, schedule_id: str) -> None:
        self._schedule_ref(schedule_id).delete()

    async def append_firing(self, firing: ScheduleFiring) -> ScheduleFiring:
        return await asyncio.to_thread(self._append_firing_sync, firing)

    def _append_firing_sync(self, firing: ScheduleFiring) -> ScheduleFiring:
        now = firing.created_at or utcnow()
        firing.created_at = now
        payload = {
            "firingId": firing.firing_id,
            "scheduleId": firing.schedule_id,
            "ownerId": firing.owner_id,
            "scheduledFor": firing.scheduled_for,
            "taskId": firing.task_id,
            "runId": firing.run_id,
            "sessionId": firing.session_id,
            "status": firing.status,
            "error": firing.error,
            "createdAt": now,
        }
        self._firing_ref(firing.schedule_id, firing.firing_id).set(payload)
        return firing

    async def list_firings(self, schedule_id: str, *, limit: int = 50) -> list[ScheduleFiring]:
        return await asyncio.to_thread(self._list_firings_sync, schedule_id, limit)

    def _list_firings_sync(self, schedule_id: str, limit: int) -> list[ScheduleFiring]:
        query = (
            self._schedule_ref(schedule_id)
            .collection("firings")
            .order_by("createdAt", direction="DESCENDING")
            .limit(max(1, min(int(limit), 200)))
        )
        return [self._build_firing(doc.id, doc.to_dict() or {}) for doc in query.stream()]

    async def latest_firing(self, schedule_id: str) -> ScheduleFiring | None:
        rows = await self.list_firings(schedule_id, limit=1)
        return rows[0] if rows else None


def build_schedule_from_input(
    *,
    owner_id: str,
    title: str,
    prompt: str,
    timezone_name: str = "UTC",
    freq: str = "daily",
    time_of_day: str = "09:00",
    days_of_week: list[int] | None = None,
    once_at: datetime | str | None = None,
    day_of_month: int = 1,
    run_mode: str = "new_task",
    continue_task_id: str | None = None,
    connector_ids: list[str] | None = None,
    tool_ids: list[str] | None = None,
    autonomy_mode: str | None = None,
    skip_confirmations: bool = False,
    allowed_unattended_tools: list[str] | None = None,
    status: str = "active",
    schedule_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Schedule:
    freq_norm = str(freq or "daily").strip().lower()
    if freq_norm not in SCHEDULE_FREQS:
        raise ValueError(f"Unsupported schedule frequency: {freq}")
    run_mode_norm = str(run_mode or "new_task").strip().lower()
    if run_mode_norm not in RUN_MODES:
        raise ValueError(f"Unsupported run mode: {run_mode}")
    status_norm = str(status or "active").strip().lower()
    if status_norm not in SCHEDULE_STATUSES:
        raise ValueError(f"Unsupported status: {status}")
    resolve_zone(timezone_name)
    if run_mode_norm == "continue_task" and not str(continue_task_id or "").strip():
        raise ValueError("continue_task requires continue_task_id")
    allowed = sanitize_unattended_tools(allowed_unattended_tools)
    skip = bool(skip_confirmations)
    schedule = Schedule(
        schedule_id=schedule_id or _uuid("sched_"),
        owner_id=owner_id,
        title=(title or prompt[:120] or "Scheduled task").strip()[:240],
        prompt=str(prompt or "").strip(),
        timezone=(timezone_name or "UTC").strip() or "UTC",
        freq=freq_norm,
        time_of_day=str(time_of_day or "09:00").strip() or "09:00",
        days_of_week=_clean_days(days_of_week),
        once_at=parse_datetime(once_at),
        day_of_month=min(max(int(day_of_month or 1), 1), 31),
        status=status_norm,
        run_mode=run_mode_norm,
        continue_task_id=str(continue_task_id).strip() if continue_task_id else None,
        connector_ids=_clean_ids(connector_ids),
        tool_ids=_clean_ids(tool_ids),
        autonomy_mode="auto" if skip else normalize_autonomy_mode(autonomy_mode),
        skip_confirmations=skip,
        allowed_unattended_tools=allowed,
        metadata=metadata or {},
    )
    if not schedule.prompt:
        raise ValueError("Schedule prompt is required")
    if freq_norm == "once" and schedule.once_at is None:
        raise ValueError("One-time schedules require once_at")
    schedule.next_run_at = compute_next_run(schedule, after=utcnow() - timedelta(seconds=1))
    if schedule.status == "active" and schedule.next_run_at is None:
        raise ValueError("Schedule has no upcoming run time")
    return schedule
