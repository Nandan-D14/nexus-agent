# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Durable production task repository.

This is the new source of truth for real-world task execution. The current
session/history system remains in place; this repository adds backend-owned
tasks, runs, events, approvals, and worker leases.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Magic strings constants
FIELD_CANCEL_REQUESTED = "cancelRequested"
STATUS_WAITING_APPROVAL = "waiting_approval"
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, cast

from firebase_admin import firestore
from google.cloud.firestore_v1 import FieldFilter

from nexus.config import settings
from nexus.firebase import get_firestore_client
from nexus.policy import normalize_autonomy_mode

TaskStatus = Literal[
    "queued",
    "running",
    "waiting_approval",
    "paused",
    "completed",
    "failed",
    "cancelled",
    "cancelling",
]

CANONICAL_TASK_STATUSES: frozenset[str] = frozenset(TaskStatus.__args__)  # type: ignore[attr-defined]
TERMINAL_TASK_STATUSES: frozenset[str] = frozenset({"completed", "failed", "cancelled"})

HISTORY_TO_DURABLE_STATUS: dict[str, TaskStatus] = {
    "idle": "queued",
    "creating": "queued",
    "ready": "queued",
    "queued": "queued",
    "active": "running",
    "running": "running",
    "waiting_approval": "waiting_approval",
    "paused": "paused",
    "completed": "completed",
    "ended": "completed",
    "failed": "failed",
    "error": "failed",
    "cancelled": "cancelled",
    "cancelling": "cancelling",
    "destroyed": "cancelled",
    "deleted": "cancelled",
}


def canonicalize_task_status(status: str | None) -> TaskStatus:
    """Normalize any execution status into the durable lifecycle vocabulary."""
    normalized = str(status or "queued").strip().lower()
    if normalized in CANONICAL_TASK_STATUSES:
        return cast(TaskStatus, normalized)
    if normalized not in HISTORY_TO_DURABLE_STATUS:
        logger.warning(f"Unknown task status '{normalized}' mapped to 'queued'")
    return HISTORY_TO_DURABLE_STATUS.get(normalized, "queued")


def map_history_status_to_durable(status: str | None) -> TaskStatus:
    """Map legacy session/run statuses to the canonical durable lifecycle."""
    return canonicalize_task_status(status)


def map_durable_status_to_history(status: str | None) -> str:
    """Map durable status back to the legacy history status surface."""
    durable = canonicalize_task_status(status)
    if durable == "waiting_approval":
        return "running"
    if durable == "paused":
        return "queued"
    return durable


def history_task_projection_from_durable(task: "DurableTask") -> dict[str, Any]:
    """Build a history-task projection from canonical durable task state."""
    return {
        "taskId": task.task_id,
        "ownerId": task.owner_id,
        "title": task.title,
        "status": map_durable_status_to_history(task.status),
        "runStatus": map_durable_status_to_history(task.status),
        "currentSessionId": task.session_id,
        "currentRunId": task.current_run_id,
        "updatedAt": task.updated_at,
        "schemaVersion": 2,
        "canonicalSource": "production_tasks",
    }


def history_run_projection_from_durable(run: "DurableTaskRun") -> dict[str, Any]:
    """Build a history-run projection from canonical durable run state."""
    return {
        "runId": run.run_id,
        "taskId": run.task_id,
        "ownerId": run.owner_id,
        "sessionId": run.session_id,
        "status": map_durable_status_to_history(run.status),
        "startedAt": run.started_at,
        "completedAt": run.completed_at,
        "updatedAt": run.updated_at,
        "summary": run.summary,
        "error": run.error,
        "executionPayload": run.execution_payload or {},
        "schemaVersion": 2,
        "canonicalSource": "production_tasks",
    }


