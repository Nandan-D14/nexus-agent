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
    version: int = 2
    built_at: str = ""
    summary: str = ""
    goal: str = ""
    open_tasks: list[str] = Field(default_factory=list)
    recent_turns: list[str] = Field(default_factory=list)
    latest_run_summary: str = ""
    artifact_refs: list[str] = Field(default_factory=list)
    tool_memory: list[str] = Field(default_factory=list)
    workspace_state: str = ""
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


class WorkflowTemplateInputField(BaseModel):
    key: str
    label: str
    placeholder: str = ""
    required: bool = False


class WorkflowTemplate(BaseModel):
    template_id: str
    owner_id: str
    name: str
    description: str = ""
    source_session_id: str
    source_run_id: str | None = None
    instructions: str
    input_fields: list[WorkflowTemplateInputField] = Field(default_factory=list)
    source_artifacts: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None


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


class CreateWorkflowTemplateRequest(BaseModel):
    source_session_id: str | None = None
    name: str | None = None
    description: str | None = None
    instructions: str | None = None
    input_fields: list[WorkflowTemplateInputField] = Field(default_factory=list)


class UpdateWorkflowTemplateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    instructions: str | None = None
    input_fields: list[WorkflowTemplateInputField] | None = None


class RunWorkflowTemplateRequest(BaseModel):
    inputs: dict[str, str] = Field(default_factory=dict)


class WorkflowTemplateRunResponse(BaseModel):
    session: SessionResponse
    initial_prompt: str


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


# ── Controlled Beta Access ───────────────────────────────────────

class BetaApplicationRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    role: str = Field(min_length=2, max_length=120)
    company_team: str = Field(min_length=2, max_length=120)
    primary_use_case: str = Field(min_length=10, max_length=500)
    current_workflow: str = Field(min_length=10, max_length=1_000)
    why_access: str = Field(min_length=10, max_length=1_000)
    expected_usage_frequency: str = Field(min_length=2, max_length=120)
    acknowledge_byok: bool = False


class RedeemBetaAccessCodeRequest(BaseModel):
    code: str = Field(min_length=4, max_length=64)


class BetaApplicationSummary(BaseModel):
    full_name: str = ""
    email: str = ""
    role: str = ""
    company_team: str = ""
    primary_use_case: str = ""
    current_workflow: str = ""
    why_access: str = ""
    expected_usage_frequency: str = ""
    acknowledge_byok: bool = False
    status: str = "none"
    sheet_sync_status: str | None = None


class BetaStatusResponse(BaseModel):
    state: Literal["none", "pending_review", "approved", "rejected", "revoked"] = "none"
    can_apply: bool = True
    can_access_app: bool = False
    needs_access_code: bool = False
    access_code_redeemed: bool = False
    requires_byok_setup: bool = False
    byok_missing: list[str] = Field(default_factory=list)
    message: str = ""
    application_submitted_at: datetime | None = None
    application_updated_at: datetime | None = None
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    revoked_at: datetime | None = None
    redeemed_at: datetime | None = None
    application: BetaApplicationSummary | None = None
