# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Sessions endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from nexus.auth import AuthenticatedUser, require_current_user
from nexus.config import settings
from nexus.dependencies import get_history_repository, get_session_manager, get_session_create_limiter, get_ticket_refresh_limiter
from nexus.models import (
    HistoryReuseRequest,
    RunInfo,
    RunStep,
    SessionCreateRequest,
    SessionInfo,
    SessionResponse,
    StatusMessage,
    TaskInfo,
    UserSettingsResponse,
    UserSettingsUpdateRequest,
)
from nexus.runtime_config import build_byok_storage_update, build_public_user_settings, resolve_session_runtime_config, ensure_selected_gemini_provider_available
from nexus.usage import get_expected_usage_sources
from nexus.sessions_helpers import (
    _build_session_response,
    _prepare_user_runtime,
    _serialize_context_packet,
    _serialize_handoff_summary,
    _ensure_beta_access,
)

router = APIRouter()

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
        task_id=stored_session.task_id,
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
        task_id=run.task_id,
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

def _serialize_task(task) -> TaskInfo:
    return TaskInfo(
        task_id=task.task_id,
        owner_id=task.owner_id,
        title=task.title,
        status=task.status,
        created_at=task.created_at,
        updated_at=task.updated_at,
        current_session_id=task.current_session_id,
        current_run_id=task.current_run_id,
        run_status=task.run_status,
        message_count=task.message_count,
        step_count=task.step_count,
        artifact_count=task.artifact_count,
    )

def _serialize_run_step(step) -> RunStep:
    return RunStep(
        step_id=step.step_id,
        run_id=step.run_id,
        session_id=step.session_id,
        task_id=step.task_id,
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

async def _resolve_source_session(
    owner_id: str,
    source_session_id: str | None,
):
    history_repository = get_history_repository()
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

async def _continue_existing_session_for_user(
    user: AuthenticatedUser,
    *,
    session_id: str,
) -> SessionResponse:
    user_settings = await _prepare_user_runtime(user)
    session_manager = get_session_manager()
    history_repository = get_history_repository()

    live_session = await session_manager.get_session(session_id)
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
    session_manager = get_session_manager()
    history_repository = get_history_repository()

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

@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    payload: SessionCreateRequest | None = Body(default=None),
    user: AuthenticatedUser = Depends(require_current_user),
):
    """Create a new CoComputer session using an explicit workspace mode."""
    if not get_session_create_limiter().check(user.uid):
        raise HTTPException(status_code=429, detail="Too many session requests. Please wait and try again.")
    return await _create_session_for_user(user, payload or SessionCreateRequest())

@router.get("/api/v1/workspace/resume")
async def get_resume_workspace(user: AuthenticatedUser = Depends(require_current_user)):
    history_repository = get_history_repository()
    workspace_state = await history_repository.get_workspace_state(user.uid)
    session_id = workspace_state.get("session_id")
    stored_session = await history_repository.get_session(session_id) if session_id else None
    return {
        "available": bool(workspace_state.get("sandbox_id") and stored_session),
        "session": _build_session_info_from_stored(stored_session).model_dump(mode="json") if stored_session else None,
    }

@router.post("/api/v1/history/{session_id}/reuse", response_model=SessionResponse)
async def reuse_history_session(
    session_id: str,
    body: HistoryReuseRequest | None = Body(default=None),
    user: AuthenticatedUser = Depends(require_current_user),
):
    if not get_session_create_limiter().check(user.uid):
        raise HTTPException(status_code=429, detail="Too many session requests. Please wait and try again.")
    history_repository = get_history_repository()
    stored_session = await history_repository.get_session(session_id)
    if not stored_session or stored_session.owner_id != user.uid or stored_session.status == "deleted":
        raise HTTPException(status_code=404, detail="Session not found")
    return await _continue_existing_session_for_user(user, session_id=session_id)

@router.post("/sessions/{session_id}/continue", response_model=SessionResponse)
async def continue_session(
    session_id: str,
    user: AuthenticatedUser = Depends(require_current_user),
):
    if not get_session_create_limiter().check(user.uid):
        raise HTTPException(status_code=429, detail="Too many session requests. Please wait and try again.")
    return await _continue_existing_session_for_user(user, session_id=session_id)

