"""FastAPI application — REST + WebSocket endpoints for NEXUS."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from nexus.auth import AuthenticatedUser, require_current_user
from nexus.config import settings, apply_runtime_env_overrides
from nexus.history_repository import FirestoreHistoryRepository
from nexus.models import (
    ErrorResponse,
    HealthResponse,
    SessionInfo,
    SessionResponse,
    StatusMessage,
    UserSettingsResponse,
    UserSettingsUpdateRequest,
)
from nexus.runtime_config import (
    build_byok_error_payload,
    build_byok_storage_update,
    build_public_user_settings,
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    apply_runtime_env_overrides()
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
    """Create a new NEXUS session. Sandbox boot is deferred until activation."""
    await history_repository.upsert_user(user)
    user_settings = await history_repository.get_user_settings(user.uid)

    if settings.require_byok:
        byok_status = get_byok_status(user_settings)
        if not byok_status.configured:
            return JSONResponse(
                status_code=403,
                content=build_byok_error_payload(user_settings),
            )

    # Check token quota before allowing new session
    quota = await history_repository.get_user_quota(user.uid)
    if quota["remaining"] <= 0:
        raise HTTPException(
            status_code=403,
            detail=f"Token quota exceeded. You've used {quota['used']:,} of {quota['limit']:,} tokens.",
        )

    try:
        session = await session_manager.create_session(
            owner_id=user.uid,
            runtime_config=resolve_session_runtime_config(user_settings),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    ticket = session_manager.create_ticket(session.id, user.uid)
    return SessionResponse(
        session_id=session.id,
        stream_url=session.stream_url or None,
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
            stream_url=session.stream_url or None,
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
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))

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
    """Get the user's token quota (limit, used, remaining)."""
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

    session = session_manager.get_session(session_id)
    if (
        not session
        or session.owner_id != valid_uid
        or session.status in {"destroyed", "ended"}
    ):
        await ws.close(code=4004, reason="Session not found or unavailable")
        return
    await handle_websocket(ws=ws, session=session, session_manager=session_manager)
