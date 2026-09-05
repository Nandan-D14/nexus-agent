# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Shared helper functions for sessions and templates."""

from __future__ import annotations

from typing import Any
from fastapi import HTTPException

from nexus.auth import AuthenticatedUser
from nexus.config import settings
from nexus.dependencies import get_history_repository
from nexus.models import SessionResponse, HandoffSummary, ContextPacket
from nexus.runtime_config import (
    byok_enforced,
    get_byok_status,
    build_byok_error_payload,
    ensure_selected_gemini_provider_available,
)

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
        task_id=getattr(session, "task_id", None) or (stored_session.task_id if stored_session else session.id),
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

async def _prepare_user_runtime(user: AuthenticatedUser) -> dict[str, Any]:
    history_repository = get_history_repository()
    await history_repository.upsert_user(user)
    user_settings = await history_repository.get_user_settings(user.uid)
    try:
        ensure_selected_gemini_provider_available(user_settings)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    if byok_enforced():
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
