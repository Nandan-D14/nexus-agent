# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Treg MCP OAuth discovery, Dynamic Client Registration, and token refresh."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx

from nexus.config import settings
from nexus.exa_oauth import (
    _absolute_url,
    _as_list,
    _fetch_json,
    _parse_www_authenticate_metadata,
    access_token_needs_refresh,
    pkce_challenge,
    token_expires_at_from_payload,
)

logger = logging.getLogger(__name__)

TREG_CONNECTION_ID = "treg"
TREG_PROVIDER = "treg"
TREG_CONNECTOR_NAME = "Treg"
TREG_MCP_ORIGIN = "https://treg.to/mcp/"
TREG_MCP_URL = "https://treg.to/mcp/"
TREG_OAUTH_PURPOSE = "treg_oauth"
TREG_SCOPES = "treg:catalog treg:call treg:read"


class TregOAuthError(RuntimeError):
    """Raised when Treg MCP OAuth discovery or registration fails."""


def treg_redirect_uri() -> str:
    return f"{settings.frontend_url.rstrip('/')}/auth/treg/callback"


async def discover_treg_authorization_server(client: httpx.AsyncClient) -> dict[str, Any]:
    """Resolve Treg's OAuth authorization-server metadata (RFC 8414 / RFC 9728)."""
    as_candidates: list[str] = []
    for metadata_url in (
        "https://treg.to/.well-known/oauth-protected-resource",
        "https://treg.to/.well-known/oauth-protected-resource/mcp",
    ):
        payload = await _fetch_json(client, metadata_url)
        if not payload:
            continue
        as_candidates.extend(_as_list(payload.get("authorization_servers")))
        if as_candidates:
            break

    if not as_candidates:
        try:
            probe = await client.get(TREG_MCP_ORIGIN, headers={"Accept": "application/json"})
        except httpx.HTTPError:
            probe = None
        if probe is not None:
            metadata_url = _parse_www_authenticate_metadata(probe.headers.get("www-authenticate", ""))
            if metadata_url:
                payload = await _fetch_json(client, metadata_url)
                if payload:
                    as_candidates.extend(_as_list(payload.get("authorization_servers")))

    if not as_candidates:
        as_candidates = ["https://treg.to"]

    seen: set[str] = set()
    for issuer in as_candidates:
        issuer = issuer.rstrip("/")
        if issuer in seen:
            continue
        seen.add(issuer)
        parsed = urlparse(issuer)
        well_known_urls = [
            f"{issuer}/.well-known/oauth-authorization-server",
            f"{issuer}/.well-known/openid-configuration",
        ]
        if parsed.path and parsed.path != "/":
            well_known_urls.insert(
                0,
                f"{parsed.scheme}://{parsed.netloc}/.well-known/oauth-authorization-server{parsed.path}",
            )
        for well_known in well_known_urls:
            metadata = await _fetch_json(client, well_known)
            if not metadata:
                continue
            authorization_endpoint = str(metadata.get("authorization_endpoint") or "")
            token_endpoint = str(metadata.get("token_endpoint") or "")
            if authorization_endpoint and token_endpoint:
                metadata["authorization_endpoint"] = _absolute_url(issuer, authorization_endpoint)
                metadata["token_endpoint"] = _absolute_url(issuer, token_endpoint)
                registration = str(metadata.get("registration_endpoint") or "")
                if registration:
                    metadata["registration_endpoint"] = _absolute_url(issuer, registration)
                return metadata

    raise TregOAuthError("Could not discover Treg OAuth authorization server metadata.")


async def register_treg_oauth_client(
    client: httpx.AsyncClient,
    metadata: dict[str, Any],
    redirect_uri: str,
) -> dict[str, Any]:
    endpoint = str(metadata.get("registration_endpoint") or "").strip()
    if not endpoint:
        raise TregOAuthError(
            "Treg authorization server does not advertise Dynamic Client Registration."
        )

    # Treg advertises token_endpoint_auth_methods_supported: ["none"].
    payloads = [
        {
            "client_name": "CoComputer",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "application_type": "web",
        },
        {
            "client_name": "CoComputer",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_post",
            "application_type": "web",
        },
    ]
    last_error = ""
    for body in payloads:
        try:
            response = await client.post(endpoint, json=body)
        except httpx.HTTPError as exc:
            last_error = str(exc)[:500]
            continue
        if response.status_code >= 400:
            last_error = response.text[:500]
            continue
        try:
            registered = response.json()
        except ValueError:
            last_error = "Invalid client registration response."
            continue
        if isinstance(registered, dict) and registered.get("client_id"):
            return registered
        last_error = "Registration response missing client_id."

    raise TregOAuthError(f"Treg OAuth client registration failed: {last_error or 'unknown error'}")


