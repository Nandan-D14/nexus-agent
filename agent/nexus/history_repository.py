"""Firestore-backed persistence for users, sessions, and message history."""

from __future__ import annotations

import asyncio
import hashlib
import json
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
    handoff_summary: dict[str, Any] | None = None
    can_continue_workspace: bool = False
    has_artifacts: bool = False
    resume_state: str | None = None
    workspace_owner_session_id: str | None = None
    resume_source_session_id: str | None = None
    current_run_id: str | None = None
    run_status: str | None = None
    artifact_count: int = 0
    can_continue_conversation: bool = True
    exact_workspace_resume_available: bool = False
    continuation_mode: str | None = None
    context_packet: dict[str, Any] | None = None


@dataclass
class StoredRun:
    run_id: str
    session_id: str
    owner_id: str
    status: str
    created_at: datetime
    updated_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_step_at: datetime | None = None
    step_count: int = 0
    artifact_count: int = 0
    title: str = ""
    source_session_id: str | None = None


@dataclass
class StoredRunStep:
    step_id: str
    run_id: str
    session_id: str
    step_type: str
    status: str
    title: str
    detail: str
    created_at: datetime
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    step_index: int = 0
    source: str | None = None
    error: str | None = None
    external_ref: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class StoredArtifact:
    artifact_id: str
    run_id: str
    session_id: str
    kind: str
    title: str
    preview: str
    created_at: datetime
    source_step_id: str | None = None
    path: str | None = None
    url: str | None = None
    metadata: dict[str, Any] | None = None


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
            handoff_summary=data.get("handoffSummary") if isinstance(data.get("handoffSummary"), dict) else None,
            can_continue_workspace=bool(data.get("canContinueWorkspace")),
            has_artifacts=bool(data.get("hasArtifacts")),
            resume_state=data.get("resumeState") if isinstance(data.get("resumeState"), str) else None,
            workspace_owner_session_id=(
                data.get("workspaceOwnerSessionId")
                if isinstance(data.get("workspaceOwnerSessionId"), str)
                else None
            ),
            resume_source_session_id=(
                data.get("resumeSourceSessionId")
                if isinstance(data.get("resumeSourceSessionId"), str)
                else None
            ),
            current_run_id=(
                data.get("currentRunId")
                if isinstance(data.get("currentRunId"), str)
                else None
            ),
            run_status=data.get("runStatus") if isinstance(data.get("runStatus"), str) else None,
            artifact_count=int(data.get("artifactCount", 0) or 0),
            can_continue_conversation=bool(data.get("canContinueConversation", True)),
            exact_workspace_resume_available=bool(data.get("exactWorkspaceResumeAvailable")),
            continuation_mode=(
                data.get("continuationMode")
                if isinstance(data.get("continuationMode"), str)
                else None
            ),
            context_packet=data.get("contextPacket") if isinstance(data.get("contextPacket"), dict) else None,
        )

    def _build_stored_run(self, session_id: str, run_id: str, data: dict[str, Any]) -> StoredRun:
        return StoredRun(
            run_id=run_id,
            session_id=session_id,
            owner_id=data.get("ownerId", ""),
            status=data.get("status", "queued"),
            created_at=self._coerce_datetime(data.get("createdAt")) or utcnow(),
            updated_at=self._coerce_datetime(data.get("updatedAt")),
            started_at=self._coerce_datetime(data.get("startedAt")),
            completed_at=self._coerce_datetime(data.get("completedAt")),
            last_step_at=self._coerce_datetime(data.get("lastStepAt")),
            step_count=int(data.get("stepCount", 0) or 0),
            artifact_count=int(data.get("artifactCount", 0) or 0),
            title=data.get("title") if isinstance(data.get("title"), str) else "",
            source_session_id=(
                data.get("sourceSessionId")
                if isinstance(data.get("sourceSessionId"), str)
                else None
            ),
        )

    def _build_stored_run_step(self, session_id: str, run_id: str, step_id: str, data: dict[str, Any]) -> StoredRunStep:
        return StoredRunStep(
            step_id=step_id,
            run_id=run_id,
            session_id=session_id,
            step_type=data.get("stepType", "system_event"),
            status=data.get("status", "queued"),
            title=data.get("title") if isinstance(data.get("title"), str) else "",
            detail=data.get("detail") if isinstance(data.get("detail"), str) else "",
            created_at=self._coerce_datetime(data.get("createdAt")) or utcnow(),
            updated_at=self._coerce_datetime(data.get("updatedAt")),
            completed_at=self._coerce_datetime(data.get("completedAt")),
            step_index=int(data.get("stepIndex", 0) or 0),
            source=data.get("source") if isinstance(data.get("source"), str) else None,
            error=data.get("error") if isinstance(data.get("error"), str) else None,
            external_ref=(
                data.get("externalRef")
                if isinstance(data.get("externalRef"), str)
                else None
            ),
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
        )

    def _build_stored_artifact(self, session_id: str, run_id: str, artifact_id: str, data: dict[str, Any]) -> StoredArtifact:
        return StoredArtifact(
            artifact_id=artifact_id,
            run_id=run_id,
            session_id=session_id,
            kind=data.get("kind", "text_output"),
            title=data.get("title") if isinstance(data.get("title"), str) else "",
            preview=data.get("preview") if isinstance(data.get("preview"), str) else "",
            created_at=self._coerce_datetime(data.get("createdAt")) or utcnow(),
            source_step_id=(
                data.get("sourceStepId")
                if isinstance(data.get("sourceStepId"), str)
                else None
            ),
            path=data.get("path") if isinstance(data.get("path"), str) else None,
            url=data.get("url") if isinstance(data.get("url"), str) else None,
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
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

        latest_completed_steps = [step for step in steps if step.status == "completed"]
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

        packet = {
            "summary": self._clip_text(
                handoff_summary.get("preview") or data.get("summary") or latest_run_summary,
                320,
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
        }
        digest_source = json.dumps(packet, sort_keys=True, ensure_ascii=True)
        packet["digest"] = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:16]
        return packet

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
        ref.set(payload, merge=True)

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
        run_ref = session_ref.collection("runs").document(run_id)
        payload: dict[str, Any] = {
            "ownerId": owner_id,
            "sessionId": session_id,
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
        batch.set(
            session_ref,
            {
                "currentRunId": run_id,
                "runStatus": "queued",
                "artifactCount": int((session_ref.get().to_dict() or {}).get("artifactCount", 0) or 0),
                "updatedAt": now,
            },
            merge=True,
        )
        batch.commit()
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
        run_ref = self._db.collection("sessions").document(session_id).collection("runs").document(run_id)
        run_doc = run_ref.get()
        if not run_doc.exists:
            return None

        current = run_doc.to_dict() or {}
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
            if not run_snapshot.exists:
                raise ValueError(f"Run {run_id} does not exist for session {session_id}")

            run_data = run_snapshot.to_dict() or {}
            step_index = int(run_data.get("stepCount", 0) or 0) + 1
            payload: dict[str, Any] = {
                "sessionId": session_id,
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
            if not run_snapshot.exists:
                raise ValueError(f"Run {run_id} does not exist for session {session_id}")

            session_snapshot = session_ref.get(transaction=txn)
            session_data = session_snapshot.to_dict() or {}
            run_data = run_snapshot.to_dict() or {}
            run_artifact_count = int(run_data.get("artifactCount", 0) or 0) + 1
            session_artifact_count = int(session_data.get("artifactCount", 0) or 0) + 1

            payload: dict[str, Any] = {
                "sessionId": session_id,
                "runId": run_id,
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
        return self._get_workspace_state_sync(owner_id).get("sandbox_id")

    def _get_workspace_state_sync(self, owner_id: str) -> dict[str, str | None]:
        doc = self._db.collection("users").document(owner_id).get()
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
        user_ref = self._db.collection("users").document(owner_id)
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
        steps = self._list_run_steps_sync(session_id, run.run_id, 50) if run else []
        artifacts = self._list_run_artifacts_sync(session_id, run.run_id, 25) if run else []
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
        session_ref.set(
            {
                "handoffSummary": handoff_summary,
                "contextPacket": context_packet,
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