@router.get("/sessions/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str, user: AuthenticatedUser = Depends(require_current_user)):
    session_manager = get_session_manager()
    history_repository = get_history_repository()
    session = await session_manager.get_session(session_id)
    stored_session = await history_repository.get_session(session_id)
    if session:
        if session.owner_id != user.uid:
            raise HTTPException(status_code=404, detail="Session not found")
        return SessionInfo(
            session_id=session.id,
            task_id=getattr(session, "task_id", None) or (stored_session.task_id if stored_session else session.id),
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

@router.delete("/sessions/{session_id}", response_model=StatusMessage)
async def delete_session(session_id: str, user: AuthenticatedUser = Depends(require_current_user)):
    session_manager = get_session_manager()
    history_repository = get_history_repository()
    try:
        await session_manager.destroy_if_owned(session_id, user.uid, status="ended")
    except KeyError:
        stored_session = await history_repository.get_session(session_id)
        if not stored_session or stored_session.owner_id != user.uid:
            raise HTTPException(status_code=404, detail="Session not found")
        await history_repository.mark_session_deleted(session_id)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Session not found")
    return StatusMessage(status="destroyed")

@router.post("/sessions/{session_id}/ticket")
async def refresh_ticket(session_id: str, user: AuthenticatedUser = Depends(require_current_user)):
    """Generate a new WS authentication ticket for an existing session."""
    if not get_ticket_refresh_limiter().check(user.uid):
        raise HTTPException(status_code=429, detail="Too many ticket refresh requests. Please slow down.")
    history_repository = get_history_repository()
    user_settings = await history_repository.get_user_settings(user.uid)
    _ensure_beta_access(user_settings)
    session_manager = get_session_manager()
    session = await session_manager.get_session(session_id)
    if not session or session.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Session not found")
    ticket = session_manager.create_ticket(session_id, user.uid)
    return {"ws_ticket": ticket}

@router.get("/api/v1/dashboard/stats")
async def get_dashboard_stats(user: AuthenticatedUser = Depends(require_current_user)):
    history_repository = get_history_repository()
    stats = await history_repository.get_dashboard_stats(user.uid)
    tracked_sources = set(stats.get("tracked_sources", []))
    configured_sources = set(get_expected_usage_sources())
    stats["tracked_sources"] = sorted(tracked_sources)
    stats["untracked_sources"] = sorted(configured_sources - tracked_sources)
    return stats

@router.get("/api/v1/dashboard/usage")
async def get_dashboard_usage(
    days: int = Query(30, ge=1, le=90),
    user: AuthenticatedUser = Depends(require_current_user)
):
    history_repository = get_history_repository()
    chart = await history_repository.get_dashboard_usage(user.uid, days)
    return {"chart": chart}

@router.get("/api/v1/dashboard/sessions")
async def get_dashboard_sessions(
    limit: int = Query(10, ge=1, le=50),
    user: AuthenticatedUser = Depends(require_current_user),
):
    history_repository = get_history_repository()
    sessions = await history_repository.list_recent_session_usage(user.uid, limit)
    return {"sessions": sessions}

@router.get("/api/v1/sessions/active")
async def get_active_sessions(user: AuthenticatedUser = Depends(require_current_user)):
    history_repository = get_history_repository()
    sessions = await history_repository.list_active_sessions(user.uid)
    return {"sessions": sessions}

@router.get("/api/v1/history")
async def list_history(
    limit: int = Query(25, ge=1, le=100),
    status: str | None = Query(None),
    q: str | None = Query(None),
    user: AuthenticatedUser = Depends(require_current_user)
):
    history_repository = get_history_repository()
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

@router.get("/api/v1/tasks")
async def list_tasks(
    limit: int = Query(25, ge=1, le=100),
    status: str | None = Query(None),
    q: str | None = Query(None),
    user: AuthenticatedUser = Depends(require_current_user),
):
    history_repository = get_history_repository()
    tasks = await history_repository.list_tasks(user.uid, limit, status, q)
    return {"tasks": [_serialize_task(task).model_dump(mode="json") for task in tasks]}

@router.get("/api/v1/tasks/{task_id}", response_model=TaskInfo)
async def get_task(task_id: str, user: AuthenticatedUser = Depends(require_current_user)):
    history_repository = get_history_repository()
    task = await history_repository.get_task(user.uid, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _serialize_task(task)

@router.get("/api/v1/sessions/{session_id}/run")
async def get_session_run(session_id: str, user: AuthenticatedUser = Depends(require_current_user)):
    session_manager = get_session_manager()
    history_repository = get_history_repository()
    session = await session_manager.get_session(session_id)
    if session and session.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Session not found")

    stored_session = await history_repository.get_session(session_id)
    if not session and (not stored_session or stored_session.owner_id != user.uid):
        raise HTTPException(status_code=404, detail="Session not found")
    if session and not stored_session:
        stored_session = await history_repository.get_session(session_id)

    run = await history_repository.get_session_run(session_id)
    return {"run": _serialize_run(run).model_dump(mode="json") if run else None}

@router.get("/api/v1/sessions/{session_id}/artifacts")
async def get_session_artifacts(session_id: str, user: AuthenticatedUser = Depends(require_current_user)):
    session_manager = get_session_manager()
    history_repository = get_history_repository()
    session = await session_manager.get_session(session_id)
    if session and session.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Session not found")

    stored_session = await history_repository.get_session(session_id)
    if not session and (not stored_session or stored_session.owner_id != user.uid):
        raise HTTPException(status_code=404, detail="Session not found")

    run = await history_repository.get_session_run(session_id)
    if not run:
        return {"artifacts": []}

    from nexus.routers.files import _serialize_artifact
    artifacts = await history_repository.list_run_artifacts(session_id, run.run_id)
    return {
        "artifacts": [
            _serialize_artifact(artifact).model_dump(mode="json")
            for artifact in artifacts
        ]
    }

@router.get("/api/v1/sessions/{session_id}/run/steps")
async def get_session_run_steps(session_id: str, user: AuthenticatedUser = Depends(require_current_user)):
    session_manager = get_session_manager()
    history_repository = get_history_repository()
    session = await session_manager.get_session(session_id)
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

@router.get("/api/v1/history/{session_id}/messages")
async def get_history_messages(session_id: str, user: AuthenticatedUser = Depends(require_current_user)):
    history_repository = get_history_repository()
    session = await history_repository.get_session(session_id)
    if not session or session.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Session not found")
        
    messages = await history_repository.get_session_messages(session_id)
    return {"messages": messages}

@router.get("/api/v1/user/settings", response_model=UserSettingsResponse)
async def get_user_settings(user: AuthenticatedUser = Depends(require_current_user)):
    history_repository = get_history_repository()
    user_settings = await history_repository.get_user_settings(user.uid)
    return build_public_user_settings(user_settings)

@router.patch("/api/v1/user/settings", response_model=UserSettingsResponse)
async def update_user_settings(
    updates: UserSettingsUpdateRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    history_repository = get_history_repository()
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
