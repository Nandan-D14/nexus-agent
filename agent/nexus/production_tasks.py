# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Durable production task repository.

This is the new source of truth for real-world task execution. The current
session/history system remains in place; this repository adds backend-owned
tasks, runs, events, approvals, and worker leases.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
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
from google.api_core.exceptions import FailedPrecondition
from google.cloud.firestore_v1 import FieldFilter

from nexus.config import settings
from nexus.firebase import get_firestore_client
from nexus.firestore_concurrency import guarded_write, run_with_write_retry
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


def lease_is_live(lease_expires_at: datetime | None) -> bool:
    """True when a lease timestamp is present and still in the future.

    A live lease means some worker currently owns the run, so other code paths
    must leave it alone. Naive timestamps are read as UTC, matching how the
    store writes them.
    """
    if lease_expires_at is None:
        return False
    expires = lease_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires > datetime.now(timezone.utc)

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
        "verification": run.verification or {},
        "checkpoint": run.checkpoint or {},
        "finalResponse": run.final_response,
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
    tool_ids: list[str] | None = None,
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

    cleaned_tools = []
    for item in (tool_ids or []):
        val = str(item).strip()
        if val:
            cleaned_tools.append(val)

    return {
        "schema_version": 1,
        "task_id": task_id,
        "run_id": run_id,
        "owner_id": owner_id,
        "session_id": session_id,
        "input_text": input_text,
        "connector_ids": cleaned_connectors,
        "tool_ids": cleaned_tools,
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


def approval_action_hash(tool_name: str, arguments: dict[str, Any] | None) -> str:
    """Return a stable opaque fingerprint without persisting raw arguments."""
    canonical = json.dumps(
        {"tool": tool_name, "arguments": arguments or {}},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
    claim_token: str | None = None
    claim_generation: int = 0
    session_id: str | None = None
    error: str | None = None
    summary: str | None = None
    execution_payload: dict[str, Any] | None = None
    checkpoint: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    final_response: str | None = None


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


class ProductionRepoBase:
    """Shared kernel for the durable task repositories.

    Owns the Firestore client, document-ref builders, dataclass builders, the
    task-read (``get_task``) and the durable event-log operations
    (``append_event`` / ``list_events``). :class:`TaskRunStore` and
    :class:`ApprovalStore` subclass this so their cross-concern calls
    (emitting events, reading the parent task) resolve to inherited methods.
    """

    def __init__(self) -> None:
        self._db = get_firestore_client()
        self._has_seq_cache: set[str] = set()
        self._stale_runs_index_warning_emitted = False

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
            claim_token=data.get("claimToken") if isinstance(data.get("claimToken"), str) else None,
            claim_generation=int(data.get("claimGeneration", 0) or 0),
            session_id=data.get("sessionId") if isinstance(data.get("sessionId"), str) else None,
            error=data.get("error") if isinstance(data.get("error"), str) else None,
            summary=data.get("summary") if isinstance(data.get("summary"), str) else None,
            execution_payload=(
                data.get("executionPayload")
                if isinstance(data.get("executionPayload"), dict)
                else None
            ),
            checkpoint=data.get("checkpoint") if isinstance(data.get("checkpoint"), dict) else None,
            verification=data.get("verification") if isinstance(data.get("verification"), dict) else None,
            final_response=(
                data.get("finalResponse")
                if isinstance(data.get("finalResponse"), str)
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

    async def get_task(self, task_id: str) -> DurableTask | None:
        return await asyncio.to_thread(self._get_task_sync, task_id)

    def _get_task_sync(self, task_id: str) -> DurableTask | None:
        doc = self._task_ref(task_id).get()
        if not doc.exists:
            return None
        return self._build_task(task_id, doc.to_dict() or {})

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
        async with guarded_write(task_id):
            return await asyncio.to_thread(
                run_with_write_retry,
                lambda: self._append_event_sync(
                    task_id,
                    owner_id,
                    event_type,
                    payload,
                    run_id,
                    visible,
                ),
                description="append_event",
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

        cap = int(limit or settings.task_event_replay_limit)
        # Over-fetch a little so client-side filtering on visible/runId still
        # returns up to ``cap`` matches. Firestore charges per read either way,
        # but we bound the extra work so a pathological task can't blow up.
        fetch_cap = max(cap, min(cap * 4, cap + 200))

        # Prefer seq-based ordering when available.
        if after_seq is not None or self._task_has_seq_field(task_id):
            # Single-field query only: Firestore auto-indexes ``seq``. Filtering
            # by ``visible`` / ``runId`` here would require a composite index,
            # so we do those checks in Python below.
            query = self._task_ref(task_id).collection("events").order_by("seq")
            if after_seq is not None and after_seq > 0:
                query = query.where(filter=FieldFilter("seq", ">", int(after_seq)))
            query = query.limit(fetch_cap)
            events = self._filter_events_client_side(
                query, run_id=run_id, cap=cap
            )
            if events:
                return events
            # No matching events under the seq path — fall through to the
            # createdAt path only when the task has never emitted a seq at all.
            if self._task_has_seq_field(task_id):
                return []

        # Legacy path: order by createdAt (also single-field indexed).
        query = self._task_ref(task_id).collection("events").order_by("createdAt")
        if after_event_id:
            after_doc = self._event_ref(task_id, after_event_id).get()
            if after_doc.exists:
                after_created_at = (after_doc.to_dict() or {}).get("createdAt")
                if isinstance(after_created_at, datetime):
                    query = query.where(filter=FieldFilter("createdAt", ">", after_created_at))
        query = query.limit(fetch_cap)
        return self._filter_events_client_side(query, run_id=run_id, cap=cap)

    def _filter_events_client_side(self, query, *, run_id: str | None, cap: int) -> list[DurableTaskEvent]:
        """Stream a Firestore query and apply ``visible`` / ``runId`` filters in memory.

        Keeps the Firestore queries single-field so they never require a manual
        composite index. Deployments that want server-side filtering can still
        create the composite index from ``firestore.indexes.json`` — this code
        simply doesn't rely on it.
        """
        results: list[DurableTaskEvent] = []
        try:
            iterator = query.stream()
        except Exception:
            logger.warning("Firestore event query failed for task events", exc_info=True)
            return results
        for doc in iterator:
            data = doc.to_dict() or {}
            if data.get("visible") is False:
                continue
            if run_id and data.get("runId") != run_id:
                continue
            results.append(self._build_event(doc.id, data))
            if len(results) >= cap:
                break
        return results

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



class BoundProductionStore(ProductionRepoBase):
    """A focused store that shares its owner facade's client and mutable state.

    Proxies ``_db``, ``_has_seq_cache`` and ``_stale_runs_index_warning_emitted``
    back to the owning :class:`ProductionTaskRepository` so all stores operate
    on one Firestore client and one set of caches (and so white-box callers that
    patch the facade's ``_db`` are observed by the stores).
    """

    def __init__(self, owner: "ProductionRepoBase") -> None:
        self._owner = owner

    @property
    def _db(self):
        return self._owner._db

    @property
    def _has_seq_cache(self) -> set[str]:
        return self._owner._has_seq_cache

    @property
    def _stale_runs_index_warning_emitted(self) -> bool:
        return self._owner._stale_runs_index_warning_emitted

    @_stale_runs_index_warning_emitted.setter
    def _stale_runs_index_warning_emitted(self, value: bool) -> None:
        self._owner._stale_runs_index_warning_emitted = value


class ProductionTaskRepository(ProductionRepoBase):
    """Durable task repository facade.

    Composes the focused :class:`TaskRunStore` and :class:`ApprovalStore` and
    delegates their methods via :meth:`__getattr__`. Task-read and event-log
    operations are inherited from :class:`ProductionRepoBase`, so external
    callers keep the identical public API.
    """

    def __init__(self) -> None:
        super().__init__()
        self._delegates = None

    def _ensure_delegates(self):
        delegates = self.__dict__.get("_delegates")
        if delegates is None:
            from nexus.repositories.approval_store import ApprovalStore
            from nexus.repositories.task_run_store import TaskRunStore

            self._runs = TaskRunStore(self)
            self._approvals = ApprovalStore(self)
            delegates = (self._runs, self._approvals)
            self._delegates = delegates
        return delegates

    def __getattr__(self, name: str):
        # Only invoked for methods moved to a focused store. Public method
        # names are unique across the stores, so first match wins. Delegates
        # are built lazily so instances created via ``__new__`` (e.g. tests)
        # still resolve store methods.
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        for delegate in self._ensure_delegates():
            attr = getattr(delegate, name, None)
            if attr is not None:
                return attr
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}"
        )