def build_treg_authorization_url(
    *,
    metadata: dict[str, Any],
    client_id: str,
    redirect_uri: str,
    state: str,
    code_verifier: str,
    scope: str = "",
) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": pkce_challenge(code_verifier),
        "code_challenge_method": "S256",
        "resource": TREG_MCP_ORIGIN,
    }
    resolved_scope = (
        scope
        or " ".join(_as_list(metadata.get("scopes_supported")))
        or TREG_SCOPES
    )
    if resolved_scope:
        params["scope"] = resolved_scope
    return str(metadata["authorization_endpoint"]) + "?" + urlencode(params)


def _token_form(
    *,
    grant: dict[str, str],
    client_id: str,
    client_secret: str,
) -> dict[str, str]:
    data = {
        **grant,
        "client_id": client_id,
        "resource": TREG_MCP_ORIGIN,
    }
    if client_secret:
        data["client_secret"] = client_secret
    return data


async def exchange_treg_authorization_code(
    client: httpx.AsyncClient,
    *,
    token_endpoint: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    client_id: str,
    client_secret: str = "",
) -> dict[str, Any]:
    response = await client.post(
        token_endpoint,
        data=_token_form(
            grant={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
            client_id=client_id,
            client_secret=client_secret,
        ),
        headers={"Accept": "application/json"},
    )
    if response.status_code >= 400:
        raise TregOAuthError(f"Treg token exchange failed: {response.text[:500]}")
    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise TregOAuthError("Treg token exchange returned no access token.")
    return payload


async def refresh_treg_access_token_payload(
    client: httpx.AsyncClient,
    *,
    token_endpoint: str,
    refresh_token: str,
    client_id: str,
    client_secret: str = "",
) -> dict[str, Any]:
    response = await client.post(
        token_endpoint,
        data=_token_form(
            grant={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            client_id=client_id,
            client_secret=client_secret,
        ),
        headers={"Accept": "application/json"},
    )
    if response.status_code >= 400:
        raise TregOAuthError(f"Treg token refresh failed: {response.text[:500]}")
    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise TregOAuthError("Treg token refresh returned no access token.")
    return payload


async def persist_treg_tokens(
    uid: str,
    token_payload: dict[str, Any],
    *,
    client_id: str,
    client_secret: str,
    token_endpoint: str,
    tools: list[dict[str, Any]] | None = None,
    resources: list[dict[str, Any]] | None = None,
    status: str = "connected",
    last_error: str | None = None,
    latency_ms: int | None = None,
    enabled: bool = True,
) -> Any:
    from nexus.dependencies import get_history_repository

    repo = get_history_repository()
    existing = await repo.get_integration_connection(uid, TREG_CONNECTION_ID)
    existing_private = existing.private if existing else {}
    refresh_token = str(
        token_payload.get("refresh_token") or existing_private.get("refreshToken") or ""
    )
    return await repo.upsert_treg_connection(
        uid,
        url=TREG_MCP_URL,
        bearer_token=str(token_payload.get("access_token") or ""),
        refresh_token=refresh_token,
        token_expires_at=token_expires_at_from_payload(token_payload),
        oauth_client_id=client_id or str(existing_private.get("oauthClientId") or ""),
        oauth_client_secret=client_secret or str(existing_private.get("oauthClientSecret") or ""),
        oauth_token_endpoint=token_endpoint or str(existing_private.get("oauthTokenEndpoint") or ""),
        enabled=enabled,
        tools=tools,
        resources=resources,
        status=status,
        last_error=last_error,
        latency_ms=latency_ms,
    )


async def ensure_treg_access_token(uid: str, *, force: bool = False) -> str:
    """Return a valid Treg access token, refreshing when it is expired or missing."""
    from nexus.dependencies import get_history_repository

    repo = get_history_repository()
    connection = await repo.get_integration_connection(uid, TREG_CONNECTION_ID)
    if not connection:
        return ""
    private = connection.private or {}
    access_token = str(private.get("bearerToken") or "")
    if access_token and not force and not access_token_needs_refresh(private):
        return access_token
    refresh_token = str(private.get("refreshToken") or "")
    token_endpoint = str(private.get("oauthTokenEndpoint") or "")
    client_id = str(private.get("oauthClientId") or "")
    if not refresh_token or not token_endpoint or not client_id:
        return access_token
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            payload = await refresh_treg_access_token_payload(
                client,
                token_endpoint=token_endpoint,
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=str(private.get("oauthClientSecret") or ""),
            )
        updated = await persist_treg_tokens(
            uid,
            payload,
            client_id=client_id,
            client_secret=str(private.get("oauthClientSecret") or ""),
            token_endpoint=token_endpoint,
            tools=private.get("tools") if isinstance(private.get("tools"), list) else None,
            resources=private.get("resources") if isinstance(private.get("resources"), list) else None,
            status=connection.status,
            last_error=None,
            enabled=connection.enabled,
        )
        return str((updated.private or {}).get("bearerToken") or payload.get("access_token") or "")
    except Exception:
        logger.warning("Treg access token refresh failed for uid=%s", uid, exc_info=True)
        return access_token
