# Proprietary and non-commercial use only.

"""Audit logging and GDPR-style user data export/delete."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from nexus._firestore_base import FirestoreRepoBase

logger = logging.getLogger(__name__)

# Never hand credentials back in a data export, even encrypted ones.
_EXPORT_REDACTED_KEYS = frozenset({
    "byok",
    "googleDriveRefreshToken",
    "googleDriveTokens",
    "integrations",
    "token",
    "apiKey",
    "bearerToken",
    "accessToken",
    "refreshToken",
    "oauthClientSecret",
    "extraHeaders",
    "accessCodeHash",
})
# Top-level collections whose documents carry ``ownerId`` for a user.
_OWNED_COLLECTIONS = ("sessions", "tasks", "schedules", "subagent_records")


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("[redacted]" if key in _EXPORT_REDACTED_KEYS else _redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class AuditRepository(FirestoreRepoBase):
    async def create_audit_log(self, actor_uid: str, action: str, target_uid: str, before: dict[str, Any] | None, after: dict[str, Any] | None) -> None:
        await asyncio.to_thread(self._create_audit_log_sync, actor_uid, action, target_uid, before, after)

    async def export_user_data(self, uid: str) -> dict[str, Any]:
        def _export_sync():
            db = self._db
            data = {}
            
            # Users
            user_doc = db.collection("users").document(uid).get()
            if user_doc.exists:
                data["user"] = user_doc.to_dict()
                
            # User Private
            private_doc = db.collection("userPrivate").document(uid).get()
            if private_doc.exists:
                data["userPrivate"] = private_doc.to_dict()
                
            # Beta Application
            beta_doc = db.collection("betaApplications").document(uid).get()
            if beta_doc.exists:
                data["betaApplication"] = beta_doc.to_dict()

            # Sessions
            sessions = []
            sessions_query = db.collection("sessions").where("ownerId", "==", uid).stream()
            for s_doc in sessions_query:
                s_data = s_doc.to_dict()
                s_data["id"] = s_doc.id
                
                # Messages
                messages = []
                for m_doc in s_doc.reference.collection("messages").stream():
                    m_data = m_doc.to_dict()
                    m_data["id"] = m_doc.id
                    messages.append(m_data)
                s_data["messages"] = messages
                
                # Artifacts and runs
                runs = []
                for r_doc in s_doc.reference.collection("runs").stream():
                    r_data = r_doc.to_dict()
                    r_data["id"] = r_doc.id
                    artifacts = []
                    for a_doc in r_doc.reference.collection("artifacts").stream():
                        a_data = a_doc.to_dict()
                        a_data["id"] = a_doc.id
                        artifacts.append(a_data)
                    r_data["artifacts"] = artifacts
                    runs.append(r_data)
                s_data["runs"] = runs
                sessions.append(s_data)
                
            data["sessions"] = sessions
            return _redact(data)
            
        return await asyncio.to_thread(_export_sync)

    async def delete_user_data(self, uid: str) -> list[str]:
        def _delete_sync():
            db = self._db
            session_ids: list[str] = []
            # recursive_delete removes a document *and every subcollection*
            # (messages, runs/steps/artifacts, usage/credit events, task
            # mirrors, approvals, firings ...) using a batched BulkWriter.
            for collection in _OWNED_COLLECTIONS:
                for doc in db.collection(collection).where("ownerId", "==", uid).stream():
                    if collection == "sessions":
                        session_ids.append(doc.id)
                    db.recursive_delete(doc.reference)

            # users/{uid} and userPrivate/{uid} hold tasks mirrors, templates,
            # integrations and credentials as subcollections.
            db.recursive_delete(db.collection("users").document(uid))
            db.recursive_delete(db.collection("userPrivate").document(uid))
            db.collection("betaApplications").document(uid).delete()
            return session_ids

        session_ids = await asyncio.to_thread(_delete_sync)

        def _delete_auth_user() -> None:
            from firebase_admin import auth as firebase_auth

            try:
                firebase_auth.delete_user(uid)
            except firebase_auth.UserNotFoundError:
                pass

        try:
            await asyncio.to_thread(_delete_auth_user)
        except Exception:
            logger.warning("Failed to delete Firebase Auth user %s", uid, exc_info=True)
        return session_ids
