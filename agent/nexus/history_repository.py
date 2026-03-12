"""Firestore-backed persistence for users, sessions, and message history."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from firebase_admin import firestore
from google.api_core.exceptions import AlreadyExists

from nexus.auth import AuthenticatedUser
from nexus.firebase import get_firestore_client

if TYPE_CHECKING:
    from nexus.session import Session


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class StoredSession:
    session_id: str
    owner_id: str
    status: str
    created_at: datetime
    ended_at: datetime | None = None
    summary: str | None = None
    message_count: int = 0


class FirestoreHistoryRepository:
    """Sync Firestore access wrapped with async-friendly helpers."""

    @property
    def _db(self):
        return get_firestore_client()

    async def upsert_user(self, user: AuthenticatedUser) -> None:
        await asyncio.to_thread(self._upsert_user_sync, user)

    async def upsert_session(
        self,
        session: "Session",
        *,
        status: str,
        ended_at: datetime | None = None,
        error_code: str | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._upsert_session_sync,
            session,
            status,
            ended_at,
            error_code,
        )

    async def append_message(
        self,
        *,
        session_id: str,
        owner_id: str,
        role: str,
        source: str,
        text: str,
    ) -> None:
        await asyncio.to_thread(
            self._append_message_sync,
            session_id,
            owner_id,
            role,
            source,
            text,
        )

    async def mark_session_summary(
        self,
        session_id: str,
        *,
        summary: str,
        status: str | None = None,
        error_code: str | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._mark_session_summary_sync,
            session_id,
            summary,
            status,
            error_code,
        )

    async def get_session(self, session_id: str) -> StoredSession | None:
        return await asyncio.to_thread(self._get_session_sync, session_id)

    def _upsert_user_sync(self, user: AuthenticatedUser) -> None:
        now = utcnow()
        ref = self._db.collection("users").document(user.uid)
        base_payload: dict[str, Any] = {
            "uid": user.uid,
            "email": user.email,
            "displayName": user.display_name,
            "photoURL": user.photo_url,
            "lastLoginAt": now,
        }
        try:
            # Atomic create — sets createdAt only when the document is new.
            ref.create({**base_payload, "createdAt": now})
        except AlreadyExists:
            # Document already exists; update mutable fields only.
            ref.set(base_payload, merge=True)

    def _upsert_session_sync(
        self,
        session: "Session",
        status: str,
        ended_at: datetime | None,
        error_code: str | None,
    ) -> None:
        ref = self._db.collection("sessions").document(session.id)
        snapshot = ref.get()
        existing = snapshot.to_dict() if snapshot.exists else {}
        now = utcnow()
        payload: dict[str, Any] = {
            "ownerId": session.owner_id,
            "memberIds": [session.owner_id],
            "status": status,
            "updatedAt": now,
            "sandboxId": session.sandbox_id or existing.get("sandboxId"),
            "schemaVersion": 1,
        }
        if not snapshot.exists:
            payload.update(
                {
                    "createdAt": session.created_at,
                    "messageCount": 0,
                    "title": "New session",
                }
            )
        if ended_at:
            payload["endedAt"] = ended_at
        if error_code:
            payload["lastErrorCode"] = error_code
        ref.set(payload, merge=True)

    def _append_message_sync(
        self,
        session_id: str,
        owner_id: str,
        role: str,
        source: str,
        text: str,
    ) -> None:
        session_ref = self._db.collection("sessions").document(session_id)
        transaction = self._db.transaction()

        @firestore.transactional
        def transactional_append(txn):
            snapshot = session_ref.get(transaction=txn)
            if not snapshot.exists:
                raise ValueError(f"Session {session_id} does not exist")

            data = snapshot.to_dict() or {}
            next_index = int(data.get("messageCount", 0)) + 1
            now = utcnow()
            message_id = f"{next_index:06d}-{uuid.uuid4().hex[:8]}"
            message_ref = session_ref.collection("messages").document(message_id)

            txn.set(
                message_ref,
                {
                    "role": role,
                    "source": source,
                    "text": text,
                    "createdAt": now,
                    "turnIndex": next_index,
                    "ownerId": owner_id,
                },
            )

            updates: dict[str, Any] = {
                "messageCount": next_index,
                "updatedAt": now,
            }
            if role == "user":
                updates["lastUserAt"] = now
                if data.get("title") in (None, "", "New session"):
                    updates["title"] = text[:80]
            elif role == "agent":
                updates["lastAgentAt"] = now
            txn.set(session_ref, updates, merge=True)

        transactional_append(transaction)

    def _mark_session_summary_sync(
        self,
        session_id: str,
        summary: str,
        status: str | None,
        error_code: str | None,
    ) -> None:
        updates: dict[str, Any] = {
            "summary": summary[:500],
            "updatedAt": utcnow(),
        }
        if status:
            updates["status"] = status
        if error_code:
            updates["lastErrorCode"] = error_code
        self._db.collection("sessions").document(session_id).set(updates, merge=True)

    def _get_session_sync(self, session_id: str) -> StoredSession | None:
        snapshot = self._db.collection("sessions").document(session_id).get()
        if not snapshot.exists:
            return None

        data = snapshot.to_dict() or {}
        created_at = data.get("createdAt") or utcnow()
        ended_at = data.get("endedAt")

        return StoredSession(
            session_id=session_id,
            owner_id=data.get("ownerId", ""),
            status=data.get("status", "ended"),
            created_at=created_at,
            ended_at=ended_at,
            summary=data.get("summary"),
            message_count=int(data.get("messageCount", 0)),
        )
