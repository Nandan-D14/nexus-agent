"""FastAPI application — REST + WebSocket endpoints for NEXUS."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from nexus.auth import AuthenticatedUser, require_current_user
from nexus.config import settings
from nexus.history_repository import FirestoreHistoryRepository
from nexus.models import ErrorResponse, HealthResponse, SessionInfo, SessionResponse, StatusMessage
from nexus.session import SessionManager
from nexus.ws_handler import handle_websocket

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

history_repository = FirestoreHistoryRepository()
session_manager = SessionManager(history_repository=history_repository)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("NEXUS agent service starting...")
    session_manager.start_cleanup()
    yield
    logger.info("NEXUS agent service shutting down...")
    session_manager.stop_cleanup()
    await session_manager.destroy_all()


app = FastAPI(
    title="NEXUS Agent Service",
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


# ── REST Endpoints ──────────────────────────────────────────────


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(active_sessions=session_manager.active_count)


@app.post("/sessions", response_model=SessionResponse)
async def create_session(user: AuthenticatedUser = Depends(require_current_user)):
    """Create a new NEXUS session with an E2B sandbox."""
    await history_repository.upsert_user(user)
    try:
        session = await session_manager.create_session(owner_id=user.uid)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    ticket = session_manager.create_ticket(session.id, user.uid)
    return SessionResponse(
        session_id=session.id,
        stream_url=session.stream_url,
        ws_ticket=ticket,
        status=session.status,
        created_at=session.created_at,
    )


@app.get("/sessions/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str, user: AuthenticatedUser = Depends(require_current_user)):
    session = session_manager.get_session(session_id)
    if session:
        if session.owner_id != user.uid:
            raise HTTPException(status_code=404, detail="Session not found")
        return SessionInfo(
            session_id=session.id,
            status=session.status,
            is_live=True,
            stream_url=session.stream_url,
            created_at=session.created_at,
        )

    stored_session = await history_repository.get_session(session_id)
    if not stored_session or stored_session.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionInfo(
        session_id=stored_session.session_id,
        status=stored_session.status,
        is_live=False,
        stream_url=None,
        created_at=stored_session.created_at,
        ended_at=stored_session.ended_at,
        summary=stored_session.summary,
        message_count=stored_session.message_count,
    )


@app.delete("/sessions/{session_id}", response_model=StatusMessage)
async def delete_session(session_id: str, user: AuthenticatedUser = Depends(require_current_user)):
    try:
        await session_manager.destroy_if_owned(session_id, user.uid, status="ended")
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
    except PermissionError:
        raise HTTPException(status_code=404, detail="Session not found")
    return StatusMessage(status="destroyed")


@app.post("/sessions/{session_id}/ticket")
async def refresh_ticket(session_id: str, user: AuthenticatedUser = Depends(require_current_user)):
    """Generate a new WS authentication ticket for an existing session."""
    session = session_manager.get_session(session_id)
    if not session or session.owner_id != user.uid:
        raise HTTPException(status_code=404, detail="Session not found")
    ticket = session_manager.create_ticket(session_id, user.uid)
    return {"ws_ticket": ticket}


@app.get("/api/v1/dashboard/stats")
async def get_dashboard_stats(user: AuthenticatedUser = Depends(require_current_user)):
    return await history_repository.get_dashboard_stats(user.uid)


@app.get("/api/v1/dashboard/usage")
async def get_dashboard_usage(
    days: int = Query(30, ge=1, le=90),
    user: AuthenticatedUser = Depends(require_current_user)
):
    chart = await history_repository.get_dashboard_usage(user.uid, days)
    return {"chart": chart}


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
            }
            for s in sessions
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

@app.get("/api/v1/user/settings")
async def get_user_settings(user: AuthenticatedUser = Depends(require_current_user)):
    settings = await history_repository.get_user_settings(user.uid)
    return settings

@app.patch("/api/v1/user/settings")
async def update_user_settings(updates: dict[str, Any], user: AuthenticatedUser = Depends(require_current_user)):
    await history_repository.update_user_settings(user.uid, updates)
    return {"status": "ok"}

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

    session = session_manager.get_session(session_id)
    if (
        not session
        or session.owner_id != valid_uid
        or session.status not in {"ready", "active"}
    ):
        await ws.close(code=4004, reason="Session not found or not ready")
        return

    try:
        await session_manager.activate_session(session_id)
    except Exception as exc:
        logger.exception("Failed to activate session %s: %s", session_id, exc)
        await ws.close(code=4000, reason="Session activation failed")
        return
    await handle_websocket(ws=ws, session=session, session_manager=session_manager)
