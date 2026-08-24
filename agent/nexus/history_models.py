# Proprietary and non-commercial use only.

"""Data models for Firestore-backed history persistence.

Extracted from ``history_repository`` so the repository classes and the
shared repo base can share these DTOs without a circular import.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class StoredSession:
    session_id: str
    owner_id: str
    task_id: str
    status: str
    created_at: datetime
    ended_at: datetime | None = None
    updated_at: datetime | None = None
    title: str = "Untitled session"
    summary: str | None = None
    message_count: int = 0
    token_totals: dict[str, Any] | None = None
    last_usage: dict[str, Any] | None = None
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
    context_packet_inputs_digest: str | None = None
    sandbox_id: str | None = None


@dataclass
class StoredRun:
    run_id: str
    session_id: str
    task_id: str
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
    task_id: str
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
    task_id: str
    kind: str
    title: str
    preview: str
    created_at: datetime
    source_step_id: str | None = None
    path: str | None = None
    url: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class StoredWorkflowTemplate:
    template_id: str
    owner_id: str
    name: str
    description: str
    source_session_id: str | None
    source_run_id: str | None
    instructions: str
    input_fields: list[dict[str, Any]]
    source_artifacts: list[str]
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None
    status: str = "published"


@dataclass
class StoredIntegrationConnection:
    connection_id: str
    owner_id: str
    connector_type: str
    provider: str
    name: str
    enabled: bool
    status: str
    public: dict[str, Any]
    private: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    last_checked_at: datetime | None = None
    last_error: str | None = None


@dataclass
class StoredTask:
    task_id: str
    owner_id: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime | None = None
    current_session_id: str | None = None
    current_run_id: str | None = None
    run_status: str | None = None
    message_count: int = 0
    step_count: int = 0
    artifact_count: int = 0
