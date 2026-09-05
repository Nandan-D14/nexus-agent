# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Slack registered-app OAuth for mcp.slack.com."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

import httpx

from nexus.config import settings
from nexus.exa_oauth import access_token_needs_refresh, pkce_challenge, token_expires_at_from_payload

logger = logging.getLogger(__name__)

SLACK_CONNECTION_ID = "slack"
SLACK_PROVIDER = "slack"
SLACK_CONNECTOR_NAME = "Slack"
SLACK_MCP_URL = "https://mcp.slack.com/mcp"
SLACK_OAUTH_PURPOSE = "slack_oauth"
SLACK_AUTHORIZE_URL = "https://slack.com/oauth/v2_user/authorize"
SLACK_TOKEN_URL = "https://slack.com/api/oauth.v2.user.access"
SLACK_REFRESH_URL = "https://slack.com/api/oauth.v2.access"
SLACK_USER_SCOPES = (
    "search:read.public,search:read.private,search:read.mpim,search:read.im,"
    "search:read.files,search:read.users,files:read,chat:write,"
    "channels:history,groups:history,mpim:history,im:history,"
    "channels:read,groups:read,mpim:read,users:read"
)


class SlackOAuthError(RuntimeError):
    """Raised when Slack OAuth fails."""


def slack_redirect_uri() -> str:
    return f"{settings.frontend_url.rstrip('/')}/auth/slack/callback"


def slack_oauth_configured() -> bool:
    return bool(settings.slack_client_id and settings.slack_client_secret)


def build_slack_authorization_url(*, state: str, code_verifier: str) -> str:
    params = {
        "client_id": settings.slack_client_id,
        "user_scope": SLACK_USER_SCOPES,
        "redirect_uri": slack_redirect_uri(),
        "state": state,
        "code_challenge": pkce_challenge(code_verifier),
        "code_challenge_method": "S256",
    }
    return f"{SLACK_AUTHORIZE_URL}?{urlencode(params)}"


def slack_user_token(payload: dict[str, Any]) -> str:
    authed_user = payload.get("authed_user")
    if isinstance(authed_user, dict):
        token = str(authed_user.get("access_token") or "")
        if token:
            return token
    return str(payload.get("access_token") or "")


def slack_refresh_token(payload: dict[str, Any], existing: str = "") -> str:
    authed_user = payload.get("authed_user")
    if isinstance(authed_user, dict):
        token = str(authed_user.get("refresh_token") or "")
        if token:
            return token
    return str(payload.get("refresh_token") or existing or "")


async def exchange_slack_authorization_code(
    client: httpx.AsyncClient,
    *,
    code: str,
    code_verifier: str,
) -> dict[str, Any]:
    response = await client.post(
        SLACK_TOKEN_URL,
        data={
            "client_id": settings.slack_client_id,
            "client_secret": settings.slack_client_secret,
            "code": code,
            "redirect_uri": slack_redirect_uri(),
            "code_verifier": code_verifier,
        },
        headers={"Accept": "application/json"},
    )
    if response.status_code >= 400:
        raise SlackOAuthError(f"Slack token exchange failed: {response.text[:500]}")
    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("ok"):
        error = payload.get("error") if isinstance(payload, dict) else "unknown"
        raise SlackOAuthError(f"Slack token exchange failed: {error}")
    if not slack_user_token(payload):
        raise SlackOAuthError("Slack token exchange returned no user access token.")
    return payload


