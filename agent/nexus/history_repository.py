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
from nexus.config import settings
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
    token_totals: dict[str, Any] | None = None
    token_tracking_started_at: datetime | None = None


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

    @staticmethod
    def _empty_token_totals() -> dict[str, Any]:
        return {
            "input": 0,
            "output": 0,
            "total": 0,
            "bySource": {},
        }

    @classmethod
    def _coerce_token_totals(cls, value: Any) -> dict[str, Any]:
        base = cls._empty_token_totals()
        if not isinstance(value, dict):
            return base

        by_source = value.get("bySource")
        normalized_sources: dict[str, Any] = {}
        if isinstance(by_source, dict):
            for key, raw in by_source.items():
                if not isinstance(key, str) or not isinstance(raw, dict):
                    continue
                normalized_sources[key] = {
                    "input": int(raw.get("input", 0) or 0),
                    "output": int(raw.get("output", 0) or 0),
                    "total": int(raw.get("total", 0) or 0),
                    "model": raw.get("model") if isinstance(raw.get("model"), str) else "",
                }

        base["input"] = int(value.get("input", 0) or 0)
        base["output"] = int(value.get("output", 0) or 0)
        base["total"] = int(value.get("total", 0) or 0)
        base["bySource"] = normalized_sources
        return base

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
            token_totals=self._coerce_token_totals(data.get("tokenTotals")),
            token_tracking_started_at=self._coerce_datetime(data.get("tokenTrackingStartedAt")),
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

    async def append_token_usage(
        self,
        *,
        session_id: str,
        owner_id: str,
        source: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
    ) -> None:
        await asyncio.to_thread(
            self._append_token_usage_sync,
            session_id,
            owner_id,
            source,
            model,
            input_tokens,
            output_tokens,
            total_tokens,
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

    async def list_recent_session_usage(self, owner_id: str, limit: int = 10) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_recent_session_usage_sync, owner_id, limit)

    async def list_active_sessions(self, owner_id: str, live_sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_active_sessions_sync, owner_id, live_sessions)

    async def get_session_messages(self, session_id: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._get_session_messages_sync, session_id)

    async def get_user_settings(self, uid: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_user_settings_sync, uid)

    async def update_user_settings(self, uid: str, updates: dict[str, Any]) -> None:
        return await asyncio.to_thread(self._update_user_settings_sync, uid, updates)

    async def get_user_quota(self, uid: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_user_quota_sync, uid)

    async def increment_user_token_usage(self, uid: str, tokens: int) -> dict[str, Any]:
        """Atomically increment user-level token usage. Returns updated quota."""
        return await asyncio.to_thread(self._increment_user_token_usage_sync, uid, tokens)

    async def get_persistent_sandbox(self, owner_id: str) -> str | None:
        """Return the paused sandbox ID for the user, or None if none exists."""
        return await asyncio.to_thread(self._get_persistent_sandbox_sync, owner_id)

    async def save_paused_sandbox(self, owner_id: str, sandbox_id: str | None) -> None:
        """Write (or clear) the user's paused sandbox ID in Firestore."""
        await asyncio.to_thread(self._save_paused_sandbox_sync, owner_id, sandbox_id)

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
            # Atomic create — sets createdAt and token quota only when the document is new.
            ref.create({
                **base_payload,
                "createdAt": now,
                "tokenUsage": 0,
                "tokenLimit": settings.default_token_limit,
            })
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
            "lastActiveAt": session.last_active,
            "sandboxId": session.sandbox_id or existing.get("sandboxId"),
            "schemaVersion": 1,
        }
        if not snapshot.exists:
            payload.update(
                {
                    "createdAt": session.created_at,
                    "messageCount": 0,
                    "title": "New session",
                    "tokenTotals": self._empty_token_totals(),
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

    def _append_token_usage_sync(
        self,
        session_id: str,
        owner_id: str,
        source: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
    ) -> None:
        if input_tokens < 0 or output_tokens < 0 or total_tokens < 0:
            return

        session_ref = self._db.collection("sessions").document(session_id)
        transaction = self._db.transaction()

        @firestore.transactional
        def transactional_append(txn):
            snapshot = session_ref.get(transaction=txn)
            if not snapshot.exists:
                raise ValueError(f"Session {session_id} does not exist")

            now = utcnow()
            data = snapshot.to_dict() or {}
            totals = self._coerce_token_totals(data.get("tokenTotals"))
            source_totals = totals["bySource"].get(
                source,
                {"input": 0, "output": 0, "total": 0, "model": model},
            )
            source_totals = {
                "input": int(source_totals.get("input", 0)) + input_tokens,
                "output": int(source_totals.get("output", 0)) + output_tokens,
                "total": int(source_totals.get("total", 0)) + total_tokens,
                "model": model or str(source_totals.get("model", "")),
            }
            totals["input"] += input_tokens
            totals["output"] += output_tokens
            totals["total"] += total_tokens
            totals["bySource"][source] = source_totals

            usage_ref = session_ref.collection("usage_events").document(
                f"{now.strftime('%Y%m%d%H%M%S%f')}-{uuid.uuid4().hex[:8]}"
            )
            txn.set(
                usage_ref,
                {
                    "ownerId": owner_id,
                    "sessionId": session_id,
                    "source": source,
                    "model": model,
                    "inputTokens": input_tokens,
                    "outputTokens": output_tokens,
                    "totalTokens": total_tokens,
                    "createdAt": now,
                },
            )
            updates: dict[str, Any] = {
                "tokenTotals": totals,
                "updatedAt": now,
            }
            if data.get("tokenTrackingStartedAt") is None:
                updates["tokenTrackingStartedAt"] = now
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
        token_totals = self._empty_token_totals()
        tracked_sources: set[str] = set()

        owner_sessions = self._list_owner_sessions_sync(owner_id)

        for _, data in owner_sessions:
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

            session_token_totals = self._coerce_token_totals(data.get("tokenTotals"))
            token_totals["input"] += session_token_totals["input"]
            token_totals["output"] += session_token_totals["output"]
            token_totals["total"] += session_token_totals["total"]
            tracked_sources.update(session_token_totals["bySource"].keys())

        avg_duration_mins = (total_duration_secs / 60) / ended_sessions_count if ended_sessions_count > 0 else 0

        return {
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "active_sessions": active_sessions,
            "sessions_this_week": sessions_this_week,
            "avg_session_duration_mins": round(avg_duration_mins, 1),
            "token_totals": token_totals,
            "tracked_sources": sorted(tracked_sources),
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
            day: {
                "date": day,
                "sessions": 0,
                "messages": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }
            for day in chart_days
        }

        owner_sessions = self._list_owner_sessions_sync(owner_id)

        for _, data in owner_sessions:
            if data.get("status") == "deleted":
                continue

            created_at = self._coerce_datetime(data.get("createdAt"))
            if not created_at or created_at < start_date:
                continue

            date_str = created_at.date().isoformat()
            if date_str in chart_data:
                chart_data[date_str]["sessions"] += 1
                chart_data[date_str]["messages"] += int(data.get("messageCount", 0))

        for session_id, data in owner_sessions:
            if data.get("status") == "deleted":
                continue

            created_at = self._coerce_datetime(data.get("createdAt"))
            last_active_at = self._coerce_datetime(data.get("lastActiveAt"))
            if created_at and created_at < start_date and (not last_active_at or last_active_at < start_date):
                continue

            usage_events = (
                self._db.collection("sessions")
                .document(session_id)
                .collection("usage_events")
                .stream()
            )
            for doc in usage_events:
                data = doc.to_dict() or {}
                created_at = self._coerce_datetime(data.get("createdAt"))
                if not created_at or created_at < start_date:
                    continue
                date_str = created_at.date().isoformat()
                if date_str not in chart_data:
                    continue
                chart_data[date_str]["input_tokens"] += int(data.get("inputTokens", 0) or 0)
                chart_data[date_str]["output_tokens"] += int(data.get("outputTokens", 0) or 0)
                chart_data[date_str]["total_tokens"] += int(data.get("totalTokens", 0) or 0)

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

    def _list_recent_session_usage_sync(self, owner_id: str, limit: int) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for session in self._list_sessions_sync(owner_id, limit, None, None):
            results.append(
                {
                    "session_id": session.session_id,
                    "title": session.title,
                    "status": session.status,
                    "created_at": session.created_at,
                    "message_count": session.message_count,
                    "token_totals": session.token_totals or self._empty_token_totals(),
                    "token_tracking_started_at": session.token_tracking_started_at,
                    "token_coverage": "tracked" if session.token_tracking_started_at else "no_data",
                }
            )
        return results

    def _list_active_sessions_sync(self, owner_id: str, live_sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for live in live_sessions:
            if live.get("owner_id") != owner_id:
                continue
            session_id = str(live.get("session_id", ""))
            stored_session = self._get_session_sync(session_id) if session_id else None
            token_totals = (
                stored_session.token_totals
                if stored_session and stored_session.token_totals
                else self._empty_token_totals()
            )
            results.append(
                {
                    "session_id": session_id,
                    "title": stored_session.title if stored_session else "New session",
                    "status": live.get("status", "active"),
                    "created_at": live.get("created_at"),
                    "last_active_at": live.get("last_active_at"),
                    "stream_url": live.get("stream_url"),
                    "message_count": stored_session.message_count if stored_session else 0,
                    "token_totals": token_totals,
                    "token_tracking_started_at": (
                        stored_session.token_tracking_started_at if stored_session else None
                    ),
                    "token_coverage": (
                        "tracked"
                        if stored_session and stored_session.token_tracking_started_at
                        else "no_data"
                    ),
                }
            )

        results.sort(
            key=lambda item: self._coerce_datetime(item.get("last_active_at")) or utcnow(),
            reverse=True,
        )
        return results

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

    def _get_user_quota_sync(self, uid: str) -> dict[str, Any]:
        doc = self._db.collection("users").document(uid).get()
        if not doc.exists:
            return {
                "limit": settings.default_token_limit,
                "used": 0,
                "remaining": settings.default_token_limit,
            }
        data = doc.to_dict() or {}
        limit = int(data.get("tokenLimit", settings.default_token_limit) or settings.default_token_limit)
        used = int(data.get("tokenUsage", 0) or 0)
        return {
            "limit": limit,
            "used": used,
            "remaining": max(0, limit - used),
        }

    def _increment_user_token_usage_sync(self, uid: str, tokens: int) -> dict[str, Any]:
        if tokens <= 0:
            return self._get_user_quota_sync(uid)

        ref = self._db.collection("users").document(uid)
        ref.update({"tokenUsage": firestore.Increment(tokens)})
        return self._get_user_quota_sync(uid)

    def _get_persistent_sandbox_sync(self, owner_id: str) -> str | None:
        doc = self._db.collection("users").document(owner_id).get()
        if not doc.exists:
            return None
        return (doc.to_dict() or {}).get("pausedSandboxId") or None

    def _save_paused_sandbox_sync(self, owner_id: str, sandbox_id: str | None) -> None:
        ref = self._db.collection("users").document(owner_id)
        if sandbox_id:
            ref.set({"pausedSandboxId": sandbox_id}, merge=True)
        else:
            ref.set({"pausedSandboxId": None}, merge=True)
