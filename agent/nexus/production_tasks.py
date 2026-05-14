# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Durable production task repository.

This is the new source of truth for real-world task execution. The current
session/history system remains in place; this repository adds backend-owned
tasks, runs, events, approvals, and worker leases.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

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
    """Firestore-backed durable task repository."""

    @property
    def _db(self):
        return get_firestore_client()

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
            status=str(data.get("status") or "queued"),
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
            status=str(data.get("status") or "queued"),
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
        )

    @staticmethod
    def _build_event(event_id: str, data: dict[str, Any]) -> DurableTaskEvent:
        return DurableTaskEvent(
            event_id=event_id,
            task_id=str(data.get("taskId") or ""),
            owner_id=str(data.get("ownerId") or ""),
            event_type=str(data.get("type") or "event"),
            created_at=_coerce_datetime(data.get("createdAt")) or utcnow(),
            payload=data.get("payload") if isinstance(data.get("payload"), dict) else {},
            run_id=data.get("runId") if isinstance(data.get("runId"), str) else None,
            visible=bool(data.get("visible", True)),
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
            "status": "queued",
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

    async def create_run(self, *, task_id: str, owner_id: str, session_id: str | None = None) -> DurableTaskRun:
        return await asyncio.to_thread(self._create_run_sync, task_id, owner_id, session_id)

    def _create_run_sync(self, task_id: str, owner_id: str, session_id: str | None) -> DurableTaskRun:
        run_id = _uuid("run_")
        now = utcnow()
        payload = {
            "runId": run_id,
            "taskId": task_id,
            "ownerId": owner_id,
            "status": "queued",
            "attempt": 1,
            "sessionId": session_id,
            "createdAt": now,
            "updatedAt": now,
        }
        batch = self._db.batch()
        batch.set(self._run_ref(task_id, run_id), payload)
        batch.set(
            self._task_ref(task_id),
            {"currentRunId": run_id, "status": "queued", "updatedAt": now},
            merge=True,
        )
        batch.commit()
        return self._build_run(run_id, payload)

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
        data = {
            "eventId": event_id,
            "taskId": task_id,
            "ownerId": owner_id,
            "runId": run_id,
            "type": event_type,
            "payload": payload,
            "visible": visible,
            "createdAt": now,
        }
        batch = self._db.batch()
        batch.set(self._event_ref(task_id, event_id), data)
        batch.set(self._task_ref(task_id), {"lastEventAt": now, "updatedAt": now}, merge=True)
        batch.commit()
        return self._build_event(event_id, data)

    async def list_events(
        self,
        *,
        task_id: str,
        owner_id: str,
        after_event_id: str | None = None,
        limit: int | None = None,
    ) -> list[DurableTaskEvent]:
        return await asyncio.to_thread(self._list_events_sync, task_id, owner_id, after_event_id, limit)

    def _list_events_sync(
        self,
        task_id: str,
        owner_id: str,
        after_event_id: str | None,
        limit: int | None,
    ) -> list[DurableTaskEvent]:
        task = self._get_task_sync(task_id)
        if not task or task.owner_id != owner_id:
            return []
        query = (
            self._task_ref(task_id)
            .collection("events")
            .where(filter=FieldFilter("visible", "==", True))
            .order_by("createdAt")
        )
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
            status = str(run_data.get("status") or "queued")
            existing_lease = _coerce_datetime(run_data.get("leaseExpiresAt"))
            if status == "running" and existing_lease and existing_lease > now:
                return None
            if status in {"completed", "failed", "cancelled"}:
                return None
            updates = {
                "status": "running",
                "leaseOwner": worker_id,
                "leaseExpiresAt": lease_expires_at,
                "startedAt": run_data.get("startedAt") or now,
                "updatedAt": now,
            }
            txn.set(run_ref, updates, merge=True)
            txn.set(
                task_ref,
                {"status": "running", "currentRunId": run_id, "updatedAt": now},
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
            "status": status,
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
            {"status": status, "updatedAt": now, "lastSummary": summary},
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
            {"cancelRequested": True, "status": "cancelling", "updatedAt": now},
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
        batch.set(self._task_ref(task_id), {"status": "waiting_approval", "updatedAt": now}, merge=True)
        batch.commit()
        return self._build_approval(approval_id, payload)

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
        self._task_ref(task_id).set({"status": "queued", "updatedAt": now}, merge=True)
        data.update(updates)
        return self._build_approval(approval_id, data)
