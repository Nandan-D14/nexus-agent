"""Pydantic models for API request / response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Responses ──────────────────────────────────────────────────

class HandoffSummary(BaseModel):
    headline: str = ""
    preview: str = ""
    goal: str = ""
    current_status: str = ""
    completed_work: list[str] = Field(default_factory=list)
    open_tasks: list[str] = Field(default_factory=list)
    important_facts: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    recommended_next_step: str = ""


class ContextPacket(BaseModel):
    summary: str = ""
    goal: str = ""
    open_tasks: list[str] = Field(default_factory=list)
    recent_turns: list[str] = Field(default_factory=list)
    latest_run_summary: str = ""
    artifact_refs: list[str] = Field(default_factory=list)
    digest: str = ""


class HealthResponse(BaseModel):
    status: str = "ok"
    active_sessions: int = 0
    checks: dict[str, Any] = Field(default_factory=dict)


class SessionResponse(BaseModel):
    session_id: str
    stream_url: Optional[str] = None
    ws_ticket: str
    status: str
    created_at: datetime
    handoff_summary: HandoffSummary | None = None
    resume_source_session_id: str | None = None
    current_run_id: str | None = None
    run_status: str | None = None
    artifact_count: int = 0
    can_continue_conversation: bool = True
    exact_workspace_resume_available: bool = False
    continuation_mode: str | None = None


class SessionInfo(BaseModel):
    session_id: str
    status: str
    is_live: bool = True
    stream_url: Optional[str] = None
    created_at: datetime
    ended_at: Optional[datetime] = None
    summary: Optional[str] = None
    message_count: int = 0
    handoff_summary: HandoffSummary | None = None
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
    context_packet: ContextPacket | None = None


class RunInfo(BaseModel):
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


class RunStep(BaseModel):
    step_id: str
    run_id: str
    session_id: str
    step_type: str
    status: str
    title: str = ""
    detail: str = ""
    created_at: datetime
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    step_index: int = 0
    source: str | None = None
    error: str | None = None
    external_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunArtifact(BaseModel):
    artifact_id: str
    run_id: str
    session_id: str
    kind: str
    title: str = ""
    preview: str = ""
    created_at: datetime
    source_step_id: str | None = None
    path: str | None = None
    url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: str
    detail: str = ""


class StatusMessage(BaseModel):
    status: str


class SessionCreateRequest(BaseModel):
    mode: Literal["fresh", "continue_latest_workspace", "reuse_history_session"] = "fresh"
    source_session_id: str | None = None


class HistoryReuseRequest(BaseModel):
    mode: Literal["continue", "fresh"] = "fresh"


# ── User Settings ────────────────────────────────────────────────

class ByokResponse(BaseModel):
    e2bKeySet: bool = False
    geminiKeySet: bool = False
    geminiProvider: Literal["apiKey", "vertex"] = "apiKey"
    missing: list[str] = Field(default_factory=list)
    configured: bool = False
    vertexConfigured: bool = False
    sharedAccessEnabled: bool = False
    sharedAccessCodeConfigured: bool = False
    serverE2bConfigured: bool = False


class UserSettingsResponse(BaseModel):
    requireByok: bool = False
    googleDriveConnected: bool = False
    settings: dict[str, Any] = Field(default_factory=dict)
    byok: ByokResponse = Field(default_factory=ByokResponse)


class ByokUpdateRequest(BaseModel):
    e2bApiKey: str | None = None
    geminiApiKey: str | None = None
    geminiProvider: Literal["apiKey", "vertex"] | None = None
    accessCode: str | None = None


class UserSettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    byok: ByokUpdateRequest | None = None
