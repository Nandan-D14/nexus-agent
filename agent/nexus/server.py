"""FastAPI application — REST + WebSocket endpoints for CoComputer."""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from nexus.auth import AuthenticatedUser, require_current_user
from nexus.beta_access import (
    append_beta_application_to_sheet,
    beta_access_enabled,
    beta_can_access_app,
    beta_can_apply,
    beta_needs_access_code,
    beta_status_message,
    build_beta_error_payload,
    build_sheet_sync_state,
    hash_beta_access_code,
    is_beta_admin,
    normalize_beta_profile,
)
from nexus.config import settings, apply_runtime_env_overrides, validate_startup_settings
from nexus.firebase import get_firestore_client
from nexus.history_repository import FirestoreHistoryRepository
from nexus.models import (
    BetaApplicationRequest,
    BetaApplicationSummary,
    BetaStatusResponse,
    ContextPacket,
    CreateWorkflowTemplateRequest,
    ErrorResponse,
    HealthResponse,
    HistoryReuseRequest,
    HandoffSummary,
    RunWorkflowTemplateRequest,
    RunArtifact,
    RunInfo,
    RunStep,
    SessionInfo,
    SessionCreateRequest,
    SessionResponse,
    StatusMessage,
    UserSettingsResponse,
    UserSettingsUpdateRequest,
    RedeemBetaAccessCodeRequest,
    WorkflowTemplate,
    WorkflowTemplateInputField,
    WorkflowTemplateRunResponse,
    UpdateWorkflowTemplateRequest,
)
from nexus.runtime_config import (
    build_byok_error_payload,
    build_byok_storage_update,
    build_public_user_settings,
    ensure_selected_gemini_provider_available,
    get_byok_status,
    resolve_session_runtime_config,
)
from nexus.session import SessionManager
from nexus.usage import get_expected_usage_sources
from nexus.ws_handler import handle_websocket

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

history_repository = FirestoreHistoryRepository()
session_manager = SessionManager(history_repository=history_repository)


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            recent = [ts for ts in self._hits[key] if now - ts < self.window_seconds]
            if len(recent) >= self.max_requests:
                self._hits[key] = recent
                return False
            recent.append(now)
            self._hits[key] = recent
            return True


session_create_limiter = RateLimiter(max_requests=5, window_seconds=60)
ticket_refresh_limiter = RateLimiter(max_requests=30, window_seconds=60)
ws_connect_limiter = RateLimiter(max_requests=30, window_seconds=60)


def _live_session_payloads(user_id: str) -> list[dict[str, Any]]:
    return [
        {
            "session_id": session.id,
            "owner_id": session.owner_id,
            "status": session.status,
            "created_at": session.created_at,
            "last_active_at": session.last_active,
            "stream_url": session.stream_url or None,
        }
        for session in session_manager.list_sessions_for_owner(user_id)
        if session.stream_url
    ]


def _serialize_handoff_summary(summary: dict[str, Any] | None) -> HandoffSummary | None:
    if not isinstance(summary, dict):
        return None
    return HandoffSummary.model_validate(summary)


def _serialize_context_packet(packet: dict[str, Any] | None) -> ContextPacket | None:
    if not isinstance(packet, dict):
        return None
    normalized = {
        "version": packet.get("version", 2),
        "built_at": packet.get("builtAt", ""),
        "summary": packet.get("summary", ""),
        "goal": packet.get("goal", ""),
        "open_tasks": packet.get("openTasks", []),
        "recent_turns": packet.get("recentTurns", []),
        "latest_run_summary": packet.get("latestRunSummary", ""),
        "artifact_refs": packet.get("artifactRefs", []),
        "tool_memory": packet.get("toolMemory", []),
        "workspace_state": packet.get("workspaceState", ""),
        "digest": packet.get("digest", ""),
    }
    return ContextPacket.model_validate(normalized)


def _build_resume_seed_context(stored_session) -> str:
    packet = stored_session.context_packet or {}
    digest = packet.get("digest") if isinstance(packet, dict) and isinstance(packet.get("digest"), str) else ""
    if not digest:
        return ""
    return (
        "[RESUME CONTEXT AVAILABLE]\n"
        f"Digest: {digest}\n"
        "Load the stored compact session context automatically instead of asking the user to restate prior work."
    )


def _build_session_info_from_stored(stored_session) -> SessionInfo:
    return SessionInfo(
        session_id=stored_session.session_id,
        status=stored_session.status,
        is_live=False,
        stream_url=None,
        created_at=stored_session.created_at,
        ended_at=stored_session.ended_at,
        summary=stored_session.summary,
        message_count=stored_session.message_count,
        handoff_summary=_serialize_handoff_summary(stored_session.handoff_summary),
        can_continue_workspace=stored_session.can_continue_workspace,
        has_artifacts=stored_session.has_artifacts,
        resume_state=stored_session.resume_state,
        workspace_owner_session_id=stored_session.workspace_owner_session_id,
        resume_source_session_id=stored_session.resume_source_session_id,
        current_run_id=stored_session.current_run_id,
        run_status=stored_session.run_status,
        artifact_count=stored_session.artifact_count,
        can_continue_conversation=stored_session.can_continue_conversation,
        exact_workspace_resume_available=stored_session.exact_workspace_resume_available,
        continuation_mode=stored_session.continuation_mode,
        context_packet=_serialize_context_packet(stored_session.context_packet),
    )


def _serialize_run(run) -> RunInfo | None:
    if run is None:
        return None
    return RunInfo(
        run_id=run.run_id,
        session_id=run.session_id,
        owner_id=run.owner_id,
        status=run.status,
        created_at=run.created_at,
        updated_at=run.updated_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        last_step_at=run.last_step_at,
        step_count=run.step_count,
        artifact_count=run.artifact_count,
        title=run.title,
        source_session_id=run.source_session_id,
    )


def _serialize_run_step(step) -> RunStep:
    return RunStep(
        step_id=step.step_id,
        run_id=step.run_id,
        session_id=step.session_id,
        step_type=step.step_type,
        status=step.status,
        title=step.title,
        detail=step.detail,
        created_at=step.created_at,
        updated_at=step.updated_at,
        completed_at=step.completed_at,
        step_index=step.step_index,
        source=step.source,
        error=step.error,
        external_ref=step.external_ref,
        metadata=step.metadata or {},
    )


