# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""WebSocket endpoints."""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, WebSocket

from nexus.auth import AuthenticatedUser
from nexus.beta_access import normalize_beta_profile, beta_access_enabled, beta_can_access_app, build_beta_error_payload
from nexus.dependencies import get_session_manager, get_history_repository, get_ws_connect_limiter, RateLimiter
from nexus.runtime_config import resolve_session_runtime_config
from nexus.ws_handler import handle_websocket

logger = logging.getLogger(__name__)

router = APIRouter()

def _ensure_beta_access(user_settings: dict | None) -> None:
    if not beta_access_enabled():
        return
    profile = normalize_beta_profile(user_settings)
    if beta_can_access_app(profile):
        return
    raise HTTPException(status_code=403, detail=build_beta_error_payload(profile))


def _ticket_candidates(ws: WebSocket) -> list[tuple[str, str | None]]:
    query_ticket = str(ws.query_params.get("ticket") or "").strip()
    if query_ticket:
        return [(query_ticket, None)]

    protocol_header = ws.headers.get("sec-websocket-protocol", "")
    return [
        (candidate, candidate)
        for candidate in (part.strip() for part in protocol_header.split(","))
        if candidate
    ]


async def _reject_ws(ws: WebSocket, *, code: int, reason: str, message: str) -> None:
    await ws.accept()
    await ws.send_json({"type": "error", "code": reason, "message": message})
    await ws.close(code=code, reason=message[:120])


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(
    ws: WebSocket,
    session_id: str,
):
    """WebSocket endpoint for voice + agent event streaming."""
    session_manager = get_session_manager()
    ws_connect_limiter = get_ws_connect_limiter()
    history_repository = get_history_repository()

    # Validate ticket
    valid_sid = valid_uid = None
    accepted_subprotocol: str | None = None
    for ticket, subprotocol in _ticket_candidates(ws):
        valid_sid, valid_uid = session_manager.validate_ticket(ticket)
        if valid_sid == session_id and valid_uid:
            accepted_subprotocol = subprotocol
            break

    if valid_sid != session_id:
        await _reject_ws(
            ws,
            code=4001,
            reason="WS_AUTH_FAILED",
            message="Invalid or expired session ticket. Refresh the page or resume the session.",
        )
        return
    if not valid_uid or not ws_connect_limiter.check(valid_uid):
        await _reject_ws(
            ws,
            code=4429,
            reason="WS_RATE_LIMITED",
            message="Too many reconnect attempts. Wait a minute, then try again.",
        )
        return
    try:
        user_settings = await history_repository.get_user_settings(valid_uid)
        _ensure_beta_access(user_settings)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"detail": str(exc.detail)}
        await _reject_ws(
            ws,
            code=4403,
            reason="WS_FORBIDDEN",
            message=str(detail.get("detail") or "Beta access required"),
        )
        return

    session = await session_manager.get_session(session_id)
    if (
        not session
        or session.owner_id != valid_uid
        or session.status in {"deleted", "destroyed"}
    ):
        await _reject_ws(
            ws,
            code=4004,
            reason="WS_SESSION_UNAVAILABLE",
            message="Session not found or unavailable. Resume or create a new session.",
        )
        return

    if getattr(session, "runtime_config", None) is None:
        stored_session = await history_repository.get_session(session_id)
        if not stored_session or stored_session.owner_id != valid_uid or stored_session.status in {"deleted", "destroyed"}:
            await _reject_ws(
                ws,
                code=4004,
                reason="WS_SESSION_UNAVAILABLE",
                message="Session not found or unavailable. Resume or create a new session.",
            )
            return
        workspace_state = await history_repository.get_workspace_state(valid_uid)
        exact_workspace_resume_available = (
            workspace_state.get("session_id") == session_id
            and bool(workspace_state.get("sandbox_id"))
        )
        session = await session_manager.continue_session(
            session_id=session_id,
            owner_id=valid_uid,
            runtime_config=resolve_session_runtime_config(user_settings),
            created_at=stored_session.created_at,
            resume_mode="continue_latest_workspace" if exact_workspace_resume_available else "fresh",
            seed_context="",
            initial_title=stored_session.title or "Continued session",
            task_id=stored_session.task_id,
            artifact_count=stored_session.artifact_count,
            exact_workspace_resume_available=exact_workspace_resume_available,
            continuation_mode=(
                "exact_workspace_resume"
                if exact_workspace_resume_available
                else "new_sandbox_resume"
            ),
        )

    await handle_websocket(
        ws=ws,
        session=session,
        session_manager=session_manager,
        subprotocol=accepted_subprotocol,
    )
