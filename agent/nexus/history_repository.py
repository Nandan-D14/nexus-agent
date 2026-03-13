"""Firestore-backed persistence for users, sessions, and message history."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from firebase_admin import firestore
from google.api_core.exceptions import AlreadyExists
from google.cloud.firestore_v1 import FieldFilter

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
    title: str = "Untitled session"
    summary: str | None = None
    message_count: int = 0


class FirestoreHistoryRepository:
    """Sync Firestore access wrapped with async-friendly helpers."""

    @property
    def _db(self):
        return get_firestore_client()

    @staticmethod
    def _coerce_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        if hasattr(value, "timestamp"):
            try:
                return datetime.fromtimestamp(value.timestamp(), tz=timezone.utc)
            except (OSError, OverflowError, TypeError, ValueError):
                return None
        return None

    def _build_stored_session(self, session_id: str, data: dict[str, Any]) -> StoredSession:
        title = data.get("title")
        summary = data.get("summary")
        return StoredSession(
            session_id=session_id,
            owner_id=data.get("ownerId", ""),
            status=data.get("status", "ended"),
            created_at=self._coerce_datetime(data.get("createdAt")) or utcnow(),
            ended_at=self._coerce_datetime(data.get("endedAt")),
            title=title.strip() if isinstance(title, str) and title.strip() else "Untitled session",
            summary=summary if isinstance(summary, str) else None,
            message_count=int(data.get("messageCount", 0)),
        )

    def _list_owner_sessions_sync(self, owner_id: str) -> list[tuple[str, dict[str, Any]]]:
        sessions = (
            self._db.collection("sessions")
            .where(filter=FieldFilter("ownerId", "==", owner_id))
            .stream()
        )
        return [(doc.id, doc.to_dict() or {}) for doc in sessions]

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

    async def get_dashboard_stats(self, owner_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_dashboard_stats_sync, owner_id)

    async def get_dashboard_usage(self, owner_id: str, days: int = 30) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._get_dashboard_usage_sync, owner_id, days)

    async def list_sessions(self, owner_id: str, limit: int = 25, status: str | None = None, search: str | None = None) -> list[StoredSession]:
        return await asyncio.to_thread(self._list_sessions_sync, owner_id, limit, status, search)

    async def get_session_messages(self, session_id: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._get_session_messages_sync, session_id)

    async def get_user_settings(self, uid: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_user_settings_sync, uid)

    async def update_user_settings(self, uid: str, updates: dict[str, Any]) -> None:
        return await asyncio.to_thread(self._update_user_settings_sync, uid, updates)

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
        return self._build_stored_session(session_id, data)

    def _get_dashboard_stats_sync(self, owner_id: str) -> dict[str, Any]:
        from datetime import timedelta
        now = utcnow()
        week_ago = now - timedelta(days=7)

        total_sessions = 0
        total_messages = 0
        active_sessions = 0
        sessions_this_week = 0
        total_duration_secs = 0
        ended_sessions_count = 0

        for _, data in self._list_owner_sessions_sync(owner_id):
            if data.get("status") == "deleted":
                continue

            total_sessions += 1
            total_messages += int(data.get("messageCount", 0))

            if data.get("status") in ("active", "ready"):
                active_sessions += 1

            created_at = self._coerce_datetime(data.get("createdAt"))
            if created_at and created_at > week_ago:
                sessions_this_week += 1

            ended_at = self._coerce_datetime(data.get("endedAt"))
            if created_at and ended_at:
                try:
                    duration = (ended_at - created_at).total_seconds()
                    if duration > 0:
                        total_duration_secs += duration
                        ended_sessions_count += 1
                except Exception:
                    pass

        avg_duration_mins = (total_duration_secs / 60) / ended_sessions_count if ended_sessions_count > 0 else 0

        return {
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "active_sessions": active_sessions,
            "sessions_this_week": sessions_this_week,
            "avg_session_duration_mins": round(avg_duration_mins, 1)
        }

    def _get_dashboard_usage_sync(self, owner_id: str, days: int) -> list[dict[str, Any]]:
        from datetime import timedelta
        now = utcnow()
        start_date = now - timedelta(days=days)

        # Initialize chart with empty days
        chart_days = [
            (now - timedelta(days=offset)).date().isoformat()
            for offset in range(days - 1, -1, -1)
        ]
        chart_data = {
            day: {"date": day, "sessions": 0, "messages": 0}
            for day in chart_days
        }

        for _, data in self._list_owner_sessions_sync(owner_id):
            if data.get("status") == "deleted":
                continue

            created_at = self._coerce_datetime(data.get("createdAt"))
            if not created_at or created_at < start_date:
                continue

            date_str = created_at.date().isoformat()
            if date_str in chart_data:
                chart_data[date_str]["sessions"] += 1
                chart_data[date_str]["messages"] += int(data.get("messageCount", 0))

        # Return sorted list naturally by date key
        return [chart_data[d] for d in sorted(chart_data.keys())]

    def _list_sessions_sync(self, owner_id: str, limit: int, status: str | None, search: str | None) -> list[StoredSession]:
        if status == "deleted":
            return []

        search_text = search.strip().lower() if search else None
        sessions: list[tuple[datetime, StoredSession]] = []

        for session_id, data in self._list_owner_sessions_sync(owner_id):
            session_status = data.get("status", "ended")
            if session_status == "deleted":
                continue
            if status and session_status != status:
                continue

            title = data.get("title", "")
            summary = data.get("summary", "")

            # Application-side search filtering (since Firestore lacks full-text search)
            if search_text:
                title_text = title.lower() if isinstance(title, str) else ""
                summary_text = summary.lower() if isinstance(summary, str) else ""
                if search_text not in title_text and search_text not in summary_text:
                    continue

            updated_at = self._coerce_datetime(data.get("updatedAt"))
            created_at = self._coerce_datetime(data.get("createdAt"))
            sort_key = updated_at or created_at or datetime.min.replace(tzinfo=timezone.utc)
            sessions.append((sort_key, self._build_stored_session(session_id, data)))

        sessions.sort(key=lambda item: item[0], reverse=True)
        return [session for _, session in sessions[:limit]]

    def _get_session_messages_sync(self, session_id: str) -> list[dict[str, Any]]:
        messages_docs = self._db.collection("sessions").document(session_id).collection("messages").order_by("turnIndex").stream()
        results = []
        for doc in messages_docs:
            data = doc.to_dict()
            results.append({
                "id": doc.id,
                "role": data.get("role"),
                "source": data.get("source"),
                "text": data.get("text"),
                "createdAt": data.get("createdAt"),
                "turnIndex": data.get("turnIndex")
            })
        return results

    def _get_user_settings_sync(self, uid: str) -> dict[str, Any]:
        doc = self._db.collection("users").document(uid).get()
        if not doc.exists:
            return {}
        return doc.to_dict()

    def _update_user_settings_sync(self, uid: str, updates: dict[str, Any]) -> None:
        # updates can contain nested dot-notation fields like "settings.voiceId" 
        # which firestore handles natively in update() but for set(merge=True) we need to pass a dict
        # Actually set(merge=True) requires a nested dict if using dict format, OR we can use update()
        ref = self._db.collection("users").document(uid)
        
        # We'll try update first, if doc not found we'll fallback to creating it
        try:
            ref.update(updates)
        except Exception:
            # Simple conversion of dot-notation for merge=True fallback (basic)
            nested_updates = {}
            for k, v in updates.items():
                if "." in k:
                    parts = k.split(".")
                    curr = nested_updates
                    for part in parts[:-1]:
                        curr = curr.setdefault(part, {})
                    curr[parts[-1]] = v
                else:
                    nested_updates[k] = v
            ref.set(nested_updates, merge=True)

