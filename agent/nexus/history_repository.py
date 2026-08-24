# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Firestore-backed persistence for users, sessions, and message history."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from firebase_admin import firestore
from google.api_core.exceptions import AlreadyExists, FailedPrecondition, GoogleAPICallError
from google.cloud.firestore_v1 import FieldFilter

from nexus._firestore_base import FirestoreRepoBase
from nexus.auth import AuthenticatedUser
from nexus.billing import build_quota_payload, calculate_usage_credits
from nexus.config import settings
from nexus.firebase import get_firestore_client
from nexus.firestore_concurrency import guarded_write, run_with_write_retry

# Re-exported for backward compatibility. The DTOs and ``utcnow`` were moved to
# ``nexus.history_models`` so the repository base and focused repositories can
# share them without a circular import.
from nexus.history_models import (  # noqa: F401
    StoredArtifact,
    StoredIntegrationConnection,
    StoredRun,
    StoredRunStep,
    StoredSession,
    StoredTask,
    StoredWorkflowTemplate,
    utcnow,
)

if TYPE_CHECKING:
    from nexus.session import Session

logger = logging.getLogger(__name__)


class FirestoreHistoryRepository(FirestoreRepoBase):
    """Sync Firestore access wrapped with async-friendly helpers.

    The shared Firestore client, document-ref helpers, value coercion, and
    ``StoredX`` projection builders live on :class:`FirestoreRepoBase`.

    Cleanly-separable concerns (users, integrations, workflow
    templates, sandbox state, audit/GDPR) are delegated to focused
    repositories under :mod:`nexus.repositories`. The interlinked
    session/run/step/artifact/usage/task aggregate remains defined on this
    class. Delegation is handled by :meth:`__getattr__`, so all existing
    ``history_repository.<method>`` call sites are unchanged.
    """

    def __init__(self) -> None:
        from nexus.repositories import (
            AuditRepository,
            IntegrationRepository,
            SandboxStateRepository,
            UserRepository,
            WorkflowTemplateRepository,
        )

        self._users = UserRepository()
        self._integrations = IntegrationRepository()
        self._templates = WorkflowTemplateRepository()
        self._sandbox_state = SandboxStateRepository()
        self._audit = AuditRepository()
        # Ordered list of delegate repositories searched by __getattr__.
        self._delegates = (
            self._users,
            self._integrations,
            self._templates,
            self._sandbox_state,
            self._audit,
        )

    def __getattr__(self, name: str):
        # Only invoked when normal attribute lookup fails, i.e. for methods
        # that were moved to a focused repository. Public method names are
        # unique across concerns, so first match wins.
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        for delegate in self.__dict__.get("_delegates", ()):  # pragma: no branch
            attr = getattr(delegate, name, None)
            if attr is not None:
                return attr
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}"
        )

    def _list_owner_sessions_sync(self, owner_id: str) -> list[tuple[str, dict[str, Any]]]:
        sessions = (
            self._db.collection("sessions")
            .where(filter=FieldFilter("ownerId", "==", owner_id))
            .stream()
        )
        return [(doc.id, doc.to_dict() or {}) for doc in sessions]

    @staticmethod
    def _clip_text(value: Any, limit: int = 220) -> str:
        if not isinstance(value, str):
            return ""
        normalized = " ".join(value.split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 1].rstrip() + "…"

    @classmethod
    def _normalize_tool_memories(cls, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []

        normalized: list[dict[str, Any]] = []
        for raw in value:
            if not isinstance(raw, dict):
                continue
            summary = cls._clip_text(raw.get("summary"), 180)
            if not summary:
                continue
            kind = raw.get("kind") if isinstance(raw.get("kind"), str) else "tool"
            normalized.append(
                {
                    "kind": kind[:40],
                    "summary": summary,
                    "hash": raw.get("hash") if isinstance(raw.get("hash"), str) else "",
                    "sourceStepId": raw.get("sourceStepId") if isinstance(raw.get("sourceStepId"), str) else None,
                    "createdAt": raw.get("createdAt"),
                    "metadata": raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {},
                }
            )
        return normalized[:20]

    def _build_handoff_summary(
        self,
        session_id: str,
        data: dict[str, Any],
        messages: list[dict[str, Any]],
        *,
        run: StoredRun | None = None,
        steps: list[StoredRunStep] | None = None,
        artifacts: list[StoredArtifact] | None = None,
        can_continue_workspace: bool,
    ) -> dict[str, Any]:
        first_user = next(
            (self._clip_text(msg.get("text")) for msg in messages if msg.get("role") == "user" and self._clip_text(msg.get("text"))),
            "",
        )
        last_user = next(
            (self._clip_text(msg.get("text")) for msg in reversed(messages) if msg.get("role") == "user" and self._clip_text(msg.get("text"))),
            "",
        )
        last_agent = next(
            (self._clip_text(msg.get("text")) for msg in reversed(messages) if msg.get("role") == "agent" and self._clip_text(msg.get("text"))),
            "",
        )
        summary = self._clip_text(data.get("summary"), 280)
        steps = steps or []
        artifacts = artifacts or []
        latest_completed_steps = [step for step in steps if step.status == "completed"]
        latest_failed_steps = [step for step in steps if step.status in {"failed", "cancelled"}]
        latest_artifact = artifacts[0] if artifacts else None

        step_summary = ""
        if latest_completed_steps:
            latest_step = latest_completed_steps[-1]
            step_summary = self._clip_text(latest_step.detail or latest_step.title, 240)

        artifact_summary = ""
        if latest_artifact:
            artifact_summary = self._clip_text(latest_artifact.preview or latest_artifact.title, 240)

        headline = summary or artifact_summary or step_summary or last_agent or last_user or first_user or "Resume where you left off"

        completed_work: list[str] = []
        for candidate in (summary, artifact_summary, step_summary, last_agent):
            if candidate and candidate not in completed_work:
                completed_work.append(candidate)
        for step in latest_completed_steps[-3:]:
            candidate = self._clip_text(step.title or step.detail, 180)
            if candidate and candidate not in completed_work:
                completed_work.append(candidate)

        open_tasks: list[str] = []
        for step in latest_failed_steps[-2:]:
            candidate = self._clip_text(step.error or step.detail or step.title, 180)
            if candidate:
                open_tasks.append(candidate)
        if last_user:
            open_tasks.append(last_user)
        if not open_tasks:
            open_tasks.append("Reopen the workspace, inspect the current state, and continue the previous task.")

        important_facts: list[str] = []
        for artifact in artifacts[:3]:
            preview = self._clip_text(artifact.preview or artifact.title, 180)
            if preview:
                important_facts.append(f"Artifact: {preview}")
        for msg in messages[-6:]:
            role = "User" if msg.get("role") == "user" else "Agent"
            text = self._clip_text(msg.get("text"), 180)
            if text:
                important_facts.append(f"{role}: {text}")

        preview = summary or artifact_summary or step_summary or last_agent or last_user or "Reusable session context is ready."
        return {
            "headline": headline,
            "preview": preview,
            "goal": first_user or "Continue the previous workspace task.",
            "current_status": "paused" if can_continue_workspace else (run.status if run else str(data.get("status", "ended"))),
            "completed_work": completed_work[:3],
            "open_tasks": open_tasks[:3],
            "important_facts": important_facts[:5],
            "artifacts": [artifact.title or artifact.kind for artifact in artifacts[:4]],
            "recommended_next_step": open_tasks[0],
            "source_session_id": session_id,
        }

    def _build_context_packet(
        self,
        data: dict[str, Any],
        messages: list[dict[str, Any]],
        *,
        handoff_summary: dict[str, Any] | None,
        run: StoredRun | None = None,
        steps: list[StoredRunStep] | None = None,
        artifacts: list[StoredArtifact] | None = None,
    ) -> dict[str, Any]:
        steps = steps or []
        artifacts = artifacts or []
        handoff_summary = handoff_summary or {}
        tool_memories = self._normalize_tool_memories(data.get("toolMemories"))

        latest_completed_steps = [step for step in steps if step.status == "completed"]
        latest_failed_steps = [step for step in steps if step.status in {"failed", "cancelled"}]
        latest_run_summary = ""
        if latest_completed_steps:
            latest_completed = latest_completed_steps[-1]
            latest_run_summary = self._clip_text(latest_completed.detail or latest_completed.title, 240)
        if not latest_run_summary and run:
            latest_run_summary = self._clip_text(run.title, 240)

        recent_turns: list[str] = []
        for msg in messages[-4:]:
            role = "User" if msg.get("role") == "user" else "Agent"
            text = self._clip_text(msg.get("text"), 200)
            if text:
                recent_turns.append(f"{role}: {text}")

        artifact_refs: list[str] = []
        for artifact in artifacts[:4]:
            preview = self._clip_text(artifact.preview or artifact.title, 180)
            if preview:
                artifact_refs.append(f"{artifact.kind}: {preview}")

        tool_memory = [
            f"{item.get('kind', 'tool')}: {self._clip_text(item.get('summary'), 180)}"
            for item in tool_memories[:6]
            if self._clip_text(item.get("summary"), 180)
        ]

        workspace_bits: list[str] = []
        current_status = handoff_summary.get("current_status")
        if isinstance(current_status, str) and current_status.strip():
            workspace_bits.append(f"Status: {current_status.strip()}")
        resume_state = data.get("resumeState")
        if isinstance(resume_state, str) and resume_state.strip():
            workspace_bits.append(f"Resume: {resume_state.strip()}")
        if latest_failed_steps:
            failed = latest_failed_steps[-1]
            failure_hint = self._clip_text(failed.error or failed.detail or failed.title, 180)
            if failure_hint:
                workspace_bits.append(f"Last issue: {failure_hint}")
        elif latest_completed_steps:
            completed = latest_completed_steps[-1]
            completion_hint = self._clip_text(completed.title or completed.detail, 180)
            if completion_hint:
                workspace_bits.append(f"Last completed step: {completion_hint}")

        packet = {
            "version": 2,
            "summary": self._clip_text(
                handoff_summary.get("preview") or data.get("summary") or latest_run_summary,
                500,
            ),
            "goal": self._clip_text(
                handoff_summary.get("goal") or "Continue the previous workspace task.",
                220,
            ),
            "openTasks": [
                self._clip_text(item, 180)
                for item in (handoff_summary.get("open_tasks") or [])
                if self._clip_text(item, 180)
            ][:4],
            "recentTurns": recent_turns,
            "latestRunSummary": latest_run_summary,
            "artifactRefs": artifact_refs,
            "toolMemory": tool_memory,
            "workspaceState": self._clip_text(" | ".join(workspace_bits), 220),
        }
        digest_source = json.dumps(packet, sort_keys=True, ensure_ascii=True)
        digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:16]
        packet["digest"] = digest
        packet["builtAt"] = utcnow().isoformat()
        packet["inputsDigest"] = digest
        return packet

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
        async with guarded_write(session_id):
            await asyncio.to_thread(
                run_with_write_retry,
                lambda: self._append_message_sync(
                    session_id,
                    owner_id,
                    role,
                    source,
                    text,
                ),
                description="append_message",
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
    ) -> tuple[int, dict[str, int]]:
        async with guarded_write(session_id):
            return await asyncio.to_thread(
                run_with_write_retry,
                lambda: self._append_token_usage_sync(
                    session_id,
                    owner_id,
                    source,
                    model,
                    input_tokens,
                    output_tokens,
                    total_tokens,
                ),
                description="append_token_usage",
            )

    async def record_credit_charge(
        self,
        *,
        session_id: str,
        owner_id: str,
        source: str,
        model: str,
        credits: int,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._record_credit_charge_sync,
            session_id,
            owner_id,
            source,
            model,
            credits,
            metadata,
        )

    async def record_tool_memory(
        self,
        *,
        session_id: str,
        kind: str,
        summary: str,
        content_hash: str,
        source_step_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._record_tool_memory_sync,
            session_id,
            kind,
            summary,
            content_hash,
            source_step_id,
            metadata,
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

    async def list_tasks(self, owner_id: str, limit: int = 25, status: str | None = None, search: str | None = None) -> list[StoredTask]:
        return await asyncio.to_thread(self._list_tasks_sync, owner_id, limit, status, search)

    async def get_task(self, owner_id: str, task_id: str) -> StoredTask | None:
        return await asyncio.to_thread(self._get_task_sync, owner_id, task_id)

    async def list_recent_session_usage(self, owner_id: str, limit: int = 10) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_recent_session_usage_sync, owner_id, limit)

    async def list_active_sessions(self, owner_id: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_active_sessions_sync, owner_id)

    async def list_all_active_sandbox_ids(self) -> list[str]:
        """Return a list of all sandbox IDs associated with active sessions across all users."""
        return await asyncio.to_thread(self._list_all_active_sandbox_ids_sync)

    async def get_session_messages(self, session_id: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._get_session_messages_sync, session_id)

    async def refresh_session_handoff(
        self,
        session_id: str,
        *,
        owner_id: str,
        resume_state: str | None = None,
        workspace_owner_session_id: str | None = None,
        can_continue_workspace: bool | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._refresh_session_handoff_sync,
            session_id,
            owner_id,
            resume_state,
            workspace_owner_session_id,
            can_continue_workspace,
        )

    async def create_run(
        self,
        *,
        session_id: str,
        owner_id: str,
        title: str,
        source_session_id: str | None = None,
    ) -> StoredRun:
        return await asyncio.to_thread(
            self._create_run_sync,
            session_id,
            owner_id,
            title,
            source_session_id,
        )

    async def ensure_run(
        self,
        *,
        session_id: str,
        run_id: str,
        owner_id: str,
        title: str = "Agent Turn",
        task_id: str | None = None,
        status: str = "queued",
    ) -> StoredRun:
        """Create the history run doc if missing. Idempotent.

        Durable workers bind a ``run_*`` id that lives under production_tasks
        but history child writes (steps/artifacts/messages) require the same
        id under ``sessions/{sessionId}/runs/{runId}``. Call this before any
        child write when the run id came from outside history.
        """
        return await asyncio.to_thread(
            self._ensure_run_sync,
            session_id,
            run_id,
            owner_id,
            title,
            task_id,
            status,
        )

    async def get_session_run(self, session_id: str) -> StoredRun | None:
        return await asyncio.to_thread(self._get_session_run_sync, session_id)

    async def set_run_status(
        self,
        *,
        session_id: str,
        run_id: str,
        status: str,
    ) -> StoredRun | None:
        return await asyncio.to_thread(self._set_run_status_sync, session_id, run_id, status)

    async def mark_session_deleted(self, session_id: str) -> None:
        await asyncio.to_thread(self._mark_session_deleted_sync, session_id)

    async def mark_session_sandbox_unavailable(
        self,
        session_id: str,
        *,
        reason: str = "sandbox_unavailable",
    ) -> None:
        await asyncio.to_thread(
            self._mark_session_sandbox_unavailable_sync,
            session_id,
            reason,
        )

    async def create_step(
        self,
        *,
        session_id: str,
        run_id: str,
        step_type: str,
        title: str,
        detail: str = "",
        status: str = "running",
        source: str | None = None,
        external_ref: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StoredRunStep:
        return await asyncio.to_thread(
            self._create_step_sync,
            session_id,
            run_id,
            step_type,
            title,
            detail,
            status,
            source,
            external_ref,
            metadata,
        )

    async def complete_step(
        self,
        *,
        session_id: str,
        run_id: str,
        step_id: str,
        detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StoredRunStep | None:
        return await asyncio.to_thread(
            self._complete_step_sync,
            session_id,
            run_id,
            step_id,
            detail,
            metadata,
        )

    async def fail_step(
        self,
        *,
        session_id: str,
        run_id: str,
        step_id: str,
        detail: str | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
        status: str = "failed",
    ) -> StoredRunStep | None:
        return await asyncio.to_thread(
            self._fail_step_sync,
            session_id,
            run_id,
            step_id,
            detail,
            error,
            metadata,
            status,
        )

    async def list_run_steps(self, session_id: str, run_id: str, limit: int = 200) -> list[StoredRunStep]:
        return await asyncio.to_thread(self._list_run_steps_sync, session_id, run_id, limit)

    async def list_session_steps(self, session_id: str, limit: int = 500) -> list[StoredRunStep]:
        """Return steps from *all* runs in a session, ordered chronologically."""
        return await asyncio.to_thread(self._list_session_steps_sync, session_id, limit)

    async def create_artifact(
        self,
        *,
        session_id: str,
        run_id: str,
        kind: str,
        title: str,
        preview: str,
        source_step_id: str | None = None,
        path: str | None = None,
        url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StoredArtifact:
        return await asyncio.to_thread(
            self._create_artifact_sync,
            session_id,
            run_id,
            kind,
            title,
            preview,
            source_step_id,
            path,
            url,
            metadata,
        )

    async def list_run_artifacts(self, session_id: str, run_id: str, limit: int = 100) -> list[StoredArtifact]:
        return await asyncio.to_thread(self._list_run_artifacts_sync, session_id, run_id, limit)

    async def list_session_artifacts(self, session_id: str, limit: int = 200) -> list[StoredArtifact]:
        """Return artifacts from *all* runs in a session, newest first."""
        return await asyncio.to_thread(self._list_session_artifacts_sync, session_id, limit)

    async def get_artifact_for_owner(self, owner_id: str, artifact_id: str) -> StoredArtifact | None:
        return await asyncio.to_thread(self._get_artifact_for_owner_sync, owner_id, artifact_id)

    async def list_owner_library_artifacts(
        self,
        owner_id: str,
        *,
        limit: int = 100,
        cursor: datetime | None = None,
        search: str | None = None,
        category: str | None = None,
    ) -> tuple[list[Any], datetime | None]:
        """Return library-eligible artifacts for an owner, newest first."""
        return await asyncio.to_thread(
            self._list_owner_library_artifacts_sync,
            owner_id,
            limit,
            cursor,
            search,
            category,
        )

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
        task_id = getattr(session, "task_id", "") or existing.get("taskId") or session.id
        payload: dict[str, Any] = {
            "ownerId": session.owner_id,
            "taskId": task_id,
            "memberIds": [session.owner_id],
            "status": status,
            "updatedAt": now,
            "lastActiveAt": session.last_active,
            "sandboxId": session.sandbox_id or existing.get("sandboxId"),
            "schemaVersion": 2,
            "resumeMode": session.resume_mode,
            "currentRunId": getattr(session, "current_run_id", None) or existing.get("currentRunId"),
            "runStatus": getattr(session, "run_status", None) or existing.get("runStatus"),
            "artifactCount": int(getattr(session, "artifact_count", 0) or existing.get("artifactCount", 0) or 0),
            "canContinueConversation": bool(getattr(session, "can_continue_conversation", True)),
            "exactWorkspaceResumeAvailable": bool(getattr(session, "exact_workspace_resume_available", False)),
            "continuationMode": getattr(session, "continuation_mode", None) or existing.get("continuationMode"),
        }
        if session.resume_source_session_id:
            payload["resumeSourceSessionId"] = session.resume_source_session_id
        if not snapshot.exists:
            payload.update(
                {
                    "createdAt": session.created_at,
                    "messageCount": 0,
                    "title": session.initial_title or "New session",
                    "tokenTotals": self._empty_token_totals(),
                    "resumeState": "ready" if status in {"ready", "active"} else "fresh",
                    "canContinueWorkspace": False,
                    "hasArtifacts": False,
                    "artifactCount": int(getattr(session, "artifact_count", 0) or 0),
                    "canContinueConversation": True,
                    "exactWorkspaceResumeAvailable": bool(
                        getattr(session, "exact_workspace_resume_available", False)
                    ),
                    "continuationMode": getattr(session, "continuation_mode", None),
                }
            )
            if session.seed_context:
                payload["seedContext"] = session.seed_context
        if ended_at:
            payload["endedAt"] = ended_at
        if error_code:
            payload["lastErrorCode"] = error_code
        task_ref = self._task_ref(session.owner_id, task_id)
        task_payload: dict[str, Any] = {
            "ownerId": session.owner_id,
            "taskId": task_id,
            "currentSessionId": session.id,
            "currentRunId": payload.get("currentRunId"),
            "runStatus": payload.get("runStatus"),
            "status": status,
            "title": payload.get("title") or existing.get("title") or session.initial_title or "New task",
            "updatedAt": now,
            "lastActiveAt": session.last_active,
            "messageCount": int(existing.get("messageCount", 0) or 0),
            "artifactCount": int(payload.get("artifactCount", 0) or 0),
            "schemaVersion": 1,
        }
        if not task_ref.get().exists:
            task_payload["createdAt"] = session.created_at
        batch = self._db.batch()
        batch.set(ref, payload, merge=True)
        batch.set(task_ref, task_payload, merge=True)
        batch.commit()

    def _create_run_sync(
        self,
        session_id: str,
        owner_id: str,
        title: str,
        source_session_id: str | None,
    ) -> StoredRun:
        now = utcnow()
        run_id = uuid.uuid4().hex[:12]
        session_ref = self._db.collection("sessions").document(session_id)
        session_data = session_ref.get().to_dict() or {}
        task_id = session_data.get("taskId") if isinstance(session_data.get("taskId"), str) else session_id
        task_ref = self._task_ref(owner_id, task_id)
        run_ref = session_ref.collection("runs").document(run_id)
        payload: dict[str, Any] = {
            "ownerId": owner_id,
            "sessionId": session_id,
            "taskId": task_id,
            "status": "queued",
            "title": title,
            "createdAt": now,
            "updatedAt": now,
            "stepCount": 0,
            "artifactCount": 0,
        }
        if source_session_id:
            payload["sourceSessionId"] = source_session_id
        batch = self._db.batch()
        batch.set(run_ref, payload, merge=True)
        batch.set(task_ref.collection("runs").document(run_id), payload, merge=True)
        batch.set(
            session_ref,
            {
                "taskId": task_id,
                "currentRunId": run_id,
                "runStatus": "queued",
                "artifactCount": int(session_data.get("artifactCount", 0) or 0),
                "updatedAt": now,
            },
            merge=True,
        )
        batch.set(
            task_ref,
            {
                "ownerId": owner_id,
                "taskId": task_id,
                "currentSessionId": session_id,
                "currentRunId": run_id,
                "runStatus": "queued",
                "status": "queued",
                "title": title or session_data.get("title") or "New task",
                "updatedAt": now,
                "createdAt": session_data.get("createdAt") or now,
                "schemaVersion": 1,
            },
            merge=True,
        )
        batch.commit()
        return self._build_stored_run(session_id, run_id, payload)

    def _ensure_run_sync(
        self,
        session_id: str,
        run_id: str,
        owner_id: str,
        title: str,
        task_id: str | None,
        status: str,
    ) -> StoredRun:
        now = utcnow()
        session_ref = self._db.collection("sessions").document(session_id)
        run_ref = session_ref.collection("runs").document(run_id)
        existing = run_ref.get()
        if existing.exists:
            return self._build_stored_run(session_id, run_id, existing.to_dict() or {})

        session_data = session_ref.get().to_dict() or {}
        effective_owner = owner_id or (
            session_data.get("ownerId") if isinstance(session_data.get("ownerId"), str) else ""
        )
        effective_task = task_id or (
            session_data.get("taskId") if isinstance(session_data.get("taskId"), str) else session_id
        )
        payload: dict[str, Any] = {
            "ownerId": effective_owner,
            "sessionId": session_id,
            "taskId": effective_task,
            "status": status or "queued",
            "title": title or "Agent Turn",
            "createdAt": now,
            "updatedAt": now,
            "stepCount": 0,
            "artifactCount": 0,
        }
        task_ref = self._task_ref(effective_owner, effective_task) if effective_owner else None
        batch = self._db.batch()
        batch.set(run_ref, payload, merge=True)
        if task_ref is not None:
            batch.set(task_ref.collection("runs").document(run_id), payload, merge=True)
            batch.set(
                task_ref,
                {
                    "ownerId": effective_owner,
                    "taskId": effective_task,
                    "currentSessionId": session_id,
                    "currentRunId": run_id,
                    "runStatus": payload["status"],
                    "status": payload["status"],
                    "title": payload["title"],
                    "updatedAt": now,
                    "schemaVersion": 1,
                },
                merge=True,
            )
        batch.set(
            session_ref,
            {
                "taskId": effective_task,
                "currentRunId": run_id,
                "runStatus": payload["status"],
                "updatedAt": now,
            },
            merge=True,
        )
        batch.commit()
        logger.info(
            "Ensured history run %s for session %s (was missing)",
            run_id,
            session_id,
        )
        return self._build_stored_run(session_id, run_id, payload)

    def _get_session_run_sync(self, session_id: str) -> StoredRun | None:
        session = self._get_session_sync(session_id)
        if not session:
            return None

        run_id = session.current_run_id
        if run_id:
            run_ref = self._db.collection("sessions").document(session_id).collection("runs").document(run_id)
            run_doc = run_ref.get()
            if run_doc.exists:
                return self._build_stored_run(session_id, run_doc.id, run_doc.to_dict() or {})

        runs = (
            self._db.collection("sessions")
            .document(session_id)
            .collection("runs")
            .order_by("createdAt", direction=firestore.Query.DESCENDING)
            .limit(1)
            .stream()
        )
        for doc in runs:
            return self._build_stored_run(session_id, doc.id, doc.to_dict() or {})
        return None

    def _set_run_status_sync(self, session_id: str, run_id: str, status: str) -> StoredRun | None:
        now = utcnow()
        session_ref = self._db.collection("sessions").document(session_id)
        run_ref = session_ref.collection("runs").document(run_id)
        run_doc = run_ref.get()
        session_doc = session_ref.get()
        session_data = session_doc.to_dict() or {} if session_doc.exists else {}

        if not run_doc.exists:
            owner_id = session_data.get("ownerId") if isinstance(session_data.get("ownerId"), str) else ""
            task_id = session_data.get("taskId") if isinstance(session_data.get("taskId"), str) else session_id
            current = {
                "ownerId": owner_id,
                "sessionId": session_id,
                "taskId": task_id,
                "status": "queued",
                "title": "Agent Turn",
                "createdAt": now,
                "updatedAt": now,
                "stepCount": 0,
                "artifactCount": 0,
            }
        else:
            current = run_doc.to_dict() or {}

        owner_id = current.get("ownerId") if isinstance(current.get("ownerId"), str) else ""
        task_id = current.get("taskId") if isinstance(current.get("taskId"), str) else (session_data.get("taskId") or session_id)
        updates: dict[str, Any] = {
            "status": status,
            "updatedAt": now,
        }
        if status == "running" and current.get("startedAt") is None:
            updates["startedAt"] = now
        if status in {"completed", "failed", "cancelled"}:
            updates["completedAt"] = now

        batch = self._db.batch()
        batch.set(run_ref, updates, merge=True)
        if owner_id:
            task_run_ref = self._task_run_ref(owner_id, task_id, run_id)
            batch.set(task_run_ref, updates, merge=True)
            batch.set(
                self._task_ref(owner_id, task_id),
                {
                    "currentSessionId": session_id,
                    "currentRunId": run_id,
                    "runStatus": status,
                    "status": status,
                    "updatedAt": now,
                },
                merge=True,
            )
        batch.set(
            self._db.collection("sessions").document(session_id),
            {
                "currentRunId": run_id,
                "runStatus": status,
                "updatedAt": now,
            },
            merge=True,
        )
        batch.commit()
        merged = {**current, **updates}
        return self._build_stored_run(session_id, run_id, merged)

    def _mark_session_deleted_sync(self, session_id: str) -> None:
        now = utcnow()
        ref = self._db.collection("sessions").document(session_id)
        doc = ref.get()
        if doc.exists:
            data = doc.to_dict() or {}
            task_id = data.get("taskId") if isinstance(data.get("taskId"), str) else session_id
            owner_id = data.get("ownerId")
            
            batch = self._db.batch()
            batch.set(
                ref,
                {
                    "status": "deleted",
                    "updatedAt": now,
                    "endedAt": now,
                    "sandboxId": None,
                    "resumeState": "deleted",
                    "canContinueWorkspace": False,
                    "exactWorkspaceResumeAvailable": False,
                },
                merge=True,
            )
            
            if owner_id:
                task_ref = self._task_ref(owner_id, task_id)
                # Note: we only update the session, not the whole task unless needed
            
            batch.commit()

    def _mark_session_sandbox_unavailable_sync(self, session_id: str, reason: str) -> None:
        now = utcnow()
        ref = self._db.collection("sessions").document(session_id)
        doc = ref.get()
        if not doc.exists:
            return

        data = doc.to_dict() or {}
        if data.get("status") == "deleted":
            return

        owner_id = data.get("ownerId") if isinstance(data.get("ownerId"), str) else ""
        task_id = data.get("taskId") if isinstance(data.get("taskId"), str) else session_id
        sandbox_id = data.get("sandboxId") if isinstance(data.get("sandboxId"), str) else None
        ended_at = data.get("endedAt") or now

        batch = self._db.batch()
        batch.set(
            ref,
            {
                "status": "ended",
                "updatedAt": now,
                "endedAt": ended_at,
                "sandboxId": None,
                "resumeState": "ended",
                "canContinueWorkspace": False,
                "exactWorkspaceResumeAvailable": False,
                "continuationMode": "new_sandbox_resume",
                "workspaceOwnerSessionId": None,
                "canContinueConversation": True,
                "lastErrorCode": reason,
            },
            merge=True,
        )

        if owner_id:
            batch.set(
                self._task_ref(owner_id, task_id),
                {
                    "status": "ended",
                    "updatedAt": now,
                    "currentSessionId": session_id,
                    "runStatus": data.get("runStatus"),
                },
                merge=True,
            )
            user_ref = self._user_public_ref(owner_id)
            user_doc = user_ref.get()
            if user_doc.exists:
                user_data = user_doc.to_dict() or {}
                if (
                    user_data.get("pausedSandboxSessionId") == session_id
                    or (sandbox_id and user_data.get("pausedSandboxId") == sandbox_id)
                ):
                    batch.set(
                        user_ref,
                        {
                            "pausedSandboxId": None,
                            "pausedSandboxSessionId": None,
                            "updatedAt": now,
                        },
                        merge=True,
                    )

        batch.commit()

    def _create_step_sync(
        self,
        session_id: str,
        run_id: str,
        step_type: str,
        title: str,
        detail: str,
        status: str,
        source: str | None,
        external_ref: str | None,
        metadata: dict[str, Any] | None,
    ) -> StoredRunStep:
        now = utcnow()
        session_ref = self._db.collection("sessions").document(session_id)
        run_ref = session_ref.collection("runs").document(run_id)
        steps_collection = run_ref.collection("steps")
        step_id = uuid.uuid4().hex[:12]
        transaction = self._db.transaction()

        @firestore.transactional
        def transactional_create(txn):
            run_snapshot = run_ref.get(transaction=txn)
            session_snapshot = session_ref.get(transaction=txn)
            session_data = session_snapshot.to_dict() or {} if session_snapshot.exists else {}

            if not run_snapshot.exists:
                owner_id = session_data.get("ownerId") if isinstance(session_data.get("ownerId"), str) else ""
                task_id = session_data.get("taskId") if isinstance(session_data.get("taskId"), str) else session_id
                run_payload = {
                    "ownerId": owner_id,
                    "sessionId": session_id,
                    "taskId": task_id,
                    "status": "running",
                    "title": "Agent Turn",
                    "createdAt": now,
                    "updatedAt": now,
                    "stepCount": 0,
                    "artifactCount": 0,
                }
                txn.set(run_ref, run_payload, merge=True)
                if owner_id:
                    task_run_ref = self._task_run_ref(owner_id, task_id, run_id)
                    txn.set(task_run_ref, run_payload, merge=True)
                run_data = run_payload
            else:
                run_data = run_snapshot.to_dict() or {}

            owner_id = run_data.get("ownerId") if isinstance(run_data.get("ownerId"), str) else ""
            task_id = run_data.get("taskId") if isinstance(run_data.get("taskId"), str) else session_data.get("taskId") or session_id
            step_index = int(run_data.get("stepCount", 0) or 0) + 1
            payload: dict[str, Any] = {
                "sessionId": session_id,
                "taskId": task_id,
                "runId": run_id,
                "stepType": step_type,
                "status": status,
                "title": title,
                "detail": detail,
                "createdAt": now,
                "updatedAt": now,
                "stepIndex": step_index,
                "metadata": metadata or {},
            }
            if source:
                payload["source"] = source
            if external_ref:
                payload["externalRef"] = external_ref

            txn.set(steps_collection.document(step_id), payload)
            if owner_id:
                task_run_ref = self._task_run_ref(owner_id, task_id, run_id)
                txn.set(task_run_ref.collection("steps").document(step_id), payload)
                txn.set(
                    task_run_ref,
                    {
                        "stepCount": step_index,
                        "lastStepAt": now,
                        "updatedAt": now,
                    },
                    merge=True,
                )
                txn.set(
                    self._task_ref(owner_id, task_id),
                    {
                        "currentSessionId": session_id,
                        "currentRunId": run_id,
                        "stepCount": step_index,
                        "lastStepAt": now,
                        "updatedAt": now,
                    },
                    merge=True,
                )
            txn.set(
                run_ref,
                {
                    "stepCount": step_index,
                    "lastStepAt": now,
                    "updatedAt": now,
                },
                merge=True,
            )
            txn.set(
                session_ref,
                {
                    "lastStepAt": now,
                    "updatedAt": now,
                },
                merge=True,
            )
            return payload

        payload = transactional_create(transaction)
        return self._build_stored_run_step(session_id, run_id, step_id, payload)

    def _complete_step_sync(
        self,
        session_id: str,
        run_id: str,
        step_id: str,
        detail: str | None,
        metadata: dict[str, Any] | None,
    ) -> StoredRunStep | None:
        now = utcnow()
        step_ref = (
            self._db.collection("sessions")
            .document(session_id)
            .collection("runs")
            .document(run_id)
            .collection("steps")
            .document(step_id)
        )
        step_doc = step_ref.get()
        if not step_doc.exists:
            return None
        existing = step_doc.to_dict() or {}
        task_id = existing.get("taskId") if isinstance(existing.get("taskId"), str) else self._task_id_for_run_sync(session_id, run_id)
        owner_id = (
            self._db.collection("sessions")
            .document(session_id)
            .collection("runs")
            .document(run_id)
            .get()
            .to_dict()
            or {}
        ).get("ownerId")
        updates: dict[str, Any] = {
            "status": "completed",
            "updatedAt": now,
            "completedAt": now,
        }
        if detail is not None:
            updates["detail"] = detail
        if metadata:
            merged_metadata = existing.get("metadata", {}) if isinstance(existing.get("metadata"), dict) else {}
            updates["metadata"] = {**merged_metadata, **metadata}
        batch = self._db.batch()
        batch.set(step_ref, updates, merge=True)
        if isinstance(owner_id, str) and owner_id:
            batch.set(
                self._task_run_ref(owner_id, task_id, run_id).collection("steps").document(step_id),
                updates,
                merge=True,
            )
            batch.set(
                self._task_run_ref(owner_id, task_id, run_id),
                {"lastStepAt": now, "updatedAt": now},
                merge=True,
            )
            batch.set(
                self._task_ref(owner_id, task_id),
                {"lastStepAt": now, "updatedAt": now},
                merge=True,
            )
        batch.set(
            self._db.collection("sessions").document(session_id).collection("runs").document(run_id),
            {"lastStepAt": now, "updatedAt": now},
            merge=True,
        )
        batch.set(
            self._db.collection("sessions").document(session_id),
            {"lastStepAt": now, "updatedAt": now},
            merge=True,
        )
        batch.commit()
        merged = {**existing, **updates}
        return self._build_stored_run_step(session_id, run_id, step_id, merged)

    def _fail_step_sync(
        self,
        session_id: str,
        run_id: str,
        step_id: str,
        detail: str | None,
        error: str | None,
        metadata: dict[str, Any] | None,
        status: str,
    ) -> StoredRunStep | None:
        now = utcnow()
        step_ref = (
            self._db.collection("sessions")
            .document(session_id)
            .collection("runs")
            .document(run_id)
            .collection("steps")
            .document(step_id)
        )
        step_doc = step_ref.get()
        if not step_doc.exists:
            return None
        existing = step_doc.to_dict() or {}
        task_id = existing.get("taskId") if isinstance(existing.get("taskId"), str) else self._task_id_for_run_sync(session_id, run_id)
        owner_id = (
            self._db.collection("sessions")
            .document(session_id)
            .collection("runs")
            .document(run_id)
            .get()
            .to_dict()
            or {}
        ).get("ownerId")
        updates: dict[str, Any] = {
            "status": status,
            "updatedAt": now,
            "completedAt": now,
        }
        if detail is not None:
            updates["detail"] = detail
        if error:
            updates["error"] = error
        if metadata:
            merged_metadata = existing.get("metadata", {}) if isinstance(existing.get("metadata"), dict) else {}
            updates["metadata"] = {**merged_metadata, **metadata}
        batch = self._db.batch()
        batch.set(step_ref, updates, merge=True)
        if isinstance(owner_id, str) and owner_id:
            batch.set(
                self._task_run_ref(owner_id, task_id, run_id).collection("steps").document(step_id),
                updates,
                merge=True,
            )
            batch.set(
                self._task_run_ref(owner_id, task_id, run_id),
                {"lastStepAt": now, "updatedAt": now},
                merge=True,
            )
            batch.set(
                self._task_ref(owner_id, task_id),
                {"lastStepAt": now, "updatedAt": now},
                merge=True,
            )
        batch.set(
            self._db.collection("sessions").document(session_id).collection("runs").document(run_id),
            {"lastStepAt": now, "updatedAt": now},
            merge=True,
        )
        batch.set(
            self._db.collection("sessions").document(session_id),
            {"lastStepAt": now, "updatedAt": now},
            merge=True,
        )
        batch.commit()
        merged = {**existing, **updates}
        return self._build_stored_run_step(session_id, run_id, step_id, merged)

    def _list_run_steps_sync(self, session_id: str, run_id: str, limit: int) -> list[StoredRunStep]:
        docs = (
            self._db.collection("sessions")
            .document(session_id)
            .collection("runs")
            .document(run_id)
            .collection("steps")
            .order_by("stepIndex")
            .limit(limit)
            .stream()
        )
        return [
            self._build_stored_run_step(session_id, run_id, doc.id, doc.to_dict() or {})
            for doc in docs
        ]

    # ------------------------------------------------------------------
    #  Session-wide collection-group helpers
    # ------------------------------------------------------------------
    #
    #  Steps and artifacts are stored under two Firestore paths:
    #    1. sessions/{sid}/runs/{rid}/steps/{id}   (canonical)
    #    2. users/{uid}/tasks/{tid}/runs/{rid}/steps/{id}  (task mirror)
    #
    #  A collection_group("steps") query returns docs from *both*
    #  hierarchies.  We filter to the canonical "sessions/" prefix and
    #  deduplicate by document ID to prevent React key collisions in
    #  the frontend.
    # ------------------------------------------------------------------

    @staticmethod
    def _deduplicated_collection_group_docs(
        query_stream,
        *,
        canonical_prefix: str = "sessions/",
        limit: int = 500,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Yield (doc_id, doc_data) from a collection-group stream,
        keeping only canonical documents and deduplicating by ID."""
        results: list[tuple[str, dict[str, Any]]] = []
        seen: set[str] = set()
        for doc in query_stream:
            if doc.id in seen:
                continue
            if not doc.reference.path.startswith(canonical_prefix):
                continue
            seen.add(doc.id)
            results.append((doc.id, doc.to_dict() or {}))
            if len(results) >= limit:
                break
        return results

    def _list_session_steps_sync(self, session_id: str, limit: int) -> list[StoredRunStep]:
        """List steps across all runs for a session, ordered by creation time."""
        stream = (
            self._db.collection_group("steps")
            .where(filter=FieldFilter("sessionId", "==", session_id))
            .order_by("createdAt", direction=firestore.Query.ASCENDING)
            .stream()
        )
        return [
            self._build_stored_run_step(session_id, data.get("runId", ""), doc_id, data)
            for doc_id, data in self._deduplicated_collection_group_docs(stream, limit=limit)
        ]

    def _create_artifact_sync(
        self,
        session_id: str,
        run_id: str,
        kind: str,
        title: str,
        preview: str,
        source_step_id: str | None,
        path: str | None,
        url: str | None,
        metadata: dict[str, Any] | None,
    ) -> StoredArtifact:
        now = utcnow()
        session_ref = self._db.collection("sessions").document(session_id)
        run_ref = session_ref.collection("runs").document(run_id)
        artifact_id = uuid.uuid4().hex[:12]
        artifact_ref = run_ref.collection("artifacts").document(artifact_id)
        transaction = self._db.transaction()

        @firestore.transactional
        def transactional_create(txn):
            run_snapshot = run_ref.get(transaction=txn)
            session_snapshot = session_ref.get(transaction=txn)
            session_data = session_snapshot.to_dict() or {} if session_snapshot.exists else {}

            if not run_snapshot.exists:
                owner_id = session_data.get("ownerId") if isinstance(session_data.get("ownerId"), str) else ""
                task_id = session_data.get("taskId") if isinstance(session_data.get("taskId"), str) else session_id
                run_payload = {
                    "ownerId": owner_id,
                    "sessionId": session_id,
                    "taskId": task_id,
                    "status": "running",
                    "title": "Agent Turn",
                    "createdAt": now,
                    "updatedAt": now,
                    "stepCount": 0,
                    "artifactCount": 0,
                }
                txn.set(run_ref, run_payload, merge=True)
                if owner_id:
                    task_run_ref = self._task_run_ref(owner_id, task_id, run_id)
                    txn.set(task_run_ref, run_payload, merge=True)
                run_data = run_payload
            else:
                run_data = run_snapshot.to_dict() or {}

            owner_id = run_data.get("ownerId") if isinstance(run_data.get("ownerId"), str) else ""
            task_id = run_data.get("taskId") if isinstance(run_data.get("taskId"), str) else session_data.get("taskId") or session_id
            run_artifact_count = int(run_data.get("artifactCount", 0) or 0) + 1
            session_artifact_count = int(session_data.get("artifactCount", 0) or 0) + 1

            payload: dict[str, Any] = {
                "artifactId": artifact_id,
                "sessionId": session_id,
                "taskId": task_id,
                "runId": run_id,
                "ownerId": owner_id,
                "kind": kind,
                "title": title,
                "preview": preview,
                "createdAt": now,
                "metadata": metadata or {},
            }
            if source_step_id:
                payload["sourceStepId"] = source_step_id
            if path:
                payload["path"] = path
            if url:
                payload["url"] = url

            txn.set(artifact_ref, payload)
            if owner_id:
                task_ref = self._task_ref(owner_id, str(task_id))
                task_run_ref = task_ref.collection("runs").document(run_id)
                txn.set(task_ref.collection("artifacts").document(artifact_id), payload)
                txn.set(task_run_ref.collection("artifacts").document(artifact_id), payload)
                txn.set(
                    task_run_ref,
                    {
                        "artifactCount": run_artifact_count,
                        "updatedAt": now,
                    },
                    merge=True,
                )
                txn.set(
                    task_ref,
                    {
                        "currentSessionId": session_id,
                        "currentRunId": run_id,
                        "artifactCount": session_artifact_count,
                        "hasArtifacts": True,
                        "updatedAt": now,
                    },
                    merge=True,
                )
            txn.set(
                run_ref,
                {
                    "artifactCount": run_artifact_count,
                    "updatedAt": now,
                },
                merge=True,
            )
            txn.set(
                session_ref,
                {
                    "artifactCount": session_artifact_count,
                    "hasArtifacts": True,
                    "updatedAt": now,
                },
                merge=True,
            )
            return payload

        payload = transactional_create(transaction)
        return self._build_stored_artifact(session_id, run_id, artifact_id, payload)

    def _get_artifact_for_owner_sync(self, owner_id: str, artifact_id: str) -> StoredArtifact | None:
        docs = (
            self._db.collection_group("artifacts")
            .where(filter=FieldFilter("ownerId", "==", owner_id))
            .where(filter=FieldFilter("artifactId", "==", artifact_id))
            .limit(1)
            .stream()
        )
        for doc in docs:
            data = doc.to_dict() or {}
            session_id = str(data.get("sessionId") or "")
            run_id = str(data.get("runId") or "")
            if session_id and run_id:
                return self._build_stored_artifact(session_id, run_id, doc.id, data)
        return None

    def _list_run_artifacts_sync(self, session_id: str, run_id: str, limit: int) -> list[StoredArtifact]:
        docs = (
            self._db.collection("sessions")
            .document(session_id)
            .collection("runs")
            .document(run_id)
            .collection("artifacts")
            .order_by("createdAt", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        return [
            self._build_stored_artifact(session_id, run_id, doc.id, doc.to_dict() or {})
            for doc in docs
        ]

    def _list_session_artifacts_sync(self, session_id: str, limit: int) -> list[StoredArtifact]:
        """List artifacts across all runs for a session, newest first."""
        stream = (
            self._db.collection_group("artifacts")
            .where(filter=FieldFilter("sessionId", "==", session_id))
            .order_by("createdAt", direction=firestore.Query.DESCENDING)
            .stream()
        )
        return [
            self._build_stored_artifact(session_id, data.get("runId", ""), doc_id, data)
            for doc_id, data in self._deduplicated_collection_group_docs(stream, limit=limit)
        ]

    _LIBRARY_FETCH_CAP = 400

    @staticmethod
    def _is_missing_firestore_index_error(exc: BaseException) -> bool:
        message = str(exc).lower()
        return "index" in message and (
            isinstance(exc, FailedPrecondition)
            or "requires an index" in message
            or "currently building" in message
        )

    def _list_owner_library_artifacts_sync(
        self,
        owner_id: str,
        limit: int,
        cursor: datetime | None,
        search: str | None,
        category: str | None,
    ) -> tuple[list[Any], datetime | None]:
        """List deliverable artifacts for a user, excluding scrapes/sources.

        Uses per-session listing because the collection-group index
        artifacts(ownerId ASC, createdAt DESC) is not deployed in all
        environments yet. A FailedPrecondition on that query was being
        mapped to HTTP 503 by the global Google API handler.
        """
        return self._list_owner_library_artifacts_via_sessions_sync(
            owner_id,
            limit,
            cursor,
            search,
            category,
        )

    def _list_owner_library_artifacts_collection_group_sync(
        self,
        owner_id: str,
        limit: int,
        cursor: datetime | None,
        search: str | None,
        category: str | None,
    ) -> tuple[list[Any], datetime | None]:
        from nexus.library_artifacts import (
            LIBRARY_CATEGORIES,
            LibraryListRow,
            is_library_artifact,
            library_category,
            matches_library_search,
        )

        page_limit = max(1, min(int(limit or 100), 100))
        category_filter = category if category in LIBRARY_CATEGORIES else None
        search_query = search.strip() if isinstance(search, str) and search.strip() else None

        collected: list[LibraryListRow] = []
        page_cursor = cursor
        exhausted = False
        title_cache: dict[str, str] = {}

        while len(collected) < page_limit and not exhausted:
            query = (
                self._db.collection_group("artifacts")
                .where(filter=FieldFilter("ownerId", "==", owner_id))
                .order_by("createdAt", direction=firestore.Query.DESCENDING)
            )
            if page_cursor is not None:
                query = query.start_after(page_cursor)
            query = query.limit(self._LIBRARY_FETCH_CAP)
            batch: list[StoredArtifact] = []
            for doc_id, data in self._deduplicated_collection_group_docs(
                query.stream(),
                limit=self._LIBRARY_FETCH_CAP,
            ):
                session_id = str(data.get("sessionId") or "")
                run_id = str(data.get("runId") or "")
                if not session_id:
                    continue
                batch.append(self._build_stored_artifact(session_id, run_id, doc_id, data))

            if not batch:
                exhausted = True
                break

            page_cursor = batch[-1].created_at
            if len(batch) < self._LIBRARY_FETCH_CAP:
                exhausted = True

            eligible = [artifact for artifact in batch if is_library_artifact(artifact)]
            self._hydrate_session_titles(eligible, title_cache)
            for artifact in eligible:
                session_title = title_cache.get(artifact.session_id, "Untitled session")
                mapped = library_category(artifact)
                if category_filter and mapped != category_filter:
                    continue
                if search_query and not matches_library_search(artifact, session_title, search_query):
                    continue
                collected.append(
                    LibraryListRow(
                        artifact=artifact,
                        session_title=session_title,
                        category=mapped,
                    )
                )
                if len(collected) >= page_limit:
                    break

        next_cursor = None
        if collected and len(collected) >= page_limit:
            next_cursor = collected[-1].artifact.created_at
        return collected, next_cursor

    def _list_owner_library_artifacts_via_sessions_sync(
        self,
        owner_id: str,
        limit: int,
        cursor: datetime | None,
        search: str | None,
        category: str | None,
    ) -> tuple[list[Any], datetime | None]:
        """Fallback when the ownerId+createdAt collection-group index is missing."""
        from nexus.library_artifacts import (
            LIBRARY_CATEGORIES,
            LibraryListRow,
            is_library_artifact,
            library_category,
            matches_library_search,
        )

        page_limit = max(1, min(int(limit or 100), 100))
        category_filter = category if category in LIBRARY_CATEGORIES else None
        search_query = search.strip() if isinstance(search, str) and search.strip() else None

        rows: list[LibraryListRow] = []
        for session_id, data in self._list_owner_sessions_sync(owner_id):
            if data.get("status") == "deleted":
                continue
            has_artifacts = bool(data.get("hasArtifacts"))
            artifact_count = int(data.get("artifactCount") or 0)
            if not has_artifacts and artifact_count <= 0:
                continue
            raw_title = data.get("title")
            session_title = (
                raw_title.strip()
                if isinstance(raw_title, str) and raw_title.strip()
                else "Untitled session"
            )
            try:
                session_artifacts = self._list_session_run_artifacts_sync(session_id, 200)
            except GoogleAPICallError:
                logger.warning(
                    "Skipping library artifacts for session %s",
                    session_id,
                    exc_info=True,
                )
                continue
            for artifact in session_artifacts:
                if not is_library_artifact(artifact):
                    continue
                mapped = library_category(artifact)
                if category_filter and mapped != category_filter:
                    continue
                if search_query and not matches_library_search(artifact, session_title, search_query):
                    continue
                created_at = artifact.created_at
                if cursor is not None and created_at and created_at >= cursor:
                    continue
                rows.append(
                    LibraryListRow(
                        artifact=artifact,
                        session_title=session_title,
                        category=mapped,
                    )
                )

        rows.sort(
            key=lambda row: row.artifact.created_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        page = rows[:page_limit]
        next_cursor = page[-1].artifact.created_at if len(rows) > page_limit else None
        return page, next_cursor

    def _list_session_run_artifacts_sync(self, session_id: str, limit: int = 200) -> list[StoredArtifact]:
        """List artifacts from session run subcollections. No collection-group index required."""
        artifacts: list[StoredArtifact] = []
        runs = self._db.collection("sessions").document(session_id).collection("runs").stream()
        for run_doc in runs:
            run_id = run_doc.id
            docs = (
                run_doc.reference.collection("artifacts")
                .order_by("createdAt", direction=firestore.Query.DESCENDING)
                .limit(max(1, limit))
                .stream()
            )
            for doc in docs:
                artifacts.append(
                    self._build_stored_artifact(session_id, run_id, doc.id, doc.to_dict() or {})
                )
        artifacts.sort(
            key=lambda artifact: artifact.created_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        unique: list[StoredArtifact] = []
        seen: set[str] = set()
        for artifact in artifacts:
            if artifact.artifact_id in seen:
                continue
            seen.add(artifact.artifact_id)
            unique.append(artifact)
            if len(unique) >= limit:
                break
        return unique

    def _hydrate_session_titles(
        self,
        artifacts: list[StoredArtifact],
        cache: dict[str, str],
    ) -> None:
        missing = {
            artifact.session_id
            for artifact in artifacts
            if artifact.session_id and artifact.session_id not in cache
        }
        if not missing:
            return
        refs = [self._db.collection("sessions").document(session_id) for session_id in missing]
        snapshots = self._db.get_all(refs)
        for snapshot in snapshots:
            title = "Untitled session"
            if snapshot.exists:
                data = snapshot.to_dict() or {}
                raw = data.get("title")
                if isinstance(raw, str) and raw.strip():
                    title = raw.strip()
            cache[snapshot.id] = title
        for session_id in missing:
            cache.setdefault(session_id, "Untitled session")

    def _append_message_time_ordered(
        self,
        session_id: str,
        owner_id: str,
        role: str,
        source: str,
        text: str,
    ) -> None:
        """Append a message without a read-modify-write counter.

        Uses time-ordered message IDs and an epoch-microsecond ``turnIndex``
        for ordering, and bumps ``messageCount`` via an atomic ``Increment``.
        This removes the shared-doc counter read from the hot path so parallel
        appends no longer contend inside a Firestore transaction. Ordering
        readers (backend/frontend ``order_by("turnIndex")``) keep working: the
        epoch-microsecond values sort after any legacy dense indices, so mixed
        legacy + new histories still render in the correct order.
        """
        session_ref = self._db.collection("sessions").document(session_id)
        snapshot = session_ref.get()
        if not snapshot.exists:
            raise ValueError(f"Session {session_id} does not exist")

        data = snapshot.to_dict() or {}
        task_id = (
            data.get("taskId")
            if isinstance(data.get("taskId"), str) and data.get("taskId")
            else session_id
        )
        run_id = (
            data.get("currentRunId")
            if isinstance(data.get("currentRunId"), str)
            else None
        )
        task_ref = self._task_ref(owner_id, task_id)
        task_snapshot = task_ref.get()
        task_data = task_snapshot.to_dict() or {}

        now = utcnow()
        # Zero-padded epoch microseconds keep the doc ID lexicographically
        # time-sortable; the random suffix guarantees uniqueness.
        epoch_us = int(now.timestamp() * 1_000_000)
        turn_index = epoch_us
        message_id = f"{epoch_us:016d}-{uuid.uuid4().hex[:8]}"
        task_message_id = f"{epoch_us:016d}-{uuid.uuid4().hex[:8]}"
        message_ref = session_ref.collection("messages").document(message_id)
        message_payload = {
            "role": role,
            "source": source,
            "text": text,
            "createdAt": now,
            "turnIndex": turn_index,
            "ownerId": owner_id,
            "sessionId": session_id,
            "taskId": task_id,
        }
        if run_id:
            message_payload["runId"] = run_id

        task_message_payload = {
            **message_payload,
            "turnIndex": turn_index,
            "sessionMessageId": message_id,
        }

        updates: dict[str, Any] = {
            "messageCount": firestore.Increment(1),
            "updatedAt": now,
        }
        task_updates: dict[str, Any] = {
            "ownerId": owner_id,
            "taskId": task_id,
            "currentSessionId": session_id,
            "currentRunId": run_id,
            "messageCount": firestore.Increment(1),
            "updatedAt": now,
            "schemaVersion": 1,
        }
        if not task_snapshot.exists:
            task_updates["createdAt"] = data.get("createdAt") or now
        if role == "user":
            updates["lastUserAt"] = now
            task_updates["lastUserAt"] = now
            if data.get("title") in (None, "", "New session"):
                updates["title"] = text[:80]
            if task_data.get("title") in (None, "", "New task"):
                task_updates["title"] = text[:80]
        elif role == "agent":
            updates["lastAgentAt"] = now
            task_updates["lastAgentAt"] = now

        # A batch is atomic and, unlike a transaction, performs no
        # read-modify-write, so concurrent appends cannot abort each other.
        batch = self._db.batch()
        batch.set(message_ref, message_payload)
        batch.set(
            task_ref.collection("messages").document(task_message_id),
            task_message_payload,
        )
        batch.set(session_ref, updates, merge=True)
        batch.set(task_ref, task_updates, merge=True)
        batch.commit()

    def _append_message_sync(
        self,
        session_id: str,
        owner_id: str,
        role: str,
        source: str,
        text: str,
    ) -> None:
        if settings.use_time_ordered_message_ids:
            self._append_message_time_ordered(
                session_id, owner_id, role, source, text
            )
            return
        session_ref = self._db.collection("sessions").document(session_id)
        transaction = self._db.transaction()

        @firestore.transactional
        def transactional_append(txn):
            snapshot = session_ref.get(transaction=txn)
            if not snapshot.exists:
                raise ValueError(f"Session {session_id} does not exist")

            data = snapshot.to_dict() or {}
            task_id = data.get("taskId") if isinstance(data.get("taskId"), str) and data.get("taskId") else session_id
            run_id = data.get("currentRunId") if isinstance(data.get("currentRunId"), str) else None
            task_ref = self._task_ref(owner_id, task_id)
            task_snapshot = task_ref.get(transaction=txn)
            task_data = task_snapshot.to_dict() or {}
            next_index = int(data.get("messageCount", 0)) + 1
            task_next_index = int(task_data.get("messageCount", 0) or 0) + 1
            now = utcnow()
            message_id = f"{next_index:06d}-{uuid.uuid4().hex[:8]}"
            task_message_id = f"{task_next_index:06d}-{uuid.uuid4().hex[:8]}"
            message_ref = session_ref.collection("messages").document(message_id)
            message_payload = {
                "role": role,
                "source": source,
                "text": text,
                "createdAt": now,
                "turnIndex": next_index,
                "ownerId": owner_id,
                "sessionId": session_id,
                "taskId": task_id,
            }
            if run_id:
                message_payload["runId"] = run_id

            task_message_payload = {
                **message_payload,
                "turnIndex": task_next_index,
                "sessionMessageId": message_id,
            }

            txn.set(message_ref, message_payload)
            txn.set(task_ref.collection("messages").document(task_message_id), task_message_payload)

            updates: dict[str, Any] = {
                "messageCount": next_index,
                "updatedAt": now,
            }
            task_updates: dict[str, Any] = {
                "ownerId": owner_id,
                "taskId": task_id,
                "currentSessionId": session_id,
                "currentRunId": run_id,
                "messageCount": task_next_index,
                "updatedAt": now,
                "schemaVersion": 1,
            }
            if not task_snapshot.exists:
                task_updates["createdAt"] = data.get("createdAt") or now
            if role == "user":
                updates["lastUserAt"] = now
                task_updates["lastUserAt"] = now
                if data.get("title") in (None, "", "New session"):
                    updates["title"] = text[:80]
                if task_data.get("title") in (None, "", "New task"):
                    task_updates["title"] = text[:80]
            elif role == "agent":
                updates["lastAgentAt"] = now
                task_updates["lastAgentAt"] = now
            txn.set(session_ref, updates, merge=True)
            txn.set(task_ref, task_updates, merge=True)

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
    ) -> tuple[int, dict[str, int]]:
        if input_tokens < 0 or output_tokens < 0 or total_tokens < 0:
            return 0, {"input": 0, "output": 0, "total": 0}

        credits_charged = calculate_usage_credits(
            source=source,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )

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

            credit_totals = data.get("creditTotals") if isinstance(data.get("creditTotals"), dict) else {}
            credit_by_source = (
                credit_totals.get("bySource")
                if isinstance(credit_totals.get("bySource"), dict)
                else {}
            )
            credit_total = int(credit_totals.get("total", 0) or 0)
            if credits_charged > 0:
                credit_total += credits_charged
                credit_by_source[source] = int(credit_by_source.get(source, 0) or 0) + credits_charged

            usage_ref = session_ref.collection("usage_events").document(
                f"{now.strftime('%Y%m%d%H%M%S%f')}-{uuid.uuid4().hex[:8]}"
            )
            usage_payload: dict[str, Any] = {
                "ownerId": owner_id,
                "sessionId": session_id,
                "source": source,
                "model": model,
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
                "totalTokens": total_tokens,
                "createdAt": now,
            }
            if credits_charged > 0:
                usage_payload.update(
                    {
                        "creditsCharged": credits_charged,
                        "creditUnit": "credits",
                    }
                )
            txn.set(usage_ref, usage_payload)
            updates: dict[str, Any] = {
                "tokenTotals": totals,
                "lastUsage": {
                    "model": model,
                    "source": source,
                    "inputTokens": input_tokens,
                    "outputTokens": output_tokens,
                    "totalTokens": total_tokens,
                },
                "updatedAt": now,
            }
            if credits_charged > 0:
                updates["creditTotals"] = {
                    "total": credit_total,
                    "bySource": credit_by_source,
                }
            if data.get("tokenTrackingStartedAt") is None:
                updates["tokenTrackingStartedAt"] = now
            txn.set(session_ref, updates, merge=True)
            return credits_charged, {
                "input": int(totals["input"]),
                "output": int(totals["output"]),
                "total": int(totals["total"]),
            }

        return transactional_append(transaction)

    def _record_credit_charge_sync(
        self,
        session_id: str,
        owner_id: str,
        source: str,
        model: str,
        credits: int,
        metadata: dict[str, Any] | None,
    ) -> None:
        if credits <= 0:
            return

        session_ref = self._db.collection("sessions").document(session_id)
        transaction = self._db.transaction()

        @firestore.transactional
        def transactional_record(txn):
            snapshot = session_ref.get(transaction=txn)
            if not snapshot.exists:
                raise ValueError(f"Session {session_id} does not exist")

            now = utcnow()
            data = snapshot.to_dict() or {}
            credit_totals = data.get("creditTotals") if isinstance(data.get("creditTotals"), dict) else {}
            credit_by_source = (
                credit_totals.get("bySource")
                if isinstance(credit_totals.get("bySource"), dict)
                else {}
            )
            credit_by_source[source] = int(credit_by_source.get(source, 0) or 0) + credits
            total = int(credit_totals.get("total", 0) or 0) + credits

            event_ref = session_ref.collection("credit_events").document(
                f"{now.strftime('%Y%m%d%H%M%S%f')}-{uuid.uuid4().hex[:8]}"
            )
            txn.set(
                event_ref,
                {
                    "ownerId": owner_id,
                    "sessionId": session_id,
                    "source": source,
                    "model": model,
                    "credits": credits,
                    "unit": "credits",
                    "metadata": metadata or {},
                    "createdAt": now,
                },
            )
            txn.set(
                session_ref,
                {
                    "creditTotals": {
                        "total": total,
                        "bySource": credit_by_source,
                    },
                    "updatedAt": now,
                },
                merge=True,
            )

        transactional_record(transaction)

    def _record_tool_memory_sync(
        self,
        session_id: str,
        kind: str,
        summary: str,
        content_hash: str,
        source_step_id: str | None,
        metadata: dict[str, Any] | None,
    ) -> None:
        clean_summary = self._clip_text(summary, 700)
        if not clean_summary:
            return

        session_ref = self._db.collection("sessions").document(session_id)
        snapshot = session_ref.get()
        if not snapshot.exists:
            return

        data = snapshot.to_dict() or {}
        existing = self._normalize_tool_memories(data.get("toolMemories"))
        dedupe_key = content_hash.strip()
        next_entries: list[dict[str, Any]] = []

        if dedupe_key:
            for item in existing:
                if item.get("hash") == dedupe_key and item.get("kind") == kind:
                    item = {
                        **item,
                        "summary": clean_summary,
                        "sourceStepId": source_step_id or item.get("sourceStepId"),
                        "metadata": metadata or item.get("metadata") or {},
                        "createdAt": utcnow(),
                    }
                    next_entries.append(item)
                else:
                    next_entries.append(item)
            if next_entries != existing:
                session_ref.set(
                    {
                        "toolMemories": next_entries[:20],
                        "updatedAt": utcnow(),
                    },
                    merge=True,
                )
                return

        next_entries = [
            {
                "kind": kind[:40],
                "summary": clean_summary,
                "hash": dedupe_key,
                "sourceStepId": source_step_id,
                "metadata": metadata or {},
                "createdAt": utcnow(),
            }
        ]
        next_entries.extend(existing)
        session_ref.set(
            {
                "toolMemories": next_entries[:20],
                "updatedAt": utcnow(),
            },
            merge=True,
        )

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

            if data.get("status") in ("creating", "ready", "active") and data.get("sandboxId"):
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
            handoff_summary = data.get("handoffSummary", {})
            handoff_preview = ""
            if isinstance(handoff_summary, dict):
                raw_preview = handoff_summary.get("preview")
                handoff_preview = raw_preview.lower() if isinstance(raw_preview, str) else ""

            # Application-side search filtering (since Firestore lacks full-text search)
            if search_text:
                title_text = title.lower() if isinstance(title, str) else ""
                summary_text = summary.lower() if isinstance(summary, str) else ""
                if (
                    search_text not in title_text
                    and search_text not in summary_text
                    and search_text not in handoff_preview
                ):
                    continue

            updated_at = self._coerce_datetime(data.get("updatedAt"))
            created_at = self._coerce_datetime(data.get("createdAt"))
            sort_key = updated_at or created_at or datetime.min.replace(tzinfo=timezone.utc)
            sessions.append((sort_key, self._build_stored_session(session_id, data)))

        sessions.sort(key=lambda item: item[0], reverse=True)
        return [session for _, session in sessions[:limit]]

    def _get_task_sync(self, owner_id: str, task_id: str) -> StoredTask | None:
        doc = self._task_ref(owner_id, task_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        if data.get("ownerId") != owner_id:
            return None
        return self._build_stored_task(doc.id, data)

    def _list_tasks_sync(self, owner_id: str, limit: int, status: str | None, search: str | None) -> list[StoredTask]:
        if status == "deleted":
            return []
        query = self._user_public_ref(owner_id).collection("tasks").order_by(
            "createdAt",
            direction=firestore.Query.DESCENDING,
        )
        if status:
            query = query.where(filter=FieldFilter("status", "==", status))
        search_text = search.strip().lower() if search else None
        tasks: list[tuple[datetime, StoredTask]] = []
        for doc in query.limit(max(limit * 3, limit)).stream():
            task = self._build_stored_task(doc.id, doc.to_dict() or {})
            if search_text and search_text not in task.title.lower() and search_text not in task.status.lower():
                continue
            sort_key = task.updated_at or task.created_at
            tasks.append((sort_key, task))
        seen_task_ids = {task.task_id for _, task in tasks}
        for session in self._list_sessions_sync(owner_id, limit, status, search):
            if session.task_id in seen_task_ids:
                continue
            tasks.append(
                (
                    session.ended_at or session.created_at,
                    StoredTask(
                        task_id=session.task_id,
                        owner_id=session.owner_id,
                        title=session.title,
                        status=session.run_status or session.status,
                        created_at=session.created_at,
                        updated_at=session.ended_at,
                        current_session_id=session.session_id,
                        current_run_id=session.current_run_id,
                        run_status=session.run_status,
                        message_count=session.message_count,
                        artifact_count=session.artifact_count,
                    ),
                )
            )
        tasks.sort(key=lambda item: item[0], reverse=True)
        return [task for _, task in tasks[:limit]]

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

    def _list_active_sessions_sync(self, owner_id: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            from google.cloud import firestore
            docs = self._db.collection("sessions").where(filter=firestore.FieldFilter("ownerId", "==", owner_id)).where(filter=firestore.FieldFilter("status", "in", ["creating", "ready", "active"])).get()
            for doc in docs:
                session_id = doc.id
                data = doc.to_dict() or {}
                sandbox_id = data.get("sandboxId") if isinstance(data.get("sandboxId"), str) else ""
                if not sandbox_id:
                    continue
                stored_session = self._build_stored_session(session_id, data)
                results.append({
                    "session_id": session_id,
                    "title": stored_session.title,
                    "status": stored_session.status,
                    "created_at": stored_session.created_at,
                    "last_active_at": data.get("lastActiveAt") or stored_session.created_at,
                    "stream_url": None,
                    "sandbox_id": sandbox_id,
                    "message_count": stored_session.message_count,
                    "token_totals": stored_session.token_totals,
                    "token_tracking_started_at": stored_session.token_tracking_started_at,
                    "token_coverage": 1.0,
                    "current_run_id": stored_session.current_run_id,
                    "run_status": stored_session.run_status,
                    "artifact_count": stored_session.artifact_count,
                })
        except Exception:
            pass
        return results

    def _list_all_active_sandbox_ids_sync(self) -> list[str]:
        """Return a list of all sandbox IDs associated with active sessions across all users."""
        sandbox_ids = set()
        try:
            from google.cloud import firestore
            # Check active sessions
            docs = self._db.collection("sessions").where(filter=firestore.FieldFilter("status", "in", ["creating", "ready", "active"])).get()
            for doc in docs:
                sid = doc.to_dict().get("sandboxId")
                if sid:
                    sandbox_ids.add(sid)

            # Check users with paused sandboxes
            users = self._db.collection("userPublic").where(filter=firestore.FieldFilter("pausedSandboxId", "!=", None)).get()
            for user in users:
                sid = user.to_dict().get("pausedSandboxId")
                if sid:
                    sandbox_ids.add(sid)
        except Exception:
            pass
        return list(sandbox_ids)

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

    def _refresh_session_handoff_sync(
        self,
        session_id: str,
        owner_id: str,
        resume_state: str | None,
        workspace_owner_session_id: str | None,
        can_continue_workspace: bool | None,
    ) -> None:
        session_ref = self._db.collection("sessions").document(session_id)
        snapshot = session_ref.get()
        if not snapshot.exists:
            return

        data = snapshot.to_dict() or {}
        workspace_state = self._get_workspace_state_sync(owner_id)
        current_workspace_owner = workspace_owner_session_id or workspace_state.get("session_id")
        current_can_continue = (
            can_continue_workspace
            if can_continue_workspace is not None
            else current_workspace_owner == session_id and bool(workspace_state.get("sandbox_id"))
        )
        messages = self._get_session_messages_sync(session_id)
        run = self._get_session_run_sync(session_id)
        steps = self._list_session_steps_sync(session_id, 50)
        artifacts = self._list_session_artifacts_sync(session_id, 25)
        handoff_summary = self._build_handoff_summary(
            session_id,
            data,
            messages,
            run=run,
            steps=steps,
            artifacts=artifacts,
            can_continue_workspace=current_can_continue,
        )
        context_packet = self._build_context_packet(
            data,
            messages,
            handoff_summary=handoff_summary,
            run=run,
            steps=steps,
            artifacts=artifacts,
        )
        existing_packet = data.get("contextPacket") if isinstance(data.get("contextPacket"), dict) else None
        existing_inputs_digest = (
            data.get("contextPacketInputsDigest")
            if isinstance(data.get("contextPacketInputsDigest"), str)
            else None
        )
        if (
            existing_packet
            and existing_inputs_digest
            and existing_inputs_digest == context_packet.get("inputsDigest")
        ):
            context_packet = existing_packet
        session_ref.set(
            {
                "handoffSummary": handoff_summary,
                "contextPacket": context_packet,
                "contextPacketInputsDigest": context_packet.get("inputsDigest", ""),
                "hasArtifacts": bool(artifacts),
                "artifactCount": len(artifacts) if artifacts else int(data.get("artifactCount", 0) or 0),
                "canContinueWorkspace": current_can_continue,
                "canContinueConversation": True,
                "exactWorkspaceResumeAvailable": current_can_continue,
                "continuationMode": "exact_workspace_resume" if current_can_continue else "new_sandbox_resume",
                "resumeState": resume_state or ("paused" if current_can_continue else data.get("resumeState", "ended")),
                "workspaceOwnerSessionId": current_workspace_owner if current_can_continue else None,
                "currentRunId": run.run_id if run else data.get("currentRunId"),
                "runStatus": run.status if run else data.get("runStatus"),
                "updatedAt": utcnow(),
            },
            merge=True,
        )
