# Proprietary and non-commercial use only.

"""Persistent sandbox and workspace-state persistence."""

from __future__ import annotations

import asyncio
from typing import Any

from nexus._firestore_base import FirestoreRepoBase
from nexus.history_models import utcnow


class SandboxStateRepository(FirestoreRepoBase):
    async def get_persistent_sandbox(self, owner_id: str) -> str | None:
        """Return the paused sandbox ID for the user, or None if none exists."""
        return await asyncio.to_thread(self._get_persistent_sandbox_sync, owner_id)

    async def get_workspace_state(self, owner_id: str) -> dict[str, str | None]:
        return await asyncio.to_thread(self._get_workspace_state_sync, owner_id)

    async def save_paused_sandbox(
        self,
        owner_id: str,
        sandbox_id: str | None,
        session_id: str | None = None,
    ) -> None:
        """Write (or clear) the user's paused sandbox ID in Firestore."""
        await asyncio.to_thread(self._save_paused_sandbox_sync, owner_id, sandbox_id, session_id)

    def _get_persistent_sandbox_sync(self, owner_id: str) -> str | None:
        return self._get_workspace_state_sync(owner_id).get("sandbox_id")

    def _get_workspace_state_sync(self, owner_id: str) -> dict[str, str | None]:
        doc = self._user_public_ref(owner_id).get()
        if not doc.exists:
            return {"sandbox_id": None, "session_id": None}
        data = doc.to_dict() or {}
        sandbox_id = data.get("pausedSandboxId") if isinstance(data.get("pausedSandboxId"), str) else None
        session_id = data.get("pausedSandboxSessionId") if isinstance(data.get("pausedSandboxSessionId"), str) else None
        return {"sandbox_id": sandbox_id, "session_id": session_id}

    def _save_paused_sandbox_sync(
        self,
        owner_id: str,
        sandbox_id: str | None,
        session_id: str | None,
    ) -> None:
        state = self._get_workspace_state_sync(owner_id)
        previous_session_id = state.get("session_id")
        now = utcnow()
        batch = self._db.batch()
        user_ref = self._user_public_ref(owner_id)
        batch.set(
            user_ref,
            {
                "pausedSandboxId": sandbox_id,
                "pausedSandboxSessionId": session_id,
                "updatedAt": now,
            },
            merge=True,
        )

        if previous_session_id and previous_session_id != session_id:
            batch.set(
                self._db.collection("sessions").document(previous_session_id),
                {
                    "canContinueWorkspace": False,
                    "exactWorkspaceResumeAvailable": False,
                    "continuationMode": "new_sandbox_resume",
                    "resumeState": "ended",
                    "workspaceOwnerSessionId": None,
                    "canContinueConversation": True,
                    "updatedAt": now,
                },
                merge=True,
            )

        if session_id:
            batch.set(
                self._db.collection("sessions").document(session_id),
                {
                    "canContinueWorkspace": True,
                    "exactWorkspaceResumeAvailable": True,
                    "continuationMode": "exact_workspace_resume",
                    "resumeState": "paused",
                    "workspaceOwnerSessionId": session_id,
                    "canContinueConversation": True,
                    "updatedAt": now,
                },
                merge=True,
            )
        elif previous_session_id:
            batch.set(
                self._db.collection("sessions").document(previous_session_id),
                {
                    "canContinueWorkspace": False,
                    "exactWorkspaceResumeAvailable": False,
                    "continuationMode": "new_sandbox_resume",
                    "resumeState": "ended",
                    "workspaceOwnerSessionId": None,
                    "canContinueConversation": True,
                    "updatedAt": now,
                },
                merge=True,
            )

        batch.commit()