def build_execution_payload(
    *,
    task_id: str,
    run_id: str,
    owner_id: str,
    session_id: str | None,
    input_text: str,
    connector_ids: list[str] | None = None,
    uploaded_files: list[dict[str, Any]] | None = None,
    runtime_config_snapshot: dict[str, Any] | None = None,
    autonomy_mode: str | None = None,
    budget: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Canonical durable execution payload for worker-owned runs."""
    cleaned_connectors = []
    for item in (connector_ids or []):
        val = str(item).strip()
        if val:
            cleaned_connectors.append(val)
        else:
            logger.warning("build_execution_payload: implicitly stripped an empty connector_id")

    return {
        "schema_version": 1,
        "task_id": task_id,
        "run_id": run_id,
        "owner_id": owner_id,
        "session_id": session_id,
        "input_text": input_text,
        "connector_ids": cleaned_connectors,
        "uploaded_files": [item for item in (uploaded_files or []) if isinstance(item, dict)],
        "runtime_config": runtime_config_snapshot or {},
        "autonomy_mode": normalize_autonomy_mode(autonomy_mode or settings.default_autonomy_mode),
        "budget": budget or {},
        "metadata": metadata or {},
    }


def history_event_projection_from_durable(event: "DurableTaskEvent") -> dict[str, Any]:
    """Build history projection hints for a durable event."""
    updates: dict[str, Any] = {
        "taskId": event.task_id,
        "runId": event.run_id,
        "lastEventId": event.event_id,
        "lastEventSeq": event.seq,
        "lastEventType": event.event_type,
        "lastEventAt": event.created_at,
        "canonicalSource": "production_tasks",
    }
    if event.event_type == "user_message":
        updates["messageCountDelta"] = 1
    elif event.event_type in {"step_started", "agent_tool_call"}:
        updates["runStatus"] = "running"
    elif event.event_type == "agent_complete":
        updates["runStatus"] = "completed"
        summary = event.payload.get("summary")
        if isinstance(summary, str):
            updates["summary"] = summary
    elif event.event_type == "task_cancel_requested":
        updates["runStatus"] = "cancelling"
    elif event.event_type == "approval_requested":
        updates["runStatus"] = "running"
        updates["approvalStatus"] = "pending"
    return updates


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_datetime(value: Any) -> datetime | None:
    return value if isinstance(value, datetime) else None


def _uuid(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


@dataclass
class DurableTask:
    task_id: str
    owner_id: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime | None = None
    autonomy_mode: str = "manual"
    session_id: str | None = None
    current_run_id: str | None = None
    input_text: str = ""
    cancel_requested: bool = False
    budget: dict[str, Any] | None = None
    sandbox_state: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class DurableTaskRun:
    run_id: str
    task_id: str
    owner_id: str
    status: str
    created_at: datetime
    updated_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    attempt: int = 1
    session_id: str | None = None
    error: str | None = None
    summary: str | None = None
    execution_payload: dict[str, Any] | None = None


@dataclass
class DurableTaskEvent:
    event_id: str
    task_id: str
    owner_id: str
    event_type: str
    created_at: datetime
    payload: dict[str, Any]
    run_id: str | None = None
    visible: bool = True
    # Monotonic per-task sequence number for reliable replay.
    # Older events written before this field was introduced will return seq=0,
    # in which case clients should fall back to after_event_id pagination.
    seq: int = 0


@dataclass
class DurableApproval:
    approval_id: str
    task_id: str
    owner_id: str
    status: str
    description: str
    risk: str
    created_at: datetime
    resolved_at: datetime | None = None
    approved: bool | None = None
    metadata: dict[str, Any] | None = None


class ProductionTaskRepository:
    """Operations on the canonical durable task data models."""

    def __init__(self) -> None:
        self._db = get_firestore_client()
        self._has_seq_cache: set[str] = set()

    def _task_ref(self, task_id: str):
        return self._db.collection("tasks").document(task_id)

    def _run_ref(self, task_id: str, run_id: str):
        return self._task_ref(task_id).collection("runs").document(run_id)

    def _event_ref(self, task_id: str, event_id: str):
        return self._task_ref(task_id).collection("events").document(event_id)

    def _approval_ref(self, task_id: str, approval_id: str):
        return self._task_ref(task_id).collection("approvals").document(approval_id)

    @staticmethod
    def _build_task(task_id: str, data: dict[str, Any]) -> DurableTask:
        return DurableTask(
            task_id=task_id,
            owner_id=str(data.get("ownerId") or ""),
            title=str(data.get("title") or "Untitled task"),
            status=canonicalize_task_status(str(data.get("status") or "queued")),
            created_at=_coerce_datetime(data.get("createdAt")) or utcnow(),
            updated_at=_coerce_datetime(data.get("updatedAt")),
            autonomy_mode=str(data.get("autonomyMode") or "manual"),
            session_id=data.get("sessionId") if isinstance(data.get("sessionId"), str) else None,
            current_run_id=data.get("currentRunId") if isinstance(data.get("currentRunId"), str) else None,
            input_text=str(data.get("inputText") or ""),
            cancel_requested=bool(data.get("cancelRequested")),
            budget=data.get("budget") if isinstance(data.get("budget"), dict) else None,
            sandbox_state=data.get("sandboxState") if isinstance(data.get("sandboxState"), dict) else None,
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else None,
        )

    @staticmethod
    def _build_run(run_id: str, data: dict[str, Any]) -> DurableTaskRun:
        return DurableTaskRun(
            run_id=run_id,
            task_id=str(data.get("taskId") or ""),
            owner_id=str(data.get("ownerId") or ""),
            status=canonicalize_task_status(str(data.get("status") or "queued")),
            created_at=_coerce_datetime(data.get("createdAt")) or utcnow(),
            updated_at=_coerce_datetime(data.get("updatedAt")),
            started_at=_coerce_datetime(data.get("startedAt")),
            completed_at=_coerce_datetime(data.get("completedAt")),
            lease_owner=data.get("leaseOwner") if isinstance(data.get("leaseOwner"), str) else None,
            lease_expires_at=_coerce_datetime(data.get("leaseExpiresAt")),
            attempt=int(data.get("attempt", 1) or 1),
            session_id=data.get("sessionId") if isinstance(data.get("sessionId"), str) else None,
            error=data.get("error") if isinstance(data.get("error"), str) else None,
            summary=data.get("summary") if isinstance(data.get("summary"), str) else None,
            execution_payload=(
                data.get("executionPayload")
                if isinstance(data.get("executionPayload"), dict)
                else None
            ),
        )

    @staticmethod
    def _build_event(event_id: str, data: dict[str, Any]) -> DurableTaskEvent:
        try:
            seq_raw = data.get("seq", 0)
            seq = int(seq_raw) if seq_raw is not None else 0
        except (TypeError, ValueError):
            seq = 0
        return DurableTaskEvent(
            event_id=event_id,
            task_id=str(data.get("taskId") or ""),
            owner_id=str(data.get("ownerId") or ""),
            event_type=str(data.get("type") or "event"),
            created_at=_coerce_datetime(data.get("createdAt")) or utcnow(),
            payload=data.get("payload") if isinstance(data.get("payload"), dict) else {},
            run_id=data.get("runId") if isinstance(data.get("runId"), str) else None,
            visible=bool(data.get("visible", True)),
            seq=seq,
        )

    @staticmethod
    def _build_approval(approval_id: str, data: dict[str, Any]) -> DurableApproval:
        return DurableApproval(
            approval_id=approval_id,
            task_id=str(data.get("taskId") or ""),
            owner_id=str(data.get("ownerId") or ""),
            status=str(data.get("status") or "pending"),
            description=str(data.get("description") or ""),
            risk=str(data.get("risk") or "medium"),
            created_at=_coerce_datetime(data.get("createdAt")) or utcnow(),
            resolved_at=_coerce_datetime(data.get("resolvedAt")),
            approved=data.get("approved") if isinstance(data.get("approved"), bool) else None,
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else None,
        )

    async def create_task(
        self,
        *,
        owner_id: str,
        title: str,
        input_text: str = "",
        autonomy_mode: str | None = None,
        session_id: str | None = None,
        budget: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DurableTask:
        return await asyncio.to_thread(
            self._create_task_sync,
            owner_id,
            title,
            input_text,
            autonomy_mode,
            session_id,
            budget,
            metadata,
        )

    def _create_task_sync(
        self,
        owner_id: str,
        title: str,
        input_text: str,
        autonomy_mode: str | None,
        session_id: str | None,
        budget: dict[str, Any] | None,
        metadata: dict[str, Any] | None,
    ) -> DurableTask:
        task_id = _uuid("task_")
        now = utcnow()
        payload = {
            "taskId": task_id,
            "ownerId": owner_id,
            "title": title.strip() or "Untitled task",
            "status": canonicalize_task_status("queued"),
            "autonomyMode": normalize_autonomy_mode(autonomy_mode or settings.default_autonomy_mode),
            "sessionId": session_id,
            "currentRunId": None,
            "inputText": input_text,
            "cancelRequested": False,
            "budget": budget
            or {
                "credits": settings.default_task_budget_credits,
                "maxRuntimeMinutes": settings.default_task_max_runtime_minutes,
                "maxToolCalls": settings.default_task_max_tool_calls,
            },
            "sandboxState": {"state": "none"},
            "metadata": metadata or {},
            "createdAt": now,
            "updatedAt": now,
        }
        self._task_ref(task_id).set(payload)
        return self._build_task(task_id, payload)

    async def get_task(self, task_id: str) -> DurableTask | None:
        return await asyncio.to_thread(self._get_task_sync, task_id)

    def _get_task_sync(self, task_id: str) -> DurableTask | None:
        doc = self._task_ref(task_id).get()
        if not doc.exists:
            return None
        return self._build_task(task_id, doc.to_dict() or {})

    async def create_run(
        self,
        *,
        task_id: str,
        owner_id: str,
        session_id: str | None = None,
        input_text: str | None = None,
        connector_ids: list[str] | None = None,
        uploaded_files: list[dict[str, Any]] | None = None,
        runtime_config_snapshot: dict[str, Any] | None = None,
        autonomy_mode: str | None = None,
        budget: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DurableTaskRun:
        return await asyncio.to_thread(
            self._create_run_sync,
            task_id,
            owner_id,
            session_id,
            input_text,
            connector_ids,
            uploaded_files,
            runtime_config_snapshot,
            autonomy_mode,
            budget,
            metadata,
        )

    def _create_run_sync(
        self,
        task_id: str,
        owner_id: str,
        session_id: str | None,
        input_text: str | None,
        connector_ids: list[str] | None,
        uploaded_files: list[dict[str, Any]] | None,
        runtime_config_snapshot: dict[str, Any] | None,
        autonomy_mode: str | None,
        budget: dict[str, Any] | None,
        metadata: dict[str, Any] | None,
    ) -> DurableTaskRun:
        run_id = _uuid("run_")
        now = utcnow()
        task_doc = self._task_ref(task_id).get()
        if not task_doc.exists:
            logger.error(f"Cannot create run for non-existent task: {task_id}")
            raise ValueError(f"Task not found: {task_id}")
        task_data = task_doc.to_dict() or {}
        effective_input = input_text if input_text is not None else str(task_data.get("inputText") or "")
        effective_budget = budget if budget is not None else task_data.get("budget")
        if not isinstance(effective_budget, dict):
            effective_budget = {}
        effective_autonomy = autonomy_mode or str(task_data.get("autonomyMode") or settings.default_autonomy_mode)
        execution_payload = build_execution_payload(
            task_id=task_id,
            run_id=run_id,
            owner_id=owner_id,
            session_id=session_id,
            input_text=effective_input,
            connector_ids=connector_ids,
            uploaded_files=uploaded_files,
            runtime_config_snapshot=runtime_config_snapshot,
            autonomy_mode=effective_autonomy,
            budget=effective_budget,
            metadata=metadata,
        )
        payload = {
            "runId": run_id,
            "taskId": task_id,
            "ownerId": owner_id,
            "status": canonicalize_task_status("queued"),
            "attempt": 1,
            "sessionId": session_id,
            "executionPayload": execution_payload,
            "createdAt": now,
            "updatedAt": now,
        }
        batch = self._db.batch()
        batch.set(self._run_ref(task_id, run_id), payload)
        batch.set(
            self._task_ref(task_id),
            {"currentRunId": run_id, "status": canonicalize_task_status("queued"), "updatedAt": now},
            merge=True,
        )
        try:
            batch.commit()
        except Exception as exc:
            logger.exception(f"Failed to commit run creation for task {task_id}")
            raise RuntimeError(f"Failed to commit run creation for task {task_id}: {exc}") from exc
        return self._build_run(run_id, payload)

    async def get_run(self, *, task_id: str, run_id: str, owner_id: str) -> DurableTaskRun | None:
        return await asyncio.to_thread(self._get_run_sync, task_id, run_id, owner_id)

    def _get_run_sync(self, task_id: str, run_id: str, owner_id: str) -> DurableTaskRun | None:
        doc = self._run_ref(task_id, run_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        if data.get("ownerId") != owner_id:
            return None
        return self._build_run(run_id, data)

    async def append_event(
        self,
        *,
        task_id: str,
        owner_id: str,
        event_type: str,
        payload: dict[str, Any],
        run_id: str | None = None,
        visible: bool = True,
    ) -> DurableTaskEvent:
        return await asyncio.to_thread(
            self._append_event_sync,
            task_id,
            owner_id,
            event_type,
            payload,
            run_id,
            visible,
        )

    def _append_event_sync(
        self,
        task_id: str,
        owner_id: str,
        event_type: str,
        payload: dict[str, Any],
        run_id: str | None,
        visible: bool,
    ) -> DurableTaskEvent:
        event_id = _uuid("evt_")
        now = utcnow()
        task_ref = self._task_ref(task_id)
        event_ref = self._event_ref(task_id, event_id)
        transaction = self._db.transaction()

        @firestore.transactional
        def transactional_append(txn):
            task_doc = task_ref.get(transaction=txn)
            task_data = task_doc.to_dict() or {}
            try:
                last_seq = int(task_data.get("lastEventSeq", 0) or 0)
            except (TypeError, ValueError):
                last_seq = 0
            next_seq = last_seq + 1
            data = {
                "eventId": event_id,
                "taskId": task_id,
                "ownerId": owner_id,
                "runId": run_id,
                "type": event_type,
                "payload": payload,
                "visible": visible,
                "createdAt": now,
                "seq": next_seq,
            }
            txn.set(event_ref, data)
            txn.set(
                task_ref,
                {
                    "lastEventAt": now,
                    "lastEventSeq": next_seq,
                    "updatedAt": now,
                },
                merge=True,
            )
            return data

        data = transactional_append(transaction)
        return self._build_event(event_id, data)

    async def list_events(
        self,
        *,
        task_id: str,
        owner_id: str,
        after_event_id: str | None = None,
        after_seq: int | None = None,
        run_id: str | None = None,
        limit: int | None = None,
    ) -> list[DurableTaskEvent]:
        """Return durable events for a task.

        Prefer ``after_seq`` when reconnecting clients have a last-seen sequence
        number. ``after_event_id`` is kept for backward compatibility.
        """
        return await asyncio.to_thread(
            self._list_events_sync,
            task_id,
            owner_id,
            after_event_id,
            after_seq,
            run_id,
            limit,
        )

    def _list_events_sync(
        self,
        task_id: str,
        owner_id: str,
        after_event_id: str | None,
        after_seq: int | None,
        run_id: str | None,
        limit: int | None,
    ) -> list[DurableTaskEvent]:
        task = self._get_task_sync(task_id)
        if not task or task.owner_id != owner_id:
            return []

        # Prefer seq-based ordering when available.
        if after_seq is not None or self._task_has_seq_field(task_id):
            query = (
                self._task_ref(task_id)
                .collection("events")
                .where(filter=FieldFilter("visible", "==", True))
                .order_by("seq")
            )
            if after_seq is not None and after_seq > 0:
                query = query.where(filter=FieldFilter("seq", ">", int(after_seq)))
            if run_id:
                query = query.where(filter=FieldFilter("runId", "==", run_id))
            query = query.limit(limit or settings.task_event_replay_limit)
            return [
                self._build_event(doc.id, doc.to_dict() or {})
                for doc in query.stream()
            ]

        # Legacy path: order by createdAt, paginate by event id.
        query = (
            self._task_ref(task_id)
            .collection("events")
            .where(filter=FieldFilter("visible", "==", True))
            .order_by("createdAt")
        )
        if run_id:
            query = query.where(filter=FieldFilter("runId", "==", run_id))
        if after_event_id:
            after_doc = self._event_ref(task_id, after_event_id).get()
            if after_doc.exists:
                after_created_at = (after_doc.to_dict() or {}).get("createdAt")
                if isinstance(after_created_at, datetime):
                    query = query.where(filter=FieldFilter("createdAt", ">", after_created_at))
        query = query.limit(limit or settings.task_event_replay_limit)
        return [
            self._build_event(doc.id, doc.to_dict() or {})
            for doc in query.stream()
        ]

    def _task_has_seq_field(self, task_id: str) -> bool:
        """Best-effort check for whether the task has begun emitting seq numbers."""
        if task_id in self._has_seq_cache:
            return True
        try:
            doc = self._task_ref(task_id).get()
            data = doc.to_dict() or {}
            has_seq = int(data.get("lastEventSeq", 0) or 0) > 0
            if has_seq:
                self._has_seq_cache.add(task_id)
            return has_seq
        except Exception:
            return False

    async def claim_run(self, *, task_id: str, run_id: str, worker_id: str) -> DurableTaskRun | None:
        return await asyncio.to_thread(self._claim_run_sync, task_id, run_id, worker_id)

    def _claim_run_sync(self, task_id: str, run_id: str, worker_id: str) -> DurableTaskRun | None:
        now = utcnow()
        lease_expires_at = now + timedelta(seconds=settings.task_worker_lease_seconds)
        run_ref = self._run_ref(task_id, run_id)
        task_ref = self._task_ref(task_id)
        transaction = self._db.transaction()

        @firestore.transactional
        def transactional_claim(txn):
            task_doc = task_ref.get(transaction=txn)
            run_doc = run_ref.get(transaction=txn)
            if not task_doc.exists or not run_doc.exists:
                return None
            task_data = task_doc.to_dict() or {}
            run_data = run_doc.to_dict() or {}
            if bool(task_data.get("cancelRequested")):
                return None
            status = canonicalize_task_status(str(run_data.get("status") or "queued"))
            existing_lease = _coerce_datetime(run_data.get("leaseExpiresAt"))
            if status == "running" and existing_lease and existing_lease > now:
                return None
            if status in {"completed", "failed", "cancelled"}:
                return None
            updates = {
                "status": canonicalize_task_status("running"),
                "leaseOwner": worker_id,
                "leaseExpiresAt": lease_expires_at,
                "startedAt": run_data.get("startedAt") or now,
                "updatedAt": now,
            }
            txn.set(run_ref, updates, merge=True)
            txn.set(
                task_ref,
                {"status": canonicalize_task_status("running"), "currentRunId": run_id, "updatedAt": now},
                merge=True,
            )
            run_data.update(updates)
            return self._build_run(run_id, run_data)

        return transactional_claim(transaction)

    async def finish_run(
        self,
        *,
        task_id: str,
        run_id: str,
        status: Literal["completed", "failed", "cancelled"],
        summary: str = "",
        error: str | None = None,
    ) -> None:
        await asyncio.to_thread(self._finish_run_sync, task_id, run_id, status, summary, error)

    def _finish_run_sync(
        self,
        task_id: str,
        run_id: str,
        status: str,
        summary: str,
        error: str | None,
    ) -> None:
        now = utcnow()
        updates = {
            "status": canonicalize_task_status(status),
            "summary": summary,
            "error": error,
            "completedAt": now,
            "updatedAt": now,
            "leaseOwner": None,
            "leaseExpiresAt": None,
        }
        batch = self._db.batch()
        batch.set(self._run_ref(task_id, run_id), updates, merge=True)
        batch.set(
            self._task_ref(task_id),
            {"status": canonicalize_task_status(status), "updatedAt": now, "lastSummary": summary},
            merge=True,
        )
        batch.commit()

    async def request_cancel(self, *, task_id: str, owner_id: str) -> bool:
        return await asyncio.to_thread(self._request_cancel_sync, task_id, owner_id)

    def _request_cancel_sync(self, task_id: str, owner_id: str) -> bool:
        task = self._get_task_sync(task_id)
        if not task or task.owner_id != owner_id:
            return False
        now = utcnow()
        self._task_ref(task_id).set(
            {"cancelRequested": True, "status": canonicalize_task_status("cancelling"), "updatedAt": now},
            merge=True,
        )
        self._append_event_sync(
            task_id,
            owner_id,
            "task_cancel_requested",
            {"status": "cancelling"},
            task.current_run_id,
            True,
        )
        return True

    async def create_approval(
        self,
        *,
        task_id: str,
        owner_id: str,
        description: str,
        risk: str,
        metadata: dict[str, Any] | None = None,
    ) -> DurableApproval:
        return await asyncio.to_thread(
            self._create_approval_sync,
            task_id,
            owner_id,
            description,
            risk,
            metadata,
        )

    def _create_approval_sync(
        self,
        task_id: str,
        owner_id: str,
        description: str,
        risk: str,
        metadata: dict[str, Any] | None,
    ) -> DurableApproval:
        approval_id = _uuid("appr_")
        now = utcnow()
        payload = {
            "approvalId": approval_id,
            "taskId": task_id,
            "ownerId": owner_id,
            "status": "pending",
            "description": description,
            "risk": risk,
            "metadata": metadata or {},
            "createdAt": now,
        }
        batch = self._db.batch()
        batch.set(self._approval_ref(task_id, approval_id), payload)
        batch.set(
            self._task_ref(task_id),
            {"status": canonicalize_task_status("waiting_approval"), "updatedAt": now},
            merge=True,
        )
        batch.commit()
        return self._build_approval(approval_id, payload)

    async def get_approval(
        self,
        *,
        task_id: str,
        approval_id: str,
        owner_id: str,
    ) -> DurableApproval | None:
        return await asyncio.to_thread(
            self._get_approval_sync,
            task_id,
            approval_id,
            owner_id,
        )

    def _get_approval_sync(
        self,
        task_id: str,
        approval_id: str,
        owner_id: str,
    ) -> DurableApproval | None:
        doc = self._approval_ref(task_id, approval_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        if data.get("ownerId") != owner_id:
            return None
        return self._build_approval(approval_id, data)

    async def resolve_approval(
        self,
        *,
        task_id: str,
        approval_id: str,
        owner_id: str,
        approved: bool,
    ) -> DurableApproval | None:
        return await asyncio.to_thread(
            self._resolve_approval_sync,
            task_id,
            approval_id,
            owner_id,
            approved,
        )

    def _resolve_approval_sync(
        self,
        task_id: str,
        approval_id: str,
        owner_id: str,
        approved: bool,
    ) -> DurableApproval | None:
        approval_ref = self._approval_ref(task_id, approval_id)
        doc = approval_ref.get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        if data.get("ownerId") != owner_id:
            return None
        now = utcnow()
        updates = {
            "status": "approved" if approved else "denied",
            "approved": approved,
            "resolvedAt": now,
        }
        approval_ref.set(updates, merge=True)
        self._task_ref(task_id).set(
            {"status": canonicalize_task_status("running"), "updatedAt": now},
            merge=True,
        )
        data.update(updates)
        return self._build_approval(approval_id, data)
