# Proprietary and non-commercial use only.

"""Shared base for Firestore-backed repositories.

Provides the lazy Firestore client, common document-ref helpers, value
coercion utilities, and the ``StoredX`` projection builders. Every focused
history repository (and the ``FirestoreHistoryRepository`` facade) subclasses
this so the shared helpers keep their original ``self._method(...)`` call sites
unchanged.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from firebase_admin import firestore

from nexus.firebase import get_firestore_client
from nexus.history_models import (
    StoredArtifact,
    StoredIntegrationConnection,
    StoredRun,
    StoredRunStep,
    StoredSession,
    StoredTask,
    StoredWorkflowTemplate,
    utcnow,
)


class FirestoreRepoBase:
    """Sync Firestore access shared by the focused history repositories."""

    @property
    def _db(self):
        return get_firestore_client()

    def _user_public_ref(self, uid: str):
        return self._db.collection("users").document(uid)

    def _user_private_ref(self, uid: str):
        return self._db.collection("userPrivate").document(uid)

    def _task_ref(self, uid: str, task_id: str):
        return self._user_public_ref(uid).collection("tasks").document(task_id)

    def _task_run_ref(self, uid: str, task_id: str, run_id: str):
        return self._task_ref(uid, task_id).collection("runs").document(run_id)

    def _create_audit_log_sync(
        self,
        actor_uid: str,
        action: str,
        target_uid: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> None:
        def hash_dict(d: dict[str, Any] | None) -> str | None:
            if d is None:
                return None
            s = json.dumps(d, sort_keys=True, default=str)
            return hashlib.sha256(s.encode("utf-8")).hexdigest()

        log_ref = self._db.collection("audit_logs").document()
        log_ref.set({
            "actorUid": actor_uid,
            "action": action,
            "targetUid": target_uid,
            "before": hash_dict(before),
            "after": hash_dict(after),
            "timestamp": utcnow(),
        })

    def _task_id_for_session_sync(self, session_id: str) -> str:
        data = self._db.collection("sessions").document(session_id).get().to_dict() or {}
        task_id = data.get("taskId")
        return task_id if isinstance(task_id, str) and task_id else session_id

    def _task_id_for_run_sync(self, session_id: str, run_id: str) -> str:
        data = (
            self._db.collection("sessions")
            .document(session_id)
            .collection("runs")
            .document(run_id)
            .get()
            .to_dict()
            or {}
        )
        task_id = data.get("taskId")
        return task_id if isinstance(task_id, str) and task_id else self._task_id_for_session_sync(session_id)

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

    @staticmethod
    def _expand_dot_notation_updates(updates: dict[str, Any]) -> dict[str, Any]:
        nested_updates: dict[str, Any] = {}
        for key, value in updates.items():
            if "." not in key:
                nested_updates[key] = value
                continue

            parts = key.split(".")
            current = nested_updates
            for part in parts[:-1]:
                current = current.setdefault(part, {})
            current[parts[-1]] = value
        return nested_updates

    def _apply_document_updates_sync(self, ref, updates: dict[str, Any]) -> None:
        if not updates:
            return
        try:
            ref.update(updates)
        except Exception:
            ref.set(self._expand_dot_notation_updates(updates), merge=True)

    @staticmethod
    def _is_private_user_setting_key(key: str) -> bool:
        return (
            key == "byok"
            or key.startswith("byok.")
            or key == "googleDriveRefreshToken"
            or key.startswith("googleDriveRefreshToken.")
            or key == "integrations"
            or key.startswith("integrations.")
        )

    @classmethod
    def _partition_user_settings_updates(
        cls,
        updates: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        public_updates: dict[str, Any] = {}
        private_updates: dict[str, Any] = {}
        for key, value in updates.items():
            if cls._is_private_user_setting_key(key):
                private_updates[key] = value
            else:
                public_updates[key] = value
        return public_updates, private_updates

    def _cleanup_public_user_sensitive_fields_sync(
        self,
        uid: str,
        *,
        delete_byok: bool = False,
        delete_google_drive_refresh_token: bool = False,
        delete_google_drive_tokens: bool = False,
    ) -> None:
        updates: dict[str, Any] = {}
        if delete_byok:
            updates["byok"] = firestore.DELETE_FIELD
        if delete_google_drive_refresh_token:
            updates["googleDriveRefreshToken"] = firestore.DELETE_FIELD
        if delete_google_drive_tokens:
            updates["googleDriveTokens"] = firestore.DELETE_FIELD
        if not updates:
            return

        public_ref = self._user_public_ref(uid)
        snapshot = public_ref.get()
        if not snapshot.exists:
            return

        updates["updatedAt"] = utcnow()
        public_ref.update(updates)

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
        task_id = data.get("taskId")
        return StoredSession(
            session_id=session_id,
            owner_id=data.get("ownerId", ""),
            task_id=task_id if isinstance(task_id, str) and task_id else session_id,
            status=data.get("status", "ended"),
            created_at=self._coerce_datetime(data.get("createdAt")) or utcnow(),
            ended_at=self._coerce_datetime(data.get("endedAt")),
            title=title.strip() if isinstance(title, str) and title.strip() else "Untitled session",
            summary=summary if isinstance(summary, str) else None,
            message_count=int(data.get("messageCount", 0)),
            token_totals=self._coerce_token_totals(data.get("tokenTotals")),
            last_usage=data.get("lastUsage") if isinstance(data.get("lastUsage"), dict) else None,
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
            context_packet_inputs_digest=(
                data.get("contextPacketInputsDigest")
                if isinstance(data.get("contextPacketInputsDigest"), str)
                else None
            ),
            sandbox_id=data.get("sandboxId") if isinstance(data.get("sandboxId"), str) else None,
        )

    def _build_stored_run(self, session_id: str, run_id: str, data: dict[str, Any]) -> StoredRun:
        task_id = data.get("taskId")
        return StoredRun(
            run_id=run_id,
            session_id=session_id,
            task_id=task_id if isinstance(task_id, str) and task_id else session_id,
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
        task_id = data.get("taskId")
        return StoredRunStep(
            step_id=step_id,
            run_id=run_id,
            session_id=session_id,
            task_id=task_id if isinstance(task_id, str) and task_id else session_id,
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
        task_id = data.get("taskId")
        return StoredArtifact(
            artifact_id=artifact_id,
            run_id=run_id,
            session_id=session_id,
            task_id=task_id if isinstance(task_id, str) and task_id else session_id,
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

    def _build_stored_task(self, task_id: str, data: dict[str, Any]) -> StoredTask:
        title = data.get("title")
        return StoredTask(
            task_id=task_id,
            owner_id=data.get("ownerId", ""),
            title=title.strip() if isinstance(title, str) and title.strip() else "Untitled task",
            status=data.get("status", "queued") if isinstance(data.get("status"), str) else "queued",
            created_at=self._coerce_datetime(data.get("createdAt")) or utcnow(),
            updated_at=self._coerce_datetime(data.get("updatedAt")),
            current_session_id=(
                data.get("currentSessionId")
                if isinstance(data.get("currentSessionId"), str)
                else None
            ),
            current_run_id=(
                data.get("currentRunId")
                if isinstance(data.get("currentRunId"), str)
                else None
            ),
            run_status=data.get("runStatus") if isinstance(data.get("runStatus"), str) else None,
            message_count=int(data.get("messageCount", 0) or 0),
            step_count=int(data.get("stepCount", 0) or 0),
            artifact_count=int(data.get("artifactCount", 0) or 0),
        )

    def _build_stored_workflow_template(self, template_id: str, data: dict[str, Any]) -> StoredWorkflowTemplate:
        input_fields = data.get("inputFields")
        normalized_fields: list[dict[str, Any]] = []
        if isinstance(input_fields, list):
            for raw in input_fields:
                if not isinstance(raw, dict):
                    continue
                key = raw.get("key") if isinstance(raw.get("key"), str) else ""
                label = raw.get("label") if isinstance(raw.get("label"), str) else key
                if not key:
                    continue
                normalized_fields.append(
                    {
                        "key": key,
                        "label": label or key,
                        "placeholder": raw.get("placeholder") if isinstance(raw.get("placeholder"), str) else "",
                        "required": bool(raw.get("required")),
                    }
                )

        source_artifacts = data.get("sourceArtifacts")
        normalized_artifacts = [
            str(item).strip()
            for item in source_artifacts
            if str(item).strip()
        ] if isinstance(source_artifacts, list) else []

        return StoredWorkflowTemplate(
            template_id=template_id,
            owner_id=data.get("ownerId", ""),
            name=data.get("name") if isinstance(data.get("name"), str) else "Workflow template",
            description=data.get("description") if isinstance(data.get("description"), str) else "",
            source_session_id=(
                data.get("sourceSessionId")
                if isinstance(data.get("sourceSessionId"), str)
                else ""
            ),
            source_run_id=(
                data.get("sourceRunId")
                if isinstance(data.get("sourceRunId"), str)
                else None
            ),
            instructions=data.get("instructions") if isinstance(data.get("instructions"), str) else "",
            input_fields=normalized_fields,
            source_artifacts=normalized_artifacts,
            created_at=self._coerce_datetime(data.get("createdAt")) or utcnow(),
            updated_at=self._coerce_datetime(data.get("updatedAt")) or utcnow(),
            last_used_at=self._coerce_datetime(data.get("lastUsedAt")),
        )

    def _build_stored_integration_connection(
        self,
        uid: str,
        connection_id: str,
        public_data: dict[str, Any],
        private_data: dict[str, Any] | None = None,
    ) -> StoredIntegrationConnection:
        private_data = private_data or {}
        merged = {**public_data, **private_data}
        return StoredIntegrationConnection(
            connection_id=connection_id,
            owner_id=uid,
            connector_type=str(merged.get("connectorType") or merged.get("type") or ""),
            provider=str(merged.get("provider") or ""),
            name=str(merged.get("name") or connection_id),
            enabled=bool(merged.get("enabled")),
            status=str(merged.get("status") or "needs_setup"),
            public=public_data,
            private=private_data,
            created_at=self._coerce_datetime(merged.get("createdAt")) or utcnow(),
            updated_at=self._coerce_datetime(merged.get("updatedAt")) or utcnow(),
            last_checked_at=self._coerce_datetime(merged.get("lastCheckedAt")),
            last_error=(
                str(merged.get("lastError"))
                if isinstance(merged.get("lastError"), str) and merged.get("lastError")
                else None
            ),
        )
