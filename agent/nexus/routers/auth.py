# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Authentication and OAuth endpoints."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException

from nexus.auth import AuthenticatedUser, require_current_user
from nexus.config import settings, get_oauth_client_secret
from nexus.dependencies import get_history_repository

logger = logging.getLogger(__name__)

router = APIRouter()
history_repository = get_history_repository()

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/calendar",
]

def _google_redirect_uri() -> str:
    return f"{settings.frontend_url}/auth/google-drive/callback"

def _google_oauth_configured() -> bool:
    if not (settings.google_oauth_client_id and get_oauth_client_secret()):
        logger.warning("Google OAuth not configured: client_id=%r secret_set=%s",
                       settings.google_oauth_client_id[:8] if settings.google_oauth_client_id else "",
                       bool(get_oauth_client_secret()))
        return False
    return True

def _pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

@router.get("/api/v1/auth/google/url")
async def get_google_auth_url(user: AuthenticatedUser = Depends(require_current_user)):
    """Return a Google OAuth URL the frontend should open in a popup."""
    if not _google_oauth_configured():
        raise HTTPException(status_code=501, detail="Google OAuth not configured.")

    code_verifier = secrets.token_urlsafe(72)[:96]
    from datetime import timedelta
    state_payload = {
        "uid": user.uid,
        "purpose": "google_oauth",
        "cv": code_verifier,
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
    }
    state = pyjwt.encode(state_payload, settings.jwt_secret, algorithm="HS256")

    auth_url = "https://accounts.google.com/o/oauth2/auth?" + urlencode(
        {
            "client_id": settings.google_oauth_client_id,
            "redirect_uri": _google_redirect_uri(),
            "response_type": "code",
            "scope": " ".join(GOOGLE_SCOPES),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
            "code_challenge": _pkce_challenge(code_verifier),
            "code_challenge_method": "S256",
        }
    )
    return {"auth_url": auth_url}

@router.post("/api/v1/auth/google/exchange")
async def exchange_google_code(
    body: dict[str, Any],
    user: AuthenticatedUser = Depends(require_current_user),
):
    """Exchange an authorization code for a Google refresh token and store it."""
    code = body.get("code", "")
    state = body.get("state", "")
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")

    try:
        state_data = pyjwt.decode(state, settings.jwt_secret, algorithms=["HS256"])
        if state_data.get("uid") != user.uid or (state_data.get("purpose") not in ["google_oauth", "gdrive_oauth"]):
            raise ValueError("state mismatch")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    code_verifier = state_data.get("cv")
    if not isinstance(code_verifier, str) or not code_verifier:
        raise HTTPException(status_code=400, detail="Invalid OAuth code verifier")

    if not _google_oauth_configured():
        raise HTTPException(status_code=501, detail="Google OAuth not configured.")

    client_secret = get_oauth_client_secret()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": settings.google_oauth_client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "code_verifier": code_verifier,
                    "grant_type": "authorization_code",
                    "redirect_uri": _google_redirect_uri(),
                },
            )
        if token_response.status_code >= 400:
            raise RuntimeError(token_response.text[:1000])
        token_payload = token_response.json()
        refresh_token = token_payload.get("refresh_token")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {exc}")

    if not refresh_token:
        existing_settings = await history_repository.get_user_settings(user.uid)
        refresh_token = (existing_settings or {}).get("googleDriveRefreshToken")
    if not refresh_token:
        raise HTTPException(
            status_code=400,
            detail="No refresh token returned. Remove prior app access from your Google Account, then reconnect.",
        )

    await history_repository.update_user_settings(user.uid, {"googleDriveRefreshToken": refresh_token})
    await history_repository.upsert_google_connections(user.uid)
    return {"status": "connected"}

@router.post("/api/v1/auth/google-drive/exchange")
async def exchange_google_drive_code_compat(
    body: dict[str, Any],
    user: AuthenticatedUser = Depends(require_current_user),
):
    """Compatibility endpoint for old frontend callback pages."""
    return await exchange_google_code(body, user)

@router.delete("/api/v1/auth/google")
async def disconnect_google(user: AuthenticatedUser = Depends(require_current_user)):
    """Remove Google connection for the current user."""
    await history_repository.update_user_settings(user.uid, {"googleDriveRefreshToken": None})
    for connection_id in ("google_drive", "gmail", "google_calendar", "google_tasks"):
        await history_repository.delete_integration_connection(user.uid, connection_id)
    return {"status": "disconnected"}
