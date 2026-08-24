# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Firestore persistence and leases for hidden background subagents."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import uuid
from typing import Any

from firebase_admin import firestore
from google.cloud.firestore_v1 import FieldFilter

from nexus.config import settings
from nexus.firebase import get_firestore_client
from nexus.firestore_concurrency import run_with_write_retry


TERMINAL_SUBAGENT_STATUSES = frozenset(
    {"completed", "failed", "cancelled"}
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _message(text: str, *, kind: str = "mailbox") -> dict[str, Any]:
    return {
        "messageId": f"msg_{uuid.uuid4().hex[:12]}",
        "text": text[:8_000],
        "kind": kind,
        "status": "pending",
        "createdAt": utcnow(),
    }


class FirestoreSubagentRepository:
    """Top-level records allow restart recovery without parent object state."""

    def __init__(self, db: Any = None) -> None:
        self._custom_db = db

    @property
    def _db(self):
        if self._custom_db is not None:
            return self._custom_db
        return get_firestore_client()

    @_db.setter
    def _db(self, value: Any) -> None:
        self._custom_db = value

    def _ref(self, subagent_id: str):
        return self._db.collection("subagent_records").document(subagent_id)

    async def create_record(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(
            run_with_write_retry,
            lambda: self._create_record_sync(payload),
            description="subagent_create",
        )

    def _create_record_sync(self, payload: dict[str, Any]) -> dict[str, Any]:
        subagent_id = str(payload["subagentId"])
        ref = self._ref(subagent_id)
        transaction = self._db.transaction()
        now = utcnow()

        @firestore.transactional
        def transactional_create(txn):
            existing = ref.get(transaction=txn)
            if existing.exists:
                raise ValueError(f"Subagent already exists: {subagent_id}")
            data = {
                **payload,
                "status": "queued",
                "result": None,
                "error": None,
                "stepId": payload.get("stepId"),
                "terminalRecorded": False,
                "resultConsumed": False,
                "claimGeneration": 0,
                "leaseOwner": None,
                "leaseExpiresAt": None,
                "checkpoint": {
                    "turnCount": 0,
                    "lastMessageId": None,
                    "lastResult": None,
                },
                "mailbox": [_message(str(payload.get("prompt") or ""), kind="initial")],
                "createdAt": now,
                "updatedAt": now,
            }
            txn.set(ref, data)
            return data

        return transactional_create(transaction)

    async def get_record(
        self,
        *,
        subagent_id: str,
        owner_id: str,
    ) -> dict[str, Any] | None:
        return await asyncio.to_thread(
            self._get_record_sync,
            subagent_id,
            owner_id,
        )

    def _get_record_sync(
        self,
        subagent_id: str,
        owner_id: str,
    ) -> dict[str, Any] | None:
        doc = self._ref(subagent_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        if data.get("ownerId") != owner_id:
            return None
        return data

    async def list_for_parent(
        self,
        *,
        parent_session_id: str,
        parent_run_id: str,
        owner_id: str,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._list_for_parent_sync,
            parent_session_id,
            parent_run_id,
            owner_id,
        )

    def _list_for_parent_sync(
        self,
        parent_session_id: str,
        parent_run_id: str,
        owner_id: str,
    ) -> list[dict[str, Any]]:
        query = self._db.collection("subagent_records").where(
            filter=FieldFilter(
                "parentSessionId",
                "==",
                parent_session_id,
            )
        )
        records = []
        for doc in query.stream():
            data = doc.to_dict() or {}
            if (
                data.get("ownerId") == owner_id
                and data.get("parentSessionId") == parent_session_id
                and data.get("parentRunId") == parent_run_id
            ):
                records.append(data)
        records.sort(key=lambda item: item.get("createdAt") or utcnow())
        return records

    async def claim(
        self,
        *,
        subagent_id: str,
        owner_id: str,
        worker_id: str,
    ) -> dict[str, Any] | None:
        return await asyncio.to_thread(
            run_with_write_retry,
            lambda: self._claim_sync(subagent_id, owner_id, worker_id),
            description="subagent_claim",
        )

    def _claim_sync(
        self,
        subagent_id: str,
        owner_id: str,
        worker_id: str,
    ) -> dict[str, Any] | None:
        ref = self._ref(subagent_id)
        transaction = self._db.transaction()
        now = utcnow()

        @firestore.transactional
        def transactional_claim(txn):
            doc = ref.get(transaction=txn)
            if not doc.exists:
                return None
            data = doc.to_dict() or {}
            if data.get("ownerId") != owner_id:
                return None
            status = str(data.get("status") or "queued")
            mailbox = list(data.get("mailbox") or [])
            has_pending = any(
                isinstance(item, dict)
                and item.get("status") in {"pending", "processing"}
                for item in mailbox
            )
            if status in {"cancelled", "failed"}:
                return None
            if status == "completed" and not has_pending:
                return None
            lease_expiry = data.get("leaseExpiresAt")
            if (
                status == "running"
                and isinstance(lease_expiry, datetime)
                and lease_expiry > now
            ):
                return None
            generation = int(data.get("claimGeneration", 0) or 0) + 1
            for item in mailbox:
                if (
                    isinstance(item, dict)
                    and item.get("status") == "processing"
                ):
                    item["status"] = "pending"
                    item.pop("processingGeneration", None)
                    item.pop("processingStartedAt", None)
            updates = {
                "status": "running",
                "claimGeneration": generation,
                "leaseOwner": worker_id,
                "leaseExpiresAt": now
                + timedelta(seconds=settings.subagent_lease_seconds),
                "lastHeartbeatAt": now,
                "mailbox": mailbox,
                "startedAt": data.get("startedAt") or now,
                "updatedAt": now,
            }
            txn.set(ref, updates, merge=True)
            data.update(updates)
            return data

        return transactional_claim(transaction)

    async def renew_lease(
        self,
        *,
        subagent_id: str,
        owner_id: str,
        worker_id: str,
        claim_generation: int,
    ) -> bool:
        return await asyncio.to_thread(
            run_with_write_retry,
            lambda: self._renew_lease_sync(
                subagent_id, owner_id, worker_id, claim_generation
            ),
            description="subagent_renew_lease",
        )

    def _renew_lease_sync(
        self,
        subagent_id: str,
        owner_id: str,
        worker_id: str,
        claim_generation: int,
    ) -> bool:
        ref = self._ref(subagent_id)
        transaction = self._db.transaction()
        now = utcnow()

        @firestore.transactional
        def transactional_renew(txn):
            doc = ref.get(transaction=txn)
            if not doc.exists:
                return False
            data = doc.to_dict() or {}
            if (
                data.get("ownerId") != owner_id
                or data.get("status") != "running"
                or data.get("leaseOwner") != worker_id
                or int(data.get("claimGeneration", 0) or 0)
                != int(claim_generation)
            ):
                return False
            txn.set(
                ref,
                {
                    "leaseExpiresAt": now
                    + timedelta(seconds=settings.subagent_lease_seconds),
                    "lastHeartbeatAt": now,
                    "updatedAt": now,
                },
                merge=True,
            )
            return True

        return bool(transactional_renew(transaction))

    async def append_message(
        self,
        *,
        subagent_id: str,
        owner_id: str,
        text: str,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            run_with_write_retry,
            lambda: self._append_message_sync(subagent_id, owner_id, text),
            description="subagent_append_message",
        )

    def _append_message_sync(
        self,
        subagent_id: str,
        owner_id: str,
        text: str,
    ) -> dict[str, Any]:
        ref = self._ref(subagent_id)
        transaction = self._db.transaction()
        message = _message(text)
        now = utcnow()

        @firestore.transactional
        def transactional_append(txn):
            doc = ref.get(transaction=txn)
            if not doc.exists:
                raise KeyError(f"Unknown subagent {subagent_id}")
            data = doc.to_dict() or {}
            if data.get("ownerId") != owner_id:
                raise KeyError(f"Unknown subagent {subagent_id}")
            if data.get("status") in {"cancelled", "failed"}:
                raise RuntimeError(
                    f"Cannot message {data.get('status')} subagent"
                )
            mailbox = list(data.get("mailbox") or [])
            active_count = sum(
                1
                for item in mailbox
                if isinstance(item, dict)
                and item.get("status") in {"pending", "processing"}
            )
            mailbox_limit = max(
                4,
                settings.subagent_max_mailbox_messages,
            )
            if active_count >= mailbox_limit:
                raise RuntimeError("Subagent mailbox is full.")
            mailbox.append(message)
            while len(mailbox) > mailbox_limit:
                completed_index = next(
                    (
                        index
                        for index, item in enumerate(mailbox)
                        if isinstance(item, dict)
                        and item.get("status") == "completed"
                    ),
                    None,
                )
                if completed_index is None:
                    break
                mailbox.pop(completed_index)
            updates = {"mailbox": mailbox, "updatedAt": now}
            if data.get("status") == "completed":
                updates["status"] = "queued"
                updates["resultConsumed"] = False
            txn.set(ref, updates, merge=True)
            return message

        return transactional_append(transaction)

    async def claim_next_message(
        self,
        *,
        subagent_id: str,
        owner_id: str,
        worker_id: str,
        claim_generation: int,
    ) -> dict[str, Any] | None:
        return await asyncio.to_thread(
            run_with_write_retry,
            lambda: self._claim_next_message_sync(
                subagent_id, owner_id, worker_id, claim_generation
            ),
            description="subagent_claim_next_message",
        )

    def _claim_next_message_sync(
        self,
        subagent_id: str,
        owner_id: str,
        worker_id: str,
        claim_generation: int,
    ) -> dict[str, Any] | None:
        ref = self._ref(subagent_id)
        transaction = self._db.transaction()
        now = utcnow()

        @firestore.transactional
        def transactional_next(txn):
            doc = ref.get(transaction=txn)
            if not doc.exists:
                return None
            data = doc.to_dict() or {}
            if (
                data.get("ownerId") != owner_id
                or data.get("leaseOwner") != worker_id
                or int(data.get("claimGeneration", 0) or 0)
                != int(claim_generation)
            ):
                return None
            mailbox = list(data.get("mailbox") or [])
            selected = None
            for item in mailbox:
                if isinstance(item, dict) and item.get("status") == "pending":
                    item["status"] = "processing"
                    item["processingGeneration"] = claim_generation
                    item["processingStartedAt"] = now
                    selected = dict(item)
                    break
            if selected is None:
                return None
            txn.set(
                ref,
                {"mailbox": mailbox, "updatedAt": now},
                merge=True,
            )
            return selected

        return transactional_next(transaction)

    async def complete_message(
        self,
        *,
        subagent_id: str,
        owner_id: str,
        worker_id: str,
        claim_generation: int,
        message_id: str,
        result: str | None,
    ) -> bool:
        return await asyncio.to_thread(
            run_with_write_retry,
            lambda: self._complete_message_sync(
                subagent_id,
                owner_id,
                worker_id,
                claim_generation,
                message_id,
                result,
            ),
            description="subagent_complete_message",
        )

    def _complete_message_sync(
        self,
        subagent_id: str,
        owner_id: str,
        worker_id: str,
        claim_generation: int,
        message_id: str,
        result: str | None,
    ) -> bool:
        ref = self._ref(subagent_id)
        transaction = self._db.transaction()
        now = utcnow()

        @firestore.transactional
        def transactional_complete(txn):
            doc = ref.get(transaction=txn)
            if not doc.exists:
                return False
            data = doc.to_dict() or {}
            if (
                data.get("ownerId") != owner_id
                or data.get("leaseOwner") != worker_id
                or int(data.get("claimGeneration", 0) or 0)
                != int(claim_generation)
            ):
                return False
            mailbox = list(data.get("mailbox") or [])
            found = False
            for item in mailbox:
                if (
                    isinstance(item, dict)
                    and item.get("messageId") == message_id
                    and item.get("status") == "processing"
                ):
                    item["status"] = "completed"
                    item["completedAt"] = now
                    found = True
                    break
            if not found:
                return False
            checkpoint = (
                dict(data.get("checkpoint") or {})
                if isinstance(data.get("checkpoint"), dict)
                else {}
            )
            checkpoint.update(
                {
                    "turnCount": int(checkpoint.get("turnCount", 0) or 0) + 1,
                    "lastMessageId": message_id,
                    "lastResult": (result or "")[:4000],
                    "updatedAt": now,
                }
            )
            txn.set(
                ref,
                {
                    "mailbox": mailbox,
                    "checkpoint": checkpoint,
                    "result": (result or "")[:20_000] or None,
                    "updatedAt": now,
                },
                merge=True,
            )
            return True

        return bool(transactional_complete(transaction))

    async def update_record(
        self,
        *,
        subagent_id: str,
        owner_id: str,
        updates: dict[str, Any],
    ) -> bool:
        return await asyncio.to_thread(
            run_with_write_retry,
            lambda: self._update_record_sync(subagent_id, owner_id, updates),
            description="subagent_update_record",
        )

    def _update_record_sync(
        self,
        subagent_id: str,
        owner_id: str,
        updates: dict[str, Any],
    ) -> bool:
        ref = self._ref(subagent_id)
        doc = ref.get()
        if not doc.exists or (doc.to_dict() or {}).get("ownerId") != owner_id:
            return False
        ref.set({**updates, "updatedAt": utcnow()}, merge=True)
        return True

    async def mark_terminal(
        self,
        *,
        subagent_id: str,
        owner_id: str,
        status: str,
        result: str | None,
        error: str | None,
        terminal_recorded: bool,
        worker_id: str | None = None,
        claim_generation: int | None = None,
    ) -> bool:
        if status not in TERMINAL_SUBAGENT_STATUSES:
            raise ValueError(f"Invalid terminal subagent status: {status}")
        return await asyncio.to_thread(
            run_with_write_retry,
            lambda: self._mark_terminal_sync(
                subagent_id,
                owner_id,
                status,
                result,
                error,
                terminal_recorded,
                worker_id,
                claim_generation,
            ),
            description="subagent_mark_terminal",
        )

    def _mark_terminal_sync(
        self,
        subagent_id: str,
        owner_id: str,
        status: str,
        result: str | None,
        error: str | None,
        terminal_recorded: bool,
        worker_id: str | None,
        claim_generation: int | None,
    ) -> bool:
        ref = self._ref(subagent_id)
        transaction = self._db.transaction()
        now = utcnow()

        @firestore.transactional
        def transactional_terminal(txn):
            doc = ref.get(transaction=txn)
            if not doc.exists:
                return False
            data = doc.to_dict() or {}
            if data.get("ownerId") != owner_id:
                return False
            if worker_id is not None and data.get("leaseOwner") != worker_id:
                return False
            if (
                claim_generation is not None
                and int(data.get("claimGeneration", 0) or 0)
                != int(claim_generation)
            ):
                return False
            txn.set(
                ref,
                {
                    "status": status,
                    "result": (result or "")[:20_000] or None,
                    "error": (error or "")[:4_000] or None,
                    "terminalRecorded": terminal_recorded,
                    "resultConsumed": False,
                    "leaseOwner": None,
                    "leaseExpiresAt": None,
                    "completedAt": now,
                    "updatedAt": now,
                },
                merge=True,
            )
            return True

        return bool(transactional_terminal(transaction))


__all__ = [
    "FirestoreSubagentRepository",
    "TERMINAL_SUBAGENT_STATUSES",
]