async def persist_slack_tokens(
    uid: str,
    token_payload: dict[str, Any],
    *,
    tools: list[dict[str, Any]] | None = None,
    resources: list[dict[str, Any]] | None = None,
    status: str = "connected",
    last_error: str | None = None,
    latency_ms: int | None = None,
    enabled: bool = True,
) -> Any:
    from nexus.dependencies import get_history_repository

    repo = get_history_repository()
    existing = await repo.get_integration_connection(uid, SLACK_CONNECTION_ID)
    existing_private = existing.private if existing else {}
    access_token = slack_user_token(token_payload)
    refresh_token = slack_refresh_token(
        token_payload,
        str(existing_private.get("refreshToken") or ""),
    )
    authed_user = token_payload.get("authed_user") if isinstance(token_payload.get("authed_user"), dict) else {}
    expires_payload = authed_user if authed_user.get("expires_in") else token_payload
    return await repo.upsert_oauth_mcp_connection(
        uid,
        connection_id=SLACK_CONNECTION_ID,
        provider=SLACK_PROVIDER,
        name=SLACK_CONNECTOR_NAME,
        url=SLACK_MCP_URL,
        bearer_token=access_token,
        refresh_token=refresh_token,
        token_expires_at=token_expires_at_from_payload(expires_payload),
        oauth_client_id=settings.slack_client_id or str(existing_private.get("oauthClientId") or ""),
        oauth_client_secret=settings.slack_client_secret or str(existing_private.get("oauthClientSecret") or ""),
        oauth_token_endpoint=SLACK_REFRESH_URL,
        enabled=enabled,
        tools=tools,
        resources=resources,
        status=status,
        last_error=last_error,
        latency_ms=latency_ms,
    )


async def persist_slack_bearer_token(
    uid: str,
    access_token: str,
    *,
    tools: list[dict[str, Any]] | None = None,
    resources: list[dict[str, Any]] | None = None,
    status: str = "connected",
    last_error: str | None = None,
    latency_ms: int | None = None,
    enabled: bool = True,
) -> Any:
    """Store a pasted Slack user token for mcp.slack.com."""
    from nexus.dependencies import get_history_repository

    repo = get_history_repository()
    return await repo.upsert_oauth_mcp_connection(
        uid,
        connection_id=SLACK_CONNECTION_ID,
        provider=SLACK_PROVIDER,
        name=SLACK_CONNECTOR_NAME,
        url=SLACK_MCP_URL,
        bearer_token=access_token,
        refresh_token="",
        token_expires_at=None,
        oauth_client_id="",
        oauth_client_secret="",
        oauth_token_endpoint="",
        enabled=enabled,
        tools=tools,
        resources=resources,
        status=status,
        last_error=last_error,
        latency_ms=latency_ms,
    )


async def refresh_slack_access_token_payload(
    client: httpx.AsyncClient,
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> dict[str, Any]:
    """Refresh a Slack user token via oauth.v2.access, not the code-exchange URL."""
    response = await client.post(
        SLACK_REFRESH_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Accept": "application/json"},
    )
    if response.status_code >= 400:
        raise SlackOAuthError(f"Slack token refresh failed: {response.text[:500]}")
    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("ok"):
        error = payload.get("error") if isinstance(payload, dict) else "unknown"
        raise SlackOAuthError(f"Slack token refresh failed: {error}")
    if not slack_user_token(payload):
        raise SlackOAuthError("Slack token refresh returned no user access token.")
    return payload


async def ensure_slack_access_token(uid: str, *, force: bool = False) -> str:
    """Return a valid Slack user token, refreshing via oauth.v2.access when needed."""
    from nexus.dependencies import get_history_repository

    repo = get_history_repository()
    connection = await repo.get_integration_connection(uid, SLACK_CONNECTION_ID)
    if not connection:
        return ""
    private = connection.private or {}
    access_token = str(private.get("bearerToken") or "")
    if access_token and not force and not access_token_needs_refresh(private):
        return access_token
    refresh_token = str(private.get("refreshToken") or "")
    client_id = settings.slack_client_id or str(private.get("oauthClientId") or "")
    client_secret = settings.slack_client_secret or str(private.get("oauthClientSecret") or "")
    if not refresh_token or not client_id or not client_secret:
        return access_token
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            payload = await refresh_slack_access_token_payload(
                client,
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=client_secret,
            )
        updated = await persist_slack_tokens(
            uid,
            payload,
            tools=private.get("tools") if isinstance(private.get("tools"), list) else None,
            resources=private.get("resources") if isinstance(private.get("resources"), list) else None,
            status=connection.status,
            last_error=None,
            enabled=connection.enabled,
        )
        return str((updated.private or {}).get("bearerToken") or slack_user_token(payload) or "")
    except Exception:
        logger.warning("Slack access token refresh failed for uid=%s", uid, exc_info=True)
        return access_token