def _serialize_artifact(artifact) -> RunArtifact:
    return RunArtifact(
        artifact_id=artifact.artifact_id,
        run_id=artifact.run_id,
        session_id=artifact.session_id,
        kind=artifact.kind,
        title=artifact.title,
        preview=artifact.preview,
        created_at=artifact.created_at,
        source_step_id=artifact.source_step_id,
        path=artifact.path,
        url=artifact.url,
        metadata=artifact.metadata or {},
    )


_TEMPLATE_KEY_RE = re.compile(r"[^a-z0-9_]+")


def _normalize_template_input_fields(
    fields: list[WorkflowTemplateInputField] | list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in fields or []:
        data = raw.model_dump() if isinstance(raw, WorkflowTemplateInputField) else raw
        if not isinstance(data, dict):
            continue
        base_key = data.get("key") if isinstance(data.get("key"), str) else ""
        candidate_key = _TEMPLATE_KEY_RE.sub("_", base_key.strip().lower()).strip("_")
        if not candidate_key:
            continue
        if candidate_key[0].isdigit():
            candidate_key = f"field_{candidate_key}"
        if candidate_key in seen:
            continue
        seen.add(candidate_key)
        label = data.get("label") if isinstance(data.get("label"), str) else ""
        placeholder = data.get("placeholder") if isinstance(data.get("placeholder"), str) else ""
        normalized.append(
            {
                "key": candidate_key[:40],
                "label": (label.strip() or candidate_key.replace("_", " ").title())[:80],
                "placeholder": placeholder.strip()[:120],
                "required": bool(data.get("required")),
            }
        )
    return normalized


def _serialize_workflow_template(template) -> WorkflowTemplate:
    return WorkflowTemplate(
        template_id=template.template_id,
        owner_id=template.owner_id,
        name=template.name,
        description=template.description,
        source_session_id=template.source_session_id,
        source_run_id=template.source_run_id,
        instructions=template.instructions,
        input_fields=[
            WorkflowTemplateInputField.model_validate(field)
            for field in template.input_fields
        ],
        source_artifacts=template.source_artifacts,
        created_at=template.created_at,
        updated_at=template.updated_at,
        last_used_at=template.last_used_at,
    )


def _build_template_defaults(stored_session, run, steps, artifacts) -> dict[str, Any]:
    handoff = stored_session.handoff_summary or {}
    packet = stored_session.context_packet or {}

    summary = ""
    for candidate in (
        handoff.get("preview"),
        stored_session.summary,
        packet.get("summary"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            summary = candidate.strip()
            break

    goal = ""
    for candidate in (
        handoff.get("goal"),
        packet.get("goal"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            goal = candidate.strip()
            break

    latest_steps: list[str] = []
    for step in reversed(steps or []):
        if step.status != "completed":
            continue
        detail = (step.detail or step.title or "").strip()
        if detail and detail not in latest_steps:
            latest_steps.append(detail)
        if len(latest_steps) >= 3:
            break

    open_tasks = [
        str(item).strip()
        for item in (handoff.get("open_tasks") or packet.get("openTasks") or [])
        if str(item).strip()
    ][:3]
    source_artifacts = []
    for artifact in artifacts or []:
        candidate = (artifact.title or artifact.preview or artifact.kind or "").strip()
        if candidate and candidate not in source_artifacts:
            source_artifacts.append(candidate)
        if len(source_artifacts) >= 4:
            break

    if not (run or summary or goal or latest_steps or source_artifacts):
        raise HTTPException(
            status_code=400,
            detail="This session does not have enough saved context to become a template yet.",
        )

    name = (stored_session.title or "").strip() or handoff.get("headline") or "Workflow template"
    description = summary or goal or "Reusable workflow saved from a prior CoComputer session."

    instruction_lines = [
        "Use this saved CoComputer workflow as the execution pattern for the new task.",
    ]
    if goal:
        instruction_lines.append(f"Original goal: {goal}")
    if summary:
        instruction_lines.append(f"Saved summary: {summary}")
    if latest_steps:
        instruction_lines.append("Successful workflow steps to preserve:")
        instruction_lines.extend(f"- {item}" for item in latest_steps)
    if open_tasks:
        instruction_lines.append("Open tasks or follow-ups to consider:")
        instruction_lines.extend(f"- {item}" for item in open_tasks)
    if source_artifacts:
        instruction_lines.append("Reference artifacts from the source session:")
        instruction_lines.extend(f"- {item}" for item in source_artifacts)
    instruction_lines.append(
        "When this template is run, use the provided template input values and execute the workflow without asking the user to restate the saved context."
    )

    return {
        "name": name[:80],
        "description": description[:240],
        "instructions": "\n".join(instruction_lines).strip(),
        "source_artifacts": source_artifacts,
    }


async def _prepare_template_source(owner_id: str, session_id: str):
    stored_session = await history_repository.get_session(session_id)
    if not stored_session or stored_session.owner_id != owner_id or stored_session.status == "deleted":
        raise HTTPException(status_code=404, detail="Session not found")
    if not stored_session.handoff_summary or not stored_session.context_packet:
        await history_repository.refresh_session_handoff(session_id, owner_id=owner_id)
        stored_session = await history_repository.get_session(session_id)
        if not stored_session:
            raise HTTPException(status_code=404, detail="Session not found")
    run = await history_repository.get_session_run(session_id)
    steps = await history_repository.list_run_steps(session_id, run.run_id) if run else []
    artifacts = await history_repository.list_run_artifacts(session_id, run.run_id) if run else []
    return stored_session, run, steps, artifacts


def _build_template_prompt(template, inputs: dict[str, str]) -> str:
    normalized_inputs = {
        key.strip(): value.strip()
        for key, value in (inputs or {}).items()
        if isinstance(key, str) and key.strip() and isinstance(value, str) and value.strip()
    }
    field_lookup = {field["key"]: field for field in template.input_fields}
    missing_required = [
        field["label"]
        for field in template.input_fields
        if field.get("required") and not normalized_inputs.get(field["key"])
    ]
    if missing_required:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required template inputs: {', '.join(missing_required)}",
        )

    lines = [template.instructions.strip()]
    if normalized_inputs:
        lines.append("")
        lines.append("Template inputs:")
        for field in template.input_fields:
            value = normalized_inputs.get(field["key"])
            if value:
                lines.append(f"- {field['label']}: {value}")
        for key in sorted(normalized_inputs):
            if key in field_lookup:
                continue
            lines.append(f"- {key}: {normalized_inputs[key]}")
    lines.append("")
    lines.append("Execute this workflow now using the saved process and the provided template inputs.")
    return "\n".join(part for part in lines if part is not None).strip()


async def _resolve_source_session(
    owner_id: str,
    source_session_id: str | None,
):
    if not source_session_id:
        return None, "", "New session"

    stored_session = await history_repository.get_session(source_session_id)
    if not stored_session or stored_session.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="Source session not found")

    if not stored_session.handoff_summary:
        await history_repository.refresh_session_handoff(source_session_id, owner_id=owner_id)
        stored_session = await history_repository.get_session(source_session_id)

    initial_title = (
        f"Continue: {stored_session.title}"
        if stored_session and stored_session.title
        else "Continued session"
    )
    seed_context = _build_resume_seed_context(stored_session) if stored_session else ""
    return stored_session, seed_context, initial_title


def _build_session_response(
    *,
    session,
    ticket: str,
    stored_session=None,
) -> SessionResponse:
    stored_handoff = stored_session.handoff_summary if stored_session else None
    exact_workspace_resume_available = bool(getattr(session, "exact_workspace_resume_available", False))
    continuation_mode = (
        getattr(session, "continuation_mode", None)
        or getattr(stored_session, "continuation_mode", None)
    )
    return SessionResponse(
        session_id=session.id,
        stream_url=session.stream_url or None,
        ws_ticket=ticket,
        status=session.status,
        created_at=session.created_at,
        handoff_summary=_serialize_handoff_summary(stored_handoff),
        resume_source_session_id=session.resume_source_session_id,
        current_run_id=session.current_run_id,
        run_status=session.run_status,
        artifact_count=session.artifact_count,
        can_continue_conversation=True,
        exact_workspace_resume_available=exact_workspace_resume_available,
        continuation_mode=continuation_mode,
    )


def _serialize_beta_application(application: dict[str, Any] | None) -> BetaApplicationSummary | None:
    if not isinstance(application, dict):
        return None
    return BetaApplicationSummary(
        full_name=str(application.get("fullName", "")),
        email=str(application.get("email", "")),
        role=str(application.get("role", "")),
        company_team=str(application.get("companyTeam", "")),
        primary_use_case=str(application.get("primaryUseCase", "")),
        current_workflow=str(application.get("currentWorkflow", "")),
        why_access=str(application.get("whyAccess", "")),
        expected_usage_frequency=str(application.get("expectedUsageFrequency", "")),
        acknowledge_byok=bool(application.get("acknowledgeByok")),
        status=str(application.get("status", "none")),
        sheet_sync_status=(
            str(application.get("sheetSync", {}).get("status"))
            if isinstance(application.get("sheetSync"), dict) and application.get("sheetSync", {}).get("status")
            else None
        ),
    )


def _build_beta_status_response(
    *,
    user_settings: dict[str, Any] | None,
    application: dict[str, Any] | None = None,
) -> BetaStatusResponse:
    # Future use: when controlled beta access is disabled we keep this endpoint
    # alive so older frontend code can still bootstrap, but everyone is allowed
    # through and only BYOK remains enforced.
    if not beta_access_enabled():
        byok_status = get_byok_status(user_settings)
        requires_byok_setup = bool((settings.require_byok or settings.beta_enforce_byok) and not byok_status.configured)
        return BetaStatusResponse(
            state="none",
            can_apply=False,
            can_access_app=True,
            needs_access_code=False,
            access_code_redeemed=False,
            requires_byok_setup=requires_byok_setup,
            byok_missing=list(byok_status.missing) if requires_byok_setup else [],
            message="Controlled beta access is disabled for now. This endpoint remains for future gated rollout.",
            application=None,
        )

    profile = normalize_beta_profile(user_settings)
    can_access_app = beta_can_access_app(profile)
    byok_status = get_byok_status(user_settings)
    requires_byok_setup = bool((settings.require_byok or settings.beta_enforce_byok) and can_access_app and not byok_status.configured)
    return BetaStatusResponse(
        state=profile["status"],
        can_apply=beta_can_apply(profile),
        can_access_app=can_access_app,
        needs_access_code=beta_needs_access_code(profile),
        access_code_redeemed=bool(profile.get("accessCodeRedeemed")),
        requires_byok_setup=requires_byok_setup,
        byok_missing=list(byok_status.missing) if requires_byok_setup else [],
        message=beta_status_message(profile),
        application_submitted_at=profile.get("applicationSubmittedAt"),
        application_updated_at=profile.get("applicationUpdatedAt"),
        approved_at=profile.get("approvedAt"),
        rejected_at=profile.get("rejectedAt"),
        revoked_at=profile.get("revokedAt"),
        redeemed_at=profile.get("redeemedAt"),
        application=_serialize_beta_application(application),
    )


def _ensure_beta_access(user_settings: dict[str, Any] | None) -> None:
    # Future use: the access-code gate can be re-enabled with
    # BETA_ACCESS_ENABLED=true without removing the beta code paths.
    if not beta_access_enabled():
        return
    profile = normalize_beta_profile(user_settings)
    if beta_can_access_app(profile):
        return
    raise HTTPException(status_code=403, detail=build_beta_error_payload(profile))


async def _prepare_user_runtime(user: AuthenticatedUser) -> dict[str, Any]:
    await history_repository.upsert_user(user)
    user_settings = await history_repository.get_user_settings(user.uid)
    _ensure_beta_access(user_settings)
    try:
        ensure_selected_gemini_provider_available(user_settings)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    if settings.require_byok or settings.beta_enforce_byok:
        byok_status = get_byok_status(user_settings)
        if not byok_status.configured:
            raise HTTPException(
                status_code=403,
                detail=build_byok_error_payload(user_settings),
            )

    quota = await history_repository.get_user_quota(user.uid)
    if quota["remaining"] <= 0:
        raise HTTPException(
            status_code=403,
            detail=(
                f"{quota.get('plan_name', settings.default_plan_name)} balance exhausted. "
                f"You've used {quota['used']:,} of {quota['limit']:,} credits."
            ),
        )
    return user_settings


async def _continue_existing_session_for_user(
    user: AuthenticatedUser,
    *,
    session_id: str,
) -> SessionResponse:
    user_settings = await _prepare_user_runtime(user)

    live_session = session_manager.get_session(session_id)
    if live_session:
        if live_session.owner_id != user.uid:
            raise HTTPException(status_code=404, detail="Session not found")
        stored_session = await history_repository.get_session(session_id)
        ticket = session_manager.create_ticket(session_id, user.uid)
        return _build_session_response(
            session=live_session,
            ticket=ticket,
            stored_session=stored_session,
        )

    stored_session = await history_repository.get_session(session_id)
    if not stored_session or stored_session.owner_id != user.uid or stored_session.status == "deleted":
        raise HTTPException(status_code=404, detail="Session not found")

    if not stored_session.handoff_summary or not stored_session.context_packet:
        await history_repository.refresh_session_handoff(session_id, owner_id=user.uid)
        stored_session = await history_repository.get_session(session_id)
        if not stored_session:
            raise HTTPException(status_code=404, detail="Session not found")

    workspace_state = await history_repository.get_workspace_state(user.uid)
    exact_workspace_resume_available = (
        workspace_state.get("session_id") == session_id
        and bool(workspace_state.get("sandbox_id"))
    )
    continuation_mode = (
        "exact_workspace_resume"
        if exact_workspace_resume_available
        else "new_sandbox_resume"
    )

    try:
        session = await session_manager.continue_session(
            session_id=session_id,
            owner_id=user.uid,
            runtime_config=resolve_session_runtime_config(user_settings),
            created_at=stored_session.created_at,
            resume_mode="continue_latest_workspace" if exact_workspace_resume_available else "fresh",
            seed_context="",
            initial_title=stored_session.title or "Continued session",
            artifact_count=stored_session.artifact_count,
            exact_workspace_resume_available=exact_workspace_resume_available,
            continuation_mode=continuation_mode,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except PermissionError:
        raise HTTPException(status_code=404, detail="Session not found")

    refreshed_session = await history_repository.get_session(session_id)
    ticket = session_manager.create_ticket(session_id, user.uid)
    return _build_session_response(
        session=session,
        ticket=ticket,
        stored_session=refreshed_session,
    )


async def _create_session_for_user(
    user: AuthenticatedUser,
    payload: SessionCreateRequest,
) -> SessionResponse:
    user_settings = await _prepare_user_runtime(user)

    mode = payload.mode
    resume_mode = "fresh"
    resume_source_session_id = payload.source_session_id
    seed_context = ""
    initial_title = "New session"

    if mode == "continue_latest_workspace":
        workspace_state = await history_repository.get_workspace_state(user.uid)
        paused_sandbox_id = workspace_state.get("sandbox_id")
        paused_session_id = workspace_state.get("session_id")
        if not paused_sandbox_id or not paused_session_id:
            raise HTTPException(status_code=409, detail="No paused workspace is available to resume")
        if payload.source_session_id and payload.source_session_id != paused_session_id:
            raise HTTPException(status_code=409, detail="Only the latest paused workspace can be continued")
        return await _continue_existing_session_for_user(user, session_id=paused_session_id)
    elif mode == "reuse_history_session":
        if not payload.source_session_id:
            raise HTTPException(status_code=400, detail="source_session_id is required for reuse_history_session")
        return await _continue_existing_session_for_user(user, session_id=payload.source_session_id)

    try:
        session = await session_manager.create_session(
            owner_id=user.uid,
            runtime_config=resolve_session_runtime_config(user_settings),
            resume_mode=resume_mode,
            resume_source_session_id=resume_source_session_id,
            seed_context=seed_context,
            initial_title=initial_title,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    stored_session = await history_repository.get_session(session.id)
    ticket = session_manager.create_ticket(session.id, user.uid)
    return _build_session_response(
        session=session,
        ticket=ticket,
        stored_session=stored_session,
    )


async def _create_template_from_session_for_user(
    *,
    user: AuthenticatedUser,
    source_session_id: str,
    payload: CreateWorkflowTemplateRequest,
) -> WorkflowTemplate:
    stored_session, run, steps, artifacts = await _prepare_template_source(user.uid, source_session_id)
    defaults = _build_template_defaults(stored_session, run, steps, artifacts)
    normalized_input_fields = _normalize_template_input_fields(payload.input_fields)
    template = await history_repository.create_workflow_template(
        owner_id=user.uid,
        source_session_id=source_session_id,
        source_run_id=run.run_id if run else None,
        name=(payload.name or defaults["name"]).strip()[:80],
        description=(payload.description or defaults["description"]).strip()[:240],
        instructions=(payload.instructions or defaults["instructions"]).strip(),
        input_fields=normalized_input_fields,
        source_artifacts=defaults["source_artifacts"],
    )
    return _serialize_workflow_template(template)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    apply_runtime_env_overrides()
    validate_startup_settings()
    logger.info("CoComputer agent service starting...")
    session_manager.start_cleanup()
    yield
    logger.info("CoComputer agent service shutting down...")
    session_manager.stop_cleanup()
    await session_manager.destroy_all()


app = FastAPI(
    title="CoComputer Agent Service",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ── REST Endpoints ──────────────────────────────────────────────


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(active_sessions=session_manager.active_count)


@app.get("/healthz")
async def deep_health():
    checks: dict[str, Any] = {
        "sessions": session_manager.active_count,
        "e2b_configured": bool(settings.e2b_api_key) or settings.require_byok,
    }
    http_status = 200

    try:
        db = get_firestore_client()
        list(db.collection("_health").limit(1).stream())
        checks["firestore"] = "ok"
    except Exception as exc:
        checks["firestore"] = f"error:{type(exc).__name__}"
        http_status = 503

    try:
        validate_startup_settings()
        checks["config"] = "ok"
    except Exception as exc:
        checks["config"] = str(exc)
        http_status = 503

    return JSONResponse(
        status_code=http_status,
        content=HealthResponse(
            status="ok" if http_status == 200 else "degraded",
            active_sessions=session_manager.active_count,
            checks=checks,
        ).model_dump(mode="json"),
    )


@app.get("/api/v1/beta/status", response_model=BetaStatusResponse)
async def get_beta_status(user: AuthenticatedUser = Depends(require_current_user)):
    await history_repository.upsert_user(user)
    user_settings = await history_repository.get_user_settings(user.uid)
    application = await history_repository.get_beta_application(user.uid)
    return _build_beta_status_response(user_settings=user_settings, application=application)


@app.post("/api/v1/beta/apply", response_model=BetaStatusResponse)
async def apply_for_beta(
    payload: BetaApplicationRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    if not beta_access_enabled():
        await history_repository.upsert_user(user)
        user_settings = await history_repository.get_user_settings(user.uid)
        return _build_beta_status_response(user_settings=user_settings, application=None)

    if not payload.acknowledge_byok:
        raise HTTPException(status_code=400, detail="You must acknowledge the BYOK requirement before applying.")

    await history_repository.upsert_user(user)
    user_settings = await history_repository.get_user_settings(user.uid)
    profile = normalize_beta_profile(user_settings)

    if profile["status"] == "revoked":
        raise HTTPException(status_code=403, detail=build_beta_error_payload(profile))
    if profile["status"] == "pending_review":
        raise HTTPException(status_code=409, detail="Your beta application is already pending review.")
    if profile["status"] == "approved":
        raise HTTPException(
            status_code=409,
            detail="Your beta application is already approved. Redeem the access code or continue setup.",
        )

    now = datetime.now(timezone.utc)
    beta_application = {
        "userId": user.uid,
        "email": user.email or "",
        "fullName": payload.full_name.strip(),
        "role": payload.role.strip(),
        "companyTeam": payload.company_team.strip(),
        "primaryUseCase": payload.primary_use_case.strip(),
        "currentWorkflow": payload.current_workflow.strip(),
        "whyAccess": payload.why_access.strip(),
        "expectedUsageFrequency": payload.expected_usage_frequency.strip(),
        "acknowledgeByok": True,
        "status": "pending_review",
        "submittedAt": now,
        "updatedAt": now,
        "sheetSyncStatus": "pending",
        "sheetSync": build_sheet_sync_state("pending"),
    }
    await history_repository.upsert_beta_application(user.uid, beta_application)
    await history_repository.set_beta_profile(
        user.uid,
        {
            **profile,
            "status": "pending_review",
            "applicationId": user.uid,
            "applicationSubmittedAt": now,
            "applicationUpdatedAt": now,
            "approvedAt": None,
            "rejectedAt": None,
            "revokedAt": None,
            "redeemedAt": None,
            "accessCodeRedeemed": False,
            "accessCodeId": None,
            "accessCodePreview": None,
            "lastDecisionBy": None,
            "rejectionReason": None,
            "revokedReason": None,
        },
    )

    try:
        append_beta_application_to_sheet(beta_application)
        await history_repository.upsert_beta_application(
            user.uid,
            {
                "sheetSyncStatus": "synced",
                "sheetSync": build_sheet_sync_state("synced"),
            },
        )
    except Exception as exc:
        logger.warning("Beta application Sheets sync failed for %s: %s", user.uid, exc)
        await history_repository.upsert_beta_application(
            user.uid,
            {
                "sheetSyncStatus": "error",
                "sheetSync": build_sheet_sync_state("error", str(exc)),
            },
        )

    updated_user_settings = await history_repository.get_user_settings(user.uid)
    application = await history_repository.get_beta_application(user.uid)
    return _build_beta_status_response(user_settings=updated_user_settings, application=application)


@app.post("/api/v1/beta/redeem-code", response_model=BetaStatusResponse)
async def redeem_beta_access_code(
    payload: RedeemBetaAccessCodeRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    if not beta_access_enabled():
        await history_repository.upsert_user(user)
        user_settings = await history_repository.get_user_settings(user.uid)
        return _build_beta_status_response(user_settings=user_settings, application=None)

    await history_repository.upsert_user(user)
    user_settings = await history_repository.get_user_settings(user.uid)
    profile = normalize_beta_profile(user_settings)

    if profile["status"] != "approved":
        raise HTTPException(status_code=403, detail=build_beta_error_payload(profile))
    if profile.get("accessCodeRedeemed"):
        application = await history_repository.get_beta_application(user.uid)
        return _build_beta_status_response(user_settings=user_settings, application=application)

    try:
        await history_repository.redeem_beta_access_code(user.uid, hash_beta_access_code(payload.code))
    except KeyError:
        raise HTTPException(
            status_code=403,
            detail={"code": "BETA_ACCESS_CODE_INVALID", "detail": "Invalid beta access code."},
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail={"code": "BETA_ACCESS_CODE_INVALID", "detail": str(exc)},
        )

    updated_user_settings = await history_repository.get_user_settings(user.uid)
    application = await history_repository.get_beta_application(user.uid)
    return _build_beta_status_response(user_settings=updated_user_settings, application=application)


@app.post("/sessions", response_model=SessionResponse)
async def create_session(
    payload: SessionCreateRequest | None = Body(default=None),
    user: AuthenticatedUser = Depends(require_current_user),
):
    """Create a new CoComputer session using an explicit workspace mode."""
    if not session_create_limiter.is_allowed(user.uid):
        raise HTTPException(status_code=429, detail="Too many session requests. Please wait and try again.")
    return await _create_session_for_user(user, payload or SessionCreateRequest())


@app.get("/api/v1/workspace/resume")
async def get_resume_workspace(user: AuthenticatedUser = Depends(require_current_user)):
    workspace_state = await history_repository.get_workspace_state(user.uid)
    session_id = workspace_state.get("session_id")
    stored_session = await history_repository.get_session(session_id) if session_id else None
    return {
        "available": bool(workspace_state.get("sandbox_id") and stored_session),
        "session": _build_session_info_from_stored(stored_session).model_dump(mode="json") if stored_session else None,
    }


@app.post("/api/v1/history/{session_id}/reuse", response_model=SessionResponse)
async def reuse_history_session(
    session_id: str,
    body: HistoryReuseRequest | None = Body(default=None),
    user: AuthenticatedUser = Depends(require_current_user),
):
    if not session_create_limiter.is_allowed(user.uid):
        raise HTTPException(status_code=429, detail="Too many session requests. Please wait and try again.")
    stored_session = await history_repository.get_session(session_id)
    if not stored_session or stored_session.owner_id != user.uid or stored_session.status == "deleted":
        raise HTTPException(status_code=404, detail="Session not found")
    return await _continue_existing_session_for_user(user, session_id=session_id)


@app.post("/sessions/{session_id}/continue", response_model=SessionResponse)
async def continue_session(
    session_id: str,
    user: AuthenticatedUser = Depends(require_current_user),
):
    if not session_create_limiter.is_allowed(user.uid):
        raise HTTPException(status_code=429, detail="Too many session requests. Please wait and try again.")
    return await _continue_existing_session_for_user(user, session_id=session_id)


@app.get("/sessions/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str, user: AuthenticatedUser = Depends(require_current_user)):
    session = session_manager.get_session(session_id)
    stored_session = await history_repository.get_session(session_id)
    if session:
        if session.owner_id != user.uid:
            raise HTTPException(status_code=404, detail="Session not found")
        return SessionInfo(
            session_id=session.id,
            status=session.status,
            is_live=True,
            stream_url=session.stream_url or None,
            created_at=session.created_at,
            ended_at=stored_session.ended_at if stored_session else None,
            summary=stored_session.summary if stored_session else None,
            message_count=stored_session.message_count if stored_session else 0,
            handoff_summary=_serialize_handoff_summary(stored_session.handoff_summary if stored_session else None),
            can_continue_workspace=stored_session.can_continue_workspace if stored_session else False,
            has_artifacts=stored_session.has_artifacts if stored_session else bool(session.artifact_count),
            resume_state=stored_session.resume_state if stored_session else None,
            workspace_owner_session_id=stored_session.workspace_owner_session_id if stored_session else None,
            resume_source_session_id=session.resume_source_session_id,
            current_run_id=session.current_run_id,
            run_status=session.run_status,
            artifact_count=session.artifact_count,
            can_continue_conversation=True,
            exact_workspace_resume_available=session.exact_workspace_resume_available,
            continuation_mode=session.continuation_mode or (stored_session.continuation_mode if stored_session else None),
            context_packet=_serialize_context_packet(stored_session.context_packet if stored_session else None),
        )

    if not stored_session or stored_session.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Session not found")

    return _build_session_info_from_stored(stored_session)


@app.delete("/sessions/{session_id}", response_model=StatusMessage)
async def delete_session(session_id: str, user: AuthenticatedUser = Depends(require_current_user)):
    try:
        await session_manager.destroy_if_owned(session_id, user.uid, status="ended")
    except KeyError:
        stored_session = await history_repository.get_session(session_id)
        if not stored_session or stored_session.owner_id != user.uid:
            raise HTTPException(status_code=404, detail="Session not found")
        history_repository._db.collection("sessions").document(session_id).set(
            {"status": "deleted", "updatedAt": datetime.now(timezone.utc)},
            merge=True,
        )
    except PermissionError:
        raise HTTPException(status_code=404, detail="Session not found")
    return StatusMessage(status="destroyed")


@app.post("/sessions/{session_id}/ticket")
async def refresh_ticket(session_id: str, user: AuthenticatedUser = Depends(require_current_user)):
    """Generate a new WS authentication ticket for an existing session."""
    if not ticket_refresh_limiter.is_allowed(user.uid):
        raise HTTPException(status_code=429, detail="Too many ticket refresh requests. Please slow down.")
    user_settings = await history_repository.get_user_settings(user.uid)
    _ensure_beta_access(user_settings)
    session = session_manager.get_session(session_id)
    if not session or session.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Session not found")
    ticket = session_manager.create_ticket(session_id, user.uid)
    return {"ws_ticket": ticket}


@app.get("/api/v1/dashboard/stats")
async def get_dashboard_stats(user: AuthenticatedUser = Depends(require_current_user)):
    stats = await history_repository.get_dashboard_stats(user.uid)
    tracked_sources = set(stats.get("tracked_sources", []))
    configured_sources = set(get_expected_usage_sources())
    stats["tracked_sources"] = sorted(tracked_sources)
    stats["untracked_sources"] = sorted(configured_sources - tracked_sources)
    return stats


@app.get("/api/v1/dashboard/usage")
async def get_dashboard_usage(
    days: int = Query(30, ge=1, le=90),
    user: AuthenticatedUser = Depends(require_current_user)
):
    chart = await history_repository.get_dashboard_usage(user.uid, days)
    return {"chart": chart}


@app.get("/api/v1/dashboard/sessions")
async def get_dashboard_sessions(
    limit: int = Query(10, ge=1, le=50),
    user: AuthenticatedUser = Depends(require_current_user),
):
    sessions = await history_repository.list_recent_session_usage(user.uid, limit)
    return {"sessions": sessions}


@app.get("/api/v1/sessions/active")
async def get_active_sessions(user: AuthenticatedUser = Depends(require_current_user)):
    sessions = await history_repository.list_active_sessions(
        user.uid,
        _live_session_payloads(user.uid),
    )
    return {"sessions": sessions}


@app.get("/api/v1/history")
async def list_history(
    limit: int = Query(25, ge=1, le=100),
    status: str | None = Query(None),
    q: str | None = Query(None),
    user: AuthenticatedUser = Depends(require_current_user)
):
    sessions = await history_repository.list_sessions(user.uid, limit, status, q)
    return {
        "sessions": [
            {
                "session_id": s.session_id,
                "title": getattr(s, "title", "Session") + (" - " + getattr(s, "summary", "")[:50] if getattr(s, "summary", "") else ""),
                "status": s.status,
                "created_at": s.created_at,
                "ended_at": s.ended_at,
                "message_count": s.message_count,
                "summary": s.summary,
                "handoff_summary": s.handoff_summary,
                "can_continue_workspace": s.can_continue_workspace,
                "has_artifacts": s.has_artifacts,
                "resume_state": s.resume_state,
                "workspace_owner_session_id": s.workspace_owner_session_id,
                "current_run_id": s.current_run_id,
                "run_status": s.run_status,
                "artifact_count": s.artifact_count,
                "can_continue_conversation": s.can_continue_conversation,
                "exact_workspace_resume_available": s.exact_workspace_resume_available,
                "continuation_mode": s.continuation_mode,
            }
            for s in sessions
        ]
    }


@app.get("/api/v1/sessions/{session_id}/run")
async def get_session_run(session_id: str, user: AuthenticatedUser = Depends(require_current_user)):
    session = session_manager.get_session(session_id)
    if session and session.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Session not found")

    stored_session = await history_repository.get_session(session_id)
    if not session and (not stored_session or stored_session.owner_id != user.uid):
        raise HTTPException(status_code=404, detail="Session not found")
    if session and not stored_session:
        stored_session = await history_repository.get_session(session_id)

    run = await history_repository.get_session_run(session_id)
    return {"run": _serialize_run(run).model_dump(mode="json") if run else None}


@app.get("/api/v1/sessions/{session_id}/artifacts")
async def get_session_artifacts(session_id: str, user: AuthenticatedUser = Depends(require_current_user)):
    session = session_manager.get_session(session_id)
    if session and session.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Session not found")

    stored_session = await history_repository.get_session(session_id)
    if not session and (not stored_session or stored_session.owner_id != user.uid):
        raise HTTPException(status_code=404, detail="Session not found")

    run = await history_repository.get_session_run(session_id)
    if not run:
        return {"artifacts": []}

    artifacts = await history_repository.list_run_artifacts(session_id, run.run_id)
    return {
        "artifacts": [
            _serialize_artifact(artifact).model_dump(mode="json")
            for artifact in artifacts
        ]
    }


@app.get("/api/v1/sessions/{session_id}/run/steps")
async def get_session_run_steps(session_id: str, user: AuthenticatedUser = Depends(require_current_user)):
    session = session_manager.get_session(session_id)
    if session and session.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Session not found")

    stored_session = await history_repository.get_session(session_id)
    if not session and (not stored_session or stored_session.owner_id != user.uid):
        raise HTTPException(status_code=404, detail="Session not found")

    run = await history_repository.get_session_run(session_id)
    if not run:
        return {"steps": []}

    steps = await history_repository.list_run_steps(session_id, run.run_id)
    return {
        "steps": [
            _serialize_run_step(step).model_dump(mode="json")
            for step in steps
        ]
    }

@app.get("/api/v1/history/{session_id}/messages")
async def get_history_messages(session_id: str, user: AuthenticatedUser = Depends(require_current_user)):
    # Verify owner
    session = await history_repository.get_session(session_id)
    if not session or session.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Session not found")
        
    messages = await history_repository.get_session_messages(session_id)
    return {"messages": messages}


@app.get("/api/v1/templates")
async def list_workflow_templates(
    limit: int = Query(100, ge=1, le=200),
    q: str | None = Query(None),
    user: AuthenticatedUser = Depends(require_current_user),
):
    templates = await history_repository.list_workflow_templates(
        user.uid,
        limit=limit,
        search=q,
    )
    return {
        "templates": [
            _serialize_workflow_template(template).model_dump(mode="json")
            for template in templates
        ]
    }


@app.post("/api/v1/templates", response_model=WorkflowTemplate)
async def create_workflow_template(
    payload: CreateWorkflowTemplateRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    if not payload.source_session_id:
        raise HTTPException(status_code=400, detail="source_session_id is required")
    return await _create_template_from_session_for_user(
        user=user,
        source_session_id=payload.source_session_id,
        payload=payload,
    )


@app.get("/api/v1/templates/{template_id}", response_model=WorkflowTemplate)
async def get_workflow_template(
    template_id: str,
    user: AuthenticatedUser = Depends(require_current_user),
):
    template = await history_repository.get_workflow_template(user.uid, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return _serialize_workflow_template(template)


@app.patch("/api/v1/templates/{template_id}", response_model=WorkflowTemplate)
async def update_workflow_template(
    template_id: str,
    payload: UpdateWorkflowTemplateRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    name = payload.name.strip()[:80] if isinstance(payload.name, str) else None
    description = payload.description.strip()[:240] if isinstance(payload.description, str) else None
    instructions = payload.instructions.strip() if isinstance(payload.instructions, str) else None
    if payload.name is not None and not name:
        raise HTTPException(status_code=400, detail="Template name cannot be empty")
    if payload.instructions is not None and not instructions:
        raise HTTPException(status_code=400, detail="Template instructions cannot be empty")
    normalized_input_fields = (
        _normalize_template_input_fields(payload.input_fields)
        if payload.input_fields is not None
        else None
    )
    template = await history_repository.update_workflow_template(
        owner_id=user.uid,
        template_id=template_id,
        name=name,
        description=description,
        instructions=instructions,
        input_fields=normalized_input_fields,
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return _serialize_workflow_template(template)


@app.delete("/api/v1/templates/{template_id}", response_model=StatusMessage)
async def delete_workflow_template(
    template_id: str,
    user: AuthenticatedUser = Depends(require_current_user),
):
    deleted = await history_repository.delete_workflow_template(user.uid, template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")
    return StatusMessage(status="deleted")


@app.post("/api/v1/templates/{template_id}/run", response_model=WorkflowTemplateRunResponse)
async def run_workflow_template(
    template_id: str,
    payload: RunWorkflowTemplateRequest | None = Body(default=None),
    user: AuthenticatedUser = Depends(require_current_user),
):
    if not session_create_limiter.is_allowed(user.uid):
        raise HTTPException(status_code=429, detail="Too many session requests. Please wait and try again.")
    template = await history_repository.get_workflow_template(user.uid, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    initial_prompt = _build_template_prompt(template, (payload or RunWorkflowTemplateRequest()).inputs)
    user_settings = await _prepare_user_runtime(user)
    try:
        session = await session_manager.create_session(
            owner_id=user.uid,
            runtime_config=resolve_session_runtime_config(user_settings),
            initial_title=template.name,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    await history_repository.mark_workflow_template_used(user.uid, template_id)
    stored_session = await history_repository.get_session(session.id)
    ticket = session_manager.create_ticket(session.id, user.uid)
    return WorkflowTemplateRunResponse(
        session=_build_session_response(
            session=session,
            ticket=ticket,
            stored_session=stored_session,
        ),
        initial_prompt=initial_prompt,
    )


@app.post("/api/v1/sessions/{session_id}/template", response_model=WorkflowTemplate)
async def save_session_as_workflow_template(
    session_id: str,
    payload: CreateWorkflowTemplateRequest | None = Body(default=None),
    user: AuthenticatedUser = Depends(require_current_user),
):
    return await _create_template_from_session_for_user(
        user=user,
        source_session_id=session_id,
        payload=payload or CreateWorkflowTemplateRequest(),
    )

@app.get("/api/v1/user/settings", response_model=UserSettingsResponse)
async def get_user_settings(user: AuthenticatedUser = Depends(require_current_user)):
    user_settings = await history_repository.get_user_settings(user.uid)
    return build_public_user_settings(user_settings)


@app.patch("/api/v1/user/settings", response_model=UserSettingsResponse)
async def update_user_settings(
    updates: UserSettingsUpdateRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    current_settings = await history_repository.get_user_settings(user.uid)
    update_payload = dict(updates.model_extra or {})

    byok_updates = (
        updates.byok.model_dump(exclude_unset=True)
        if updates.byok is not None
        else {}
    )
    if byok_updates:
        try:
            update_payload["byok"] = build_byok_storage_update(
                current_settings,
                byok_updates,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        candidate_settings = dict(current_settings or {})
        candidate_settings["byok"] = update_payload["byok"]
        try:
            ensure_selected_gemini_provider_available(candidate_settings)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    for raw_key in ("e2bApiKey", "geminiApiKey"):
        update_payload.pop(raw_key, None)

    if update_payload:
        try:
            await history_repository.update_user_settings(user.uid, update_payload)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))

    updated_settings = await history_repository.get_user_settings(user.uid)
    return build_public_user_settings(updated_settings)


@app.get("/api/v1/user/quota")
async def get_user_quota(user: AuthenticatedUser = Depends(require_current_user)):
    """Get the user's plan quota, with credit-first compatibility fields."""
    quota = await history_repository.get_user_quota(user.uid)
    return quota


# ── Google Drive OAuth ──────────────────────────────────────────

_GDRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


def _gdrive_redirect_uri() -> str:
    return f"{settings.frontend_url}/auth/google-drive/callback"


def _gdrive_flow():
    """Build a google-auth-oauthlib Flow. Returns None if OAuth is not configured."""
    if not (settings.google_oauth_client_id and settings.google_oauth_client_secret):
        logger.warning("Google Drive OAuth not configured: client_id=%r secret_set=%s",
                       settings.google_oauth_client_id[:8] if settings.google_oauth_client_id else "",
                       bool(settings.google_oauth_client_secret))
        return None
    try:
        from google_auth_oauthlib.flow import Flow

        client_config = {
            "web": {
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        return Flow.from_client_config(
            client_config,
            scopes=_GDRIVE_SCOPES,
            redirect_uri=_gdrive_redirect_uri(),
        )
    except Exception as exc:
        logger.warning("_gdrive_flow failed: %s", exc, exc_info=True)
        return None


@app.get("/api/v1/auth/google-drive/url")
async def get_google_drive_auth_url(user: AuthenticatedUser = Depends(require_current_user)):
    """Return a Google OAuth URL the frontend should open in a popup."""
    flow = _gdrive_flow()
    if flow is None:
        raise HTTPException(status_code=501, detail="Google Drive OAuth not configured.")

    import jwt as pyjwt
    from datetime import timedelta

    state_payload = {
        "uid": user.uid,
        "purpose": "gdrive_oauth",
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
    }
    state = pyjwt.encode(state_payload, settings.jwt_secret, algorithm="HS256")

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return {"auth_url": auth_url}


@app.post("/api/v1/auth/google-drive/exchange")
async def exchange_google_drive_code(
    body: dict[str, Any],
    user: AuthenticatedUser = Depends(require_current_user),
):
    """Exchange an authorization code for a Drive refresh token and store it."""
    flow = _gdrive_flow()
    if flow is None:
        raise HTTPException(status_code=501, detail="Google Drive OAuth not configured.")

    code = body.get("code", "")
    state = body.get("state", "")
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")

    # Validate state JWT to confirm the OAuth round-trip matches the current user
    import jwt as pyjwt

    try:
        state_data = pyjwt.decode(state, settings.jwt_secret, algorithms=["HS256"])
        if state_data.get("uid") != user.uid or state_data.get("purpose") != "gdrive_oauth":
            raise ValueError("state mismatch")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    try:
        flow.fetch_token(code=code)
        refresh_token = flow.credentials.refresh_token
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {exc}")

    if not refresh_token:
        raise HTTPException(status_code=400, detail="No refresh token returned. Ensure prompt=consent was set.")

    await history_repository.update_user_settings(user.uid, {"googleDriveRefreshToken": refresh_token})
    return {"status": "connected"}


@app.delete("/api/v1/auth/google-drive")
async def disconnect_google_drive(user: AuthenticatedUser = Depends(require_current_user)):
    """Remove the user's stored Google Drive refresh token."""
    await history_repository.update_user_settings(user.uid, {"googleDriveRefreshToken": None})
    return {"status": "disconnected"}


# ── WebSocket Endpoint ──────────────────────────────────────────


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(
    ws: WebSocket,
    session_id: str,
    ticket: str = Query(default=""),
):
    """WebSocket endpoint for voice + agent event streaming."""
    # Validate ticket
    valid_sid, valid_uid = session_manager.validate_ticket(ticket)
    if valid_sid != session_id:
        await ws.close(code=4001, reason="Invalid or expired ticket")
        return
    if not valid_uid or not ws_connect_limiter.is_allowed(valid_uid):
        await ws.close(code=4429, reason="Rate limit exceeded")
        return
    try:
        user_settings = await history_repository.get_user_settings(valid_uid)
        _ensure_beta_access(user_settings)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"detail": str(exc.detail)}
        await ws.close(code=4403, reason=str(detail.get("detail") or "Beta access required"))
        return

    session = session_manager.get_session(session_id)
    if (
        not session
        or session.owner_id != valid_uid
        or session.status in {"destroyed", "ended"}
    ):
        await ws.close(code=4004, reason="Session not found or unavailable")
        return
    await handle_websocket(ws=ws, session=session, session_manager=session_manager)
