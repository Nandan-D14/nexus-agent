# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""WebSocket endpoints."""

from __future__ import annotations

import logging
from fastapi import APIRouter, WebSocket

from nexus.dependencies import get_session_manager, get_history_repository, get_ws_connect_limiter
from nexus.runtime_config import resolve_session_runtime_config
from nexus.ws_handler import handle_websocket

logger = logging.getLogger(__name__)

router = APIRouter()


def _offered_subprotocols(ws: WebSocket) -> list[str]:
    protocol_header = ws.headers.get("sec-websocket-protocol", "")
    if not protocol_header:
        return []
    return [part.strip() for part in protocol_header.split(",") if part.strip()]


def _ticket_candidates(ws: WebSocket) -> list[tuple[str, str | None]]:
    candidates: list[tuple[str, str | None]] = []
    query_ticket = str(ws.query_params.get("ticket") or "").strip()
    if query_ticket:
        candidates.append((query_ticket, None))
    candidates.extend((candidate, candidate) for candidate in _offered_subprotocols(ws))
    return candidates


def _negotiated_subprotocol(ws: WebSocket, accepted: str | None = None) -> str | None:
    """Return a protocol the browser offered so accept() can echo it.

    Browsers fail the handshake when they send Sec-WebSocket-Protocol and the
    server accepts without selecting one of those values. Query-string tickets
    authenticate first and carry subprotocol=None, so success must still echo
    an offered protocol when the client sent one.
    """
    if accepted:
        return accepted
    offered = _offered_subprotocols(ws)
    return offered[0] if offered else None


async def _reject_ws(
    ws: WebSocket,
    *,
    code: int,
    reason: str,
    message: str,
    subprotocol: str | None = None,
) -> None:
    await ws.accept(subprotocol=_negotiated_subprotocol(ws, subprotocol))
    await ws.send_json({"type": "error", "code": reason, "message": message})
    await ws.close(code=code, reason=message[:120])


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(
    ws: WebSocket,
    session_id: str,
):
    """WebSocket endpoint for voice + agent event streaming."""
    logger.info("WS handshake for session %s", session_id[:16])
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
            subprotocol=accepted_subprotocol,
        )
        return
    try:
        user_settings = await history_repository.get_user_settings(valid_uid)
    except Exception:
        await _reject_ws(
            ws,
            code=4403,
            reason="WS_FORBIDDEN",
            message="Could not load account settings. Retry in a moment.",
            subprotocol=accepted_subprotocol,
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
            subprotocol=accepted_subprotocol,
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
                subprotocol=accepted_subprotocol,
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
            resume_mode=(
                "continue_latest_workspace"
                if exact_workspace_resume_available
                else "continue_conversation"
            ),
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
        subprotocol=_negotiated_subprotocol(ws, accepted_subprotocol),
    )
