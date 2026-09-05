# Copyright (c) 2026 nandan-d14. All rights reserved.
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
from nexus.exa_oauth import (
    EXA_CONNECTION_ID,
    EXA_MCP_URL,
    EXA_OAUTH_PURPOSE,
    ExaOAuthError,
    build_exa_authorization_url,
    discover_exa_authorization_server,
    exchange_exa_authorization_code,
    exa_redirect_uri,
    persist_exa_tokens,
    register_exa_oauth_client,
)
from nexus.mcp_client import McpRemoteClient, discovered_tools_payload
from nexus.mcp_oauth import (
    McpOAuthError,
    build_mcp_authorization_url,
    discover_mcp_authorization_server,
    exchange_mcp_authorization_code,
    mcp_redirect_uri,
    mcp_spec,
    persist_mcp_oauth_tokens,
    register_mcp_oauth_client,
)
from nexus.slack_oauth import (
    SLACK_CONNECTION_ID,
    SLACK_MCP_URL,
    SLACK_OAUTH_PURPOSE,
    SlackOAuthError,
    build_slack_authorization_url,
    exchange_slack_authorization_code,
    persist_slack_tokens,
    slack_oauth_configured,
    slack_user_token,
)
from nexus.treg_oauth import (
    TREG_CONNECTION_ID,
    TREG_MCP_URL,
    TREG_OAUTH_PURPOSE,
    TregOAuthError,
    build_treg_authorization_url,
    discover_treg_authorization_server,
    exchange_treg_authorization_code,
    persist_treg_tokens,
    register_treg_oauth_client,
    treg_redirect_uri,
)

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
            logger.error("Google token exchange failed: status=%d response=%s", 
                         token_response.status_code, token_response.text)
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


