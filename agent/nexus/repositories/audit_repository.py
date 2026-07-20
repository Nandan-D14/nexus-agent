# Proprietary and non-commercial use only.

"""Audit logging and GDPR-style user data export/delete."""

from __future__ import annotations

import asyncio
from typing import Any

from nexus._firestore_base import FirestoreRepoBase


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
            return data
            
        return await asyncio.to_thread(_export_sync)

    async def delete_user_data(self, uid: str) -> list[str]:
        def _delete_sync():
            db = self._db
            session_ids = []
            
            # Get sessions to delete artifacts in GCS later
            sessions_query = db.collection("sessions").where("ownerId", "==", uid).stream()
            for s_doc in sessions_query:
                session_ids.append(s_doc.id)
                # We won't recursively delete all subcollections here perfectly,
                # but we'll try to delete the session document. 
                # (Firestore requires a recursive delete which isn't natively supported in python client easily 
                # without iterating, but we'll do a simple delete for now, or just the main ones).
                # Actually, the user asked to delete user doc, sessions, messages, artifacts.
                for m_doc in s_doc.reference.collection("messages").stream():
                    m_doc.reference.delete()
                for r_doc in s_doc.reference.collection("runs").stream():
                    for a_doc in r_doc.reference.collection("artifacts").stream():
                        a_doc.reference.delete()
                    for st_doc in r_doc.reference.collection("steps").stream():
                        st_doc.reference.delete()
                    r_doc.reference.delete()
                for u_doc in s_doc.reference.collection("usage_events").stream():
                    u_doc.reference.delete()
                for c_doc in s_doc.reference.collection("credit_events").stream():
                    c_doc.reference.delete()
                s_doc.reference.delete()

            # Delete templates
            for t_doc in db.collection("users").document(uid).collection("workflowTemplates").stream():
                t_doc.reference.delete()
                
            # Delete integrations
            for i_doc in db.collection("users").document(uid).collection("integrations").stream():
                i_doc.reference.delete()
            for i_doc in db.collection("userPrivate").document(uid).collection("integrations").stream():
                i_doc.reference.delete()
                
            # Delete user docs
            db.collection("users").document(uid).delete()
            db.collection("userPrivate").document(uid).delete()
            db.collection("betaApplications").document(uid).delete()
            
            return session_ids

        return await asyncio.to_thread(_delete_sync)
