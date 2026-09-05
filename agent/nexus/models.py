# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Pydantic models for API request / response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


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
    task_id: str | None = None
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


class SessionTokenTotals(BaseModel):
    input: int = 0
    output: int = 0
    total: int = 0


class SessionLastUsage(BaseModel):
    model: str = ""
    source: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class SessionInfo(BaseModel):
    session_id: str
    task_id: str | None = None
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
    token_totals: SessionTokenTotals | None = None
    model_context_limit: int | None = None
    last_usage: SessionLastUsage | None = None


class TaskInfo(BaseModel):
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


class RunInfo(BaseModel):
    run_id: str
    session_id: str
    task_id: str | None = None
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
    task_id: str | None = None
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
    task_id: str | None = None
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
    source_session_id: str | None = None
    source_run_id: str | None = None
    instructions: str
    input_fields: list[WorkflowTemplateInputField] = Field(default_factory=list)
    source_artifacts: list[str] = Field(default_factory=list)
    status: Literal["draft", "published"] = "published"
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
    status: Literal["draft", "published"] | None = None


class UpdateWorkflowTemplateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    instructions: str | None = None
    input_fields: list[WorkflowTemplateInputField] | None = None
    status: Literal["draft", "published"] | None = None


class RunWorkflowTemplateRequest(BaseModel):
    inputs: dict[str, str] = Field(default_factory=dict)


class WorkflowTemplateRunResponse(BaseModel):
    session: SessionResponse
    initial_prompt: str


# ── Integrations ──────────────────────────────────────────────────

class IntegrationToolInfo(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class IntegrationConnection(BaseModel):
    connection_id: str
    connector_type: str
    provider: str
    name: str
    enabled: bool = False
    status: str = "needs_setup"
    tools: list[IntegrationToolInfo] = Field(default_factory=list)
    resources: list[dict[str, Any]] = Field(default_factory=list)
    tool_count: int = 0
    last_checked_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class IntegrationCatalogItem(BaseModel):
    provider: str
    connector_type: str
    name: str
    description: str
    status: str = "available"
    auth_mode: str = "oauth"


class CreateMcpConnectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=8, max_length=500)
    bearer_token: str | None = Field(default=None, max_length=4000)
    enabled: bool = True


class UpdateIntegrationConnectionRequest(BaseModel):
    enabled: bool | None = None


class UpsertGithubConnectionRequest(BaseModel):
    token: str = Field(min_length=8, max_length=4000)
    enabled: bool = True


class UpsertSlackConnectionRequest(BaseModel):
    token: str = Field(min_length=8, max_length=4000)
    enabled: bool = True


class UpsertTavilyConnectionRequest(BaseModel):
    api_key: str = Field(min_length=8, max_length=4000)
    enabled: bool = True


class UpsertComposioConnectionRequest(BaseModel):
    consumer_api_key: str | None = Field(default=None, max_length=4000)
    enabled: bool = True


class UpsertTinyfishConnectionRequest(BaseModel):
    api_key: str = Field(min_length=8, max_length=4000)
    enabled: bool = True


class UpsertVyoraConnectionRequest(BaseModel):
    api_key: str = Field(min_length=8, max_length=4000)
    enabled: bool = True


class UpsertOpenAIConnectionRequest(BaseModel):
    api_key: str = Field(min_length=8, max_length=4000)
    enabled: bool = True


class UpsertThesysConnectionRequest(BaseModel):
    api_key: str = Field(min_length=8, max_length=4000)
    enabled: bool = True


class AgentSkillUpsertRequest(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    category: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=1024)
    trigger: str | None = Field(default=None, max_length=500)
    instructions: str | None = Field(default=None, max_length=16000)
    enabled: bool | None = None


class AgentSkillImportRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    skill_md: str | None = Field(
        default=None,
        max_length=200_000,
        validation_alias=AliasChoices("skill_md", "skill_md"),
    )
    source_url: str | None = Field(
        default=None,
        max_length=2000,
        validation_alias=AliasChoices("source_url", "source_url"),
    )
    files: dict[str, str] | None = None
    zip_b64: str | None = Field(
        default=None,
        max_length=2_800_000,
        validation_alias=AliasChoices("zip_b64", "package_zip_b64"),
    )
    enabled: bool = True


# ── User Settings ────────────────────────────────────────────────

class LlmProviderPublic(BaseModel):
    id: str = ""
    name: str = ""
    description: str = ""
    signupUrl: str = ""
    keyUrl: str = ""
    docsUrl: str = ""
    apiBase: str = ""
    defaultModel: str = ""
    defaultVisionModel: str = ""
    recommendedModels: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    notes: str = ""
    visionWarning: str = ""
    custom: bool = False
    logoUrl: str = ""
    logoInvertInDark: bool = False


class E2bSetupPublic(BaseModel):
    signupUrl: str = ""
    keyUrl: str = ""
    docsUrl: str = ""
    steps: list[str] = Field(default_factory=list)
    notes: str = ""
    logoUrl: str = ""
    logoInvertInDark: bool = False


class ByokResponse(BaseModel):
    e2bKeySet: bool = False
    geminiKeySet: bool = False
    geminiProvider: Literal["apiKey", "vertex"] = "apiKey"
    llmKeySet: bool = False
    llmProvider: str = ""
    llmModel: str = ""
    llmVisionModel: str = ""
    llmApiBase: str = ""
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
    llmProviders: list[LlmProviderPublic] = Field(default_factory=list)
    e2bSetup: E2bSetupPublic = Field(default_factory=E2bSetupPublic)


class ByokUpdateRequest(BaseModel):
    e2bApiKey: str | None = None
    geminiApiKey: str | None = None
    geminiProvider: Literal["apiKey", "vertex"] | None = None
    accessCode: str | None = None
    llmProvider: str | None = None
    llmApiKey: str | None = None
    llmModel: str | None = None
    llmVisionModel: str | None = None
    llmApiBase: str | None = None


class TestLlmRequest(BaseModel):
    llmProvider: str | None = None
    llmApiKey: str | None = None
    llmModel: str | None = None
    llmVisionModel: str | None = None
    llmApiBase: str | None = None


class LlmModelsResponse(BaseModel):
    models: list[str] = Field(default_factory=list)
    apiBase: str = ""


class UserSettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    byok: ByokUpdateRequest | None = None
