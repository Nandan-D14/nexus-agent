# Proprietary and non-commercial use only.

"""Durable human-approval creation, resolution, and consumption."""

from __future__ import annotations

import asyncio
from typing import Any

from firebase_admin import firestore
from google.cloud.firestore_v1 import FieldFilter

from nexus.production_tasks import (
    DurableApproval,
    BoundProductionStore,
    _uuid,
    canonicalize_task_status,
    guarded_write,
    run_with_write_retry,
    utcnow,
)


class ApprovalStore(BoundProductionStore):
    async def create_approval(
        self,
        *,
        task_id: str,
        owner_id: str,
        description: str,
        risk: str,
        metadata: dict[str, Any] | None = None,
    ) -> DurableApproval:
        async with guarded_write(task_id):
            return await asyncio.to_thread(
                run_with_write_retry,
                lambda: self._create_approval_sync(
                    task_id,
                    owner_id,
                    description,
                    risk,
                    metadata,
                ),
                description="create_approval",
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
        run_id = (
            str((metadata or {}).get("run_id") or "").strip() or None
        )
        self._append_event_sync(
            task_id,
            owner_id,
            "approval_requested",
            {
                "approval_id": approval_id,
                "description": description,
                "risk": risk,
                "metadata": metadata or {},
            },
            run_id,
            True,
        )
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

    async def list_approvals(
        self,
        *,
        task_id: str,
        owner_id: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[DurableApproval]:
        return await asyncio.to_thread(
            self._list_approvals_sync,
            task_id,
            owner_id,
            status,
            limit,
        )

    def _list_approvals_sync(
        self,
        task_id: str,
        owner_id: str,
        status: str | None,
        limit: int,
    ) -> list[DurableApproval]:
        task = self._get_task_sync(task_id)
        if task is None or task.owner_id != owner_id:
            return []
        query = self._task_ref(task_id).collection("approvals")
        if status:
            query = query.where(filter=FieldFilter("status", "==", status))
        query = query.limit(max(1, min(int(limit), 200)))
        approvals = []
        for doc in query.stream():
            data = doc.to_dict() or {}
            if data.get("ownerId") == owner_id:
                approvals.append(self._build_approval(doc.id, data))
        approvals.sort(key=lambda item: item.created_at, reverse=True)
        return approvals

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
        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        run_id = str(metadata.get("run_id") or "").strip() or None
        self._append_event_sync(
            task_id,
            owner_id,
            "approval_resolved",
            {
                "approval_id": approval_id,
                "approved": approved,
                "status": updates["status"],
                "action_hash": metadata.get("action_hash"),
                "tool": metadata.get("tool"),
                "decided_at": int(now.timestamp() * 1000),
            },
            run_id,
            True,
        )
        return self._build_approval(approval_id, data)

    async def consume_approved_action(
        self,
        *,
        task_id: str,
        owner_id: str,
        action_hash: str,
        approval_id: str | None = None,
    ) -> DurableApproval | None:
        """Atomically consume one exact approved or denied tool decision."""
        async with guarded_write(task_id):
            return await asyncio.to_thread(
                run_with_write_retry,
                lambda: self._consume_approved_action_sync(
                    task_id,
                    owner_id,
                    action_hash,
                    approval_id,
                ),
                description="consume_approved_action",
            )

    def _consume_approved_action_sync(
        self,
        task_id: str,
        owner_id: str,
        action_hash: str,
        approval_id: str | None,
    ) -> DurableApproval | None:
        candidates = []
        if approval_id:
            candidates = [self._approval_ref(task_id, approval_id).get()]
        else:
            query = self._task_ref(task_id).collection("approvals")
            candidates = list(query.stream())
        selected = None
        for doc in candidates:
            if not doc.exists:
                continue
            data = doc.to_dict() or {}
            metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
            if data.get("ownerId") != owner_id:
                continue
            if data.get("status") not in {"approved", "denied"}:
                continue
            if str(metadata.get("action_hash") or "") != action_hash:
                continue
            if data.get("consumedAt") is not None:
                continue
            selected = doc
            break
        if selected is None:
            return None

        approval_ref = self._approval_ref(task_id, selected.id)
        transaction = self._db.transaction()
        now = utcnow()

        @firestore.transactional
        def transactional_consume(txn):
            current = approval_ref.get(transaction=txn)
            if not current.exists:
                return None
            data = current.to_dict() or {}
            metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
            if (
                data.get("ownerId") != owner_id
                or data.get("status") not in {"approved", "denied"}
                or data.get("consumedAt") is not None
                or str(metadata.get("action_hash") or "") != action_hash
            ):
                return None
            txn.set(approval_ref, {"consumedAt": now}, merge=True)
            data["consumedAt"] = now
            return self._build_approval(selected.id, data)

        return transactional_consume(transaction)