@router.get("/api/v1/auth/exa/url")
async def get_exa_auth_url(user: AuthenticatedUser = Depends(require_current_user)):
    """Return an Exa MCP OAuth URL the frontend should open in a popup."""
    redirect_uri = exa_redirect_uri()
    code_verifier = secrets.token_urlsafe(72)[:96]
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            metadata = await discover_exa_authorization_server(client)
            registered = await register_exa_oauth_client(client, metadata, redirect_uri)
    except ExaOAuthError as exc:
        logger.error("Exa OAuth setup failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        logger.error("Exa OAuth discovery HTTP error: %s", exc)
        raise HTTPException(status_code=502, detail=f"Could not reach Exa OAuth: {exc}") from exc

    client_id = str(registered.get("client_id") or "")
    if not client_id:
        raise HTTPException(status_code=502, detail="Exa OAuth registration returned no client_id.")

    from datetime import timedelta

    state_payload = {
        "uid": user.uid,
        "purpose": EXA_OAUTH_PURPOSE,
        "cv": code_verifier,
        "cid": client_id,
        "cs": str(registered.get("client_secret") or ""),
        "te": str(metadata.get("token_endpoint") or ""),
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
    }
    state = pyjwt.encode(state_payload, settings.jwt_secret, algorithm="HS256")
    auth_url = build_exa_authorization_url(
        metadata=metadata,
        client_id=client_id,
        redirect_uri=redirect_uri,
        state=state,
        code_verifier=code_verifier,
    )
    return {"auth_url": auth_url}


@router.post("/api/v1/auth/exa/exchange")
async def exchange_exa_code(
    body: dict[str, Any],
    user: AuthenticatedUser = Depends(require_current_user),
):
    """Exchange an Exa authorization code, discover MCP tools, and store the connection."""
    code = body.get("code", "")
    state = body.get("state", "")
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")

    try:
        state_data = pyjwt.decode(state, settings.jwt_secret, algorithms=["HS256"])
        if state_data.get("uid") != user.uid or state_data.get("purpose") != EXA_OAUTH_PURPOSE:
            raise ValueError("state mismatch")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    code_verifier = state_data.get("cv")
    client_id = state_data.get("cid")
    token_endpoint = state_data.get("te")
    if not isinstance(code_verifier, str) or not code_verifier:
        raise HTTPException(status_code=400, detail="Invalid OAuth code verifier")
    if not isinstance(client_id, str) or not client_id:
        raise HTTPException(status_code=400, detail="Invalid OAuth client id")
    if not isinstance(token_endpoint, str) or not token_endpoint:
        raise HTTPException(status_code=400, detail="Invalid OAuth token endpoint")
    client_secret = state_data.get("cs") if isinstance(state_data.get("cs"), str) else ""

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            token_payload = await exchange_exa_authorization_code(
                client,
                token_endpoint=token_endpoint,
                code=str(code),
                redirect_uri=exa_redirect_uri(),
                code_verifier=code_verifier,
                client_id=client_id,
                client_secret=client_secret,
            )
    except ExaOAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {exc}") from exc

    access_token = str(token_payload.get("access_token") or "")
    test = await McpRemoteClient(url=EXA_MCP_URL, bearer_token=access_token).discover()
    status = "connected" if test.ok else "error"
    await persist_exa_tokens(
        user.uid,
        token_payload,
        client_id=client_id,
        client_secret=client_secret,
        token_endpoint=token_endpoint,
        tools=discovered_tools_payload(test.tools),
        resources=test.resources,
        status=status,
        last_error=test.error or None,
        latency_ms=test.latency_ms,
        enabled=test.ok,
    )
    if not test.ok:
        raise HTTPException(
            status_code=400,
            detail=test.error or "Connected to Exa but MCP tool discovery failed.",
        )
    return {"status": "connected"}


@router.delete("/api/v1/auth/exa")
async def disconnect_exa(user: AuthenticatedUser = Depends(require_current_user)):
    """Remove the Exa connection for the current user."""
    await history_repository.delete_integration_connection(user.uid, EXA_CONNECTION_ID)
    return {"status": "disconnected"}


@router.get("/api/v1/auth/treg/url")
async def get_treg_auth_url(user: AuthenticatedUser = Depends(require_current_user)):
    """Return a Treg MCP OAuth URL the frontend should open in a popup."""
    redirect_uri = treg_redirect_uri()
    code_verifier = secrets.token_urlsafe(72)[:96]
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            metadata = await discover_treg_authorization_server(client)
            registered = await register_treg_oauth_client(client, metadata, redirect_uri)
    except TregOAuthError as exc:
        logger.error("Treg OAuth setup failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        logger.error("Treg OAuth discovery HTTP error: %s", exc)
        raise HTTPException(status_code=502, detail=f"Could not reach Treg OAuth: {exc}") from exc

    client_id = str(registered.get("client_id") or "")
    if not client_id:
        raise HTTPException(status_code=502, detail="Treg OAuth registration returned no client_id.")

    from datetime import timedelta

    state_payload = {
        "uid": user.uid,
        "purpose": TREG_OAUTH_PURPOSE,
        "cv": code_verifier,
        "cid": client_id,
        "cs": str(registered.get("client_secret") or ""),
        "te": str(metadata.get("token_endpoint") or ""),
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
    }
    state = pyjwt.encode(state_payload, settings.jwt_secret, algorithm="HS256")
    auth_url = build_treg_authorization_url(
        metadata=metadata,
        client_id=client_id,
        redirect_uri=redirect_uri,
        state=state,
        code_verifier=code_verifier,
    )
    return {"auth_url": auth_url}


@router.post("/api/v1/auth/treg/exchange")
async def exchange_treg_code(
    body: dict[str, Any],
    user: AuthenticatedUser = Depends(require_current_user),
):
    """Exchange a Treg authorization code, discover MCP tools, and store the connection."""
    code = body.get("code", "")
    state = body.get("state", "")
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")

    try:
        state_data = pyjwt.decode(state, settings.jwt_secret, algorithms=["HS256"])
        if state_data.get("uid") != user.uid or state_data.get("purpose") != TREG_OAUTH_PURPOSE:
            raise ValueError("state mismatch")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    code_verifier = state_data.get("cv")
    client_id = state_data.get("cid")
    token_endpoint = state_data.get("te")
    if not isinstance(code_verifier, str) or not code_verifier:
        raise HTTPException(status_code=400, detail="Invalid OAuth code verifier")
    if not isinstance(client_id, str) or not client_id:
        raise HTTPException(status_code=400, detail="Invalid OAuth client id")
    if not isinstance(token_endpoint, str) or not token_endpoint:
        raise HTTPException(status_code=400, detail="Invalid OAuth token endpoint")
    client_secret = state_data.get("cs") if isinstance(state_data.get("cs"), str) else ""

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            token_payload = await exchange_treg_authorization_code(
                client,
                token_endpoint=token_endpoint,
                code=str(code),
                redirect_uri=treg_redirect_uri(),
                code_verifier=code_verifier,
                client_id=client_id,
                client_secret=client_secret,
            )
    except TregOAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {exc}") from exc

    access_token = str(token_payload.get("access_token") or "")
    test = await McpRemoteClient(url=TREG_MCP_URL, bearer_token=access_token).discover()
    status = "connected" if test.ok else "error"
    await persist_treg_tokens(
        user.uid,
        token_payload,
        client_id=client_id,
        client_secret=client_secret,
        token_endpoint=token_endpoint,
        tools=discovered_tools_payload(test.tools),
        resources=test.resources,
        status=status,
        last_error=test.error or None,
        latency_ms=test.latency_ms,
        enabled=test.ok,
    )
    if not test.ok:
        raise HTTPException(
            status_code=400,
            detail=test.error or "Connected to Treg but MCP tool discovery failed.",
        )
    return {"status": "connected"}


GITHUB_OAUTH_PURPOSE = "github_oauth"
GITHUB_SCOPES = "repo read:user"
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"


def _github_redirect_uri() -> str:
    return f"{settings.frontend_url.rstrip('/')}/auth/github/callback"


def _github_oauth_configured() -> bool:
    return bool(settings.github_oauth_client_id and settings.github_oauth_client_secret)


@router.delete("/api/v1/auth/treg")
async def disconnect_treg(user: AuthenticatedUser = Depends(require_current_user)):
    """Remove the Treg connection for the current user."""
    await history_repository.delete_integration_connection(user.uid, TREG_CONNECTION_ID)
    return {"status": "disconnected"}


@router.get("/api/v1/auth/github/url")
async def get_github_auth_url(user: AuthenticatedUser = Depends(require_current_user)):
    """Return a GitHub OAuth URL the frontend should open in a popup."""
    if not _github_oauth_configured():
        raise HTTPException(status_code=501, detail="GitHub OAuth not configured.")
    code_verifier = secrets.token_urlsafe(72)[:96]
    from datetime import timedelta

    state_payload = {
        "uid": user.uid,
        "purpose": GITHUB_OAUTH_PURPOSE,
        "cv": code_verifier,
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
    }
    state = pyjwt.encode(state_payload, settings.jwt_secret, algorithm="HS256")
    params = {
        "client_id": settings.github_oauth_client_id,
        "redirect_uri": _github_redirect_uri(),
        "response_type": "code",
        "scope": GITHUB_SCOPES,
        "state": state,
        "code_challenge": _pkce_challenge(code_verifier),
        "code_challenge_method": "S256",
    }
    return {"auth_url": f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"}


@router.post("/api/v1/auth/github/exchange")
async def exchange_github_code(
    body: dict[str, Any],
    user: AuthenticatedUser = Depends(require_current_user),
):
    """Exchange a GitHub authorization code and store the access token on the native connection."""
    if not _github_oauth_configured():
        raise HTTPException(status_code=501, detail="GitHub OAuth not configured.")
    code = body.get("code", "")
    state = body.get("state", "")
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")
    try:
        state_data = pyjwt.decode(state, settings.jwt_secret, algorithms=["HS256"])
        if state_data.get("uid") != user.uid or state_data.get("purpose") != GITHUB_OAUTH_PURPOSE:
            raise ValueError("state mismatch")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    code_verifier = state_data.get("cv")
    if not isinstance(code_verifier, str) or not code_verifier:
        raise HTTPException(status_code=400, detail="Invalid OAuth code verifier")

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            token_response = await client.post(
                GITHUB_TOKEN_URL,
                data={
                    "client_id": settings.github_oauth_client_id,
                    "client_secret": settings.github_oauth_client_secret,
                    "code": str(code),
                    "grant_type": "authorization_code",
                    "redirect_uri": _github_redirect_uri(),
                    "code_verifier": code_verifier,
                },
                headers={"Accept": "application/json"},
            )
            token_payload = token_response.json()
            if token_response.status_code >= 400 or not isinstance(token_payload, dict):
                raise HTTPException(status_code=400, detail="GitHub token exchange failed.")
            access_token = str(token_payload.get("access_token") or "")
            if not access_token:
                error = token_payload.get("error_description") or token_payload.get("error") or "no access token"
                raise HTTPException(status_code=400, detail=f"GitHub token exchange failed: {error}")
            user_response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=400, detail=f"GitHub token exchange failed: {exc}") from exc

    status = "connected" if user_response.status_code < 400 else "error"
    last_error = None if status == "connected" else f"GitHub API returned HTTP {user_response.status_code}."
    await history_repository.upsert_github_connection(
        user.uid,
        token=access_token,
        enabled=status == "connected",
        status=status,
        last_error=last_error,
    )
    if status != "connected":
        raise HTTPException(status_code=400, detail=last_error or "GitHub OAuth succeeded but API check failed.")
    return {"status": "connected"}


@router.delete("/api/v1/auth/github")
async def disconnect_github(user: AuthenticatedUser = Depends(require_current_user)):
    """Remove the GitHub connection for the current user."""
    await history_repository.delete_integration_connection(user.uid, "github")
    return {"status": "disconnected"}


@router.get("/api/v1/auth/slack/url")
async def get_slack_auth_url(user: AuthenticatedUser = Depends(require_current_user)):
    """Return a Slack OAuth URL the frontend should open in a popup."""
    if not slack_oauth_configured():
        raise HTTPException(status_code=501, detail="Slack OAuth not configured.")
    code_verifier = secrets.token_urlsafe(72)[:96]
    from datetime import timedelta

    state_payload = {
        "uid": user.uid,
        "purpose": SLACK_OAUTH_PURPOSE,
        "cv": code_verifier,
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
    }
    state = pyjwt.encode(state_payload, settings.jwt_secret, algorithm="HS256")
    return {"auth_url": build_slack_authorization_url(state=state, code_verifier=code_verifier)}


@router.post("/api/v1/auth/slack/exchange")
async def exchange_slack_code(
    body: dict[str, Any],
    user: AuthenticatedUser = Depends(require_current_user),
):
    """Exchange a Slack authorization code, discover MCP tools, and store the connection."""
    if not slack_oauth_configured():
        raise HTTPException(status_code=501, detail="Slack OAuth not configured.")
    code = body.get("code", "")
    state = body.get("state", "")
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")
    try:
        state_data = pyjwt.decode(state, settings.jwt_secret, algorithms=["HS256"])
        if state_data.get("uid") != user.uid or state_data.get("purpose") != SLACK_OAUTH_PURPOSE:
            raise ValueError("state mismatch")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    code_verifier = state_data.get("cv")
    if not isinstance(code_verifier, str) or not code_verifier:
        raise HTTPException(status_code=400, detail="Invalid OAuth code verifier")

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            token_payload = await exchange_slack_authorization_code(
                client,
                code=str(code),
                code_verifier=code_verifier,
            )
    except SlackOAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {exc}") from exc

    access_token = slack_user_token(token_payload)
    test = await McpRemoteClient(url=SLACK_MCP_URL, bearer_token=access_token).discover()
    status = "connected" if test.ok else "error"
    await persist_slack_tokens(
        user.uid,
        token_payload,
        tools=discovered_tools_payload(test.tools),
        resources=test.resources,
        status=status,
        last_error=test.error or None,
        latency_ms=test.latency_ms,
        enabled=test.ok,
    )
    if not test.ok:
        raise HTTPException(
            status_code=400,
            detail=test.error or "Connected to Slack but MCP tool discovery failed.",
        )
    return {"status": "connected"}


@router.delete("/api/v1/auth/slack")
async def disconnect_slack(user: AuthenticatedUser = Depends(require_current_user)):
    """Remove the Slack connection for the current user."""
    await history_repository.delete_integration_connection(user.uid, SLACK_CONNECTION_ID)
    return {"status": "disconnected"}


@router.get("/api/v1/auth/{provider}/url")
async def get_mcp_oauth_url(provider: str, user: AuthenticatedUser = Depends(require_current_user)):
    """Return a remote-MCP OAuth URL for a first-class DCR provider."""
    spec = mcp_spec(provider)
    if spec is None:
        raise HTTPException(status_code=404, detail="Unknown OAuth provider")
    redirect_uri = mcp_redirect_uri(spec)
    code_verifier = secrets.token_urlsafe(72)[:96]
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            metadata = await discover_mcp_authorization_server(client, spec)
            registered = await register_mcp_oauth_client(client, spec, metadata, redirect_uri)
    except McpOAuthError as exc:
        logger.error("%s OAuth setup failed: %s", spec.name, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        logger.error("%s OAuth discovery HTTP error: %s", spec.name, exc)
        raise HTTPException(status_code=502, detail=f"Could not reach {spec.name} OAuth: {exc}") from exc

    client_id = str(registered.get("client_id") or "")
    if not client_id:
        raise HTTPException(
            status_code=502,
            detail=f"{spec.name} OAuth registration returned no client_id.",
        )

    from datetime import timedelta

    state_payload = {
        "uid": user.uid,
        "purpose": spec.oauth_purpose,
        "cv": code_verifier,
        "cid": client_id,
        "cs": str(registered.get("client_secret") or ""),
        "te": str(metadata.get("token_endpoint") or ""),
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
    }
    state = pyjwt.encode(state_payload, settings.jwt_secret, algorithm="HS256")
    auth_url = build_mcp_authorization_url(
        spec,
        metadata=metadata,
        client_id=client_id,
        redirect_uri=redirect_uri,
        state=state,
        code_verifier=code_verifier,
    )
    return {"auth_url": auth_url}


@router.post("/api/v1/auth/{provider}/exchange")
async def exchange_mcp_oauth_code(
    provider: str,
    body: dict[str, Any],
    user: AuthenticatedUser = Depends(require_current_user),
):
    """Exchange a remote-MCP authorization code, discover tools, and store the connection."""
    spec = mcp_spec(provider)
    if spec is None:
        raise HTTPException(status_code=404, detail="Unknown OAuth provider")
    code = body.get("code", "")
    state = body.get("state", "")
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")

    try:
        state_data = pyjwt.decode(state, settings.jwt_secret, algorithms=["HS256"])
        if state_data.get("uid") != user.uid or state_data.get("purpose") != spec.oauth_purpose:
            raise ValueError("state mismatch")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    code_verifier = state_data.get("cv")
    client_id = state_data.get("cid")
    token_endpoint = state_data.get("te")
    if not isinstance(code_verifier, str) or not code_verifier:
        raise HTTPException(status_code=400, detail="Invalid OAuth code verifier")
    if not isinstance(client_id, str) or not client_id:
        raise HTTPException(status_code=400, detail="Invalid OAuth client id")
    if not isinstance(token_endpoint, str) or not token_endpoint:
        raise HTTPException(status_code=400, detail="Invalid OAuth token endpoint")
    client_secret = state_data.get("cs") if isinstance(state_data.get("cs"), str) else ""

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            token_payload = await exchange_mcp_authorization_code(
                client,
                spec,
                token_endpoint=token_endpoint,
                code=str(code),
                redirect_uri=mcp_redirect_uri(spec),
                code_verifier=code_verifier,
                client_id=client_id,
                client_secret=client_secret,
            )
    except McpOAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {exc}") from exc

    access_token = str(token_payload.get("access_token") or "")
    test = await McpRemoteClient(url=spec.mcp_url, bearer_token=access_token).discover()
    status = "connected" if test.ok else "error"
    await persist_mcp_oauth_tokens(
        spec,
        user.uid,
        token_payload,
        client_id=client_id,
        client_secret=client_secret,
        token_endpoint=token_endpoint,
        tools=discovered_tools_payload(test.tools),
        resources=test.resources,
        status=status,
        last_error=test.error or None,
        latency_ms=test.latency_ms,
        enabled=test.ok,
    )
    if not test.ok:
        raise HTTPException(
            status_code=400,
            detail=test.error or f"Connected to {spec.name} but MCP tool discovery failed.",
        )
    return {"status": "connected"}


@router.delete("/api/v1/auth/{provider}")
async def disconnect_mcp_oauth(provider: str, user: AuthenticatedUser = Depends(require_current_user)):
    """Remove a first-class remote-MCP OAuth connection."""
    spec = mcp_spec(provider)
    if spec is None:
        raise HTTPException(status_code=404, detail="Unknown OAuth provider")
    await history_repository.delete_integration_connection(user.uid, spec.connection_id)
    return {"status": "disconnected"}
