# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Exa MCP OAuth discovery, Dynamic Client Registration, and token refresh."""

from __future__ import annotations

import base64
import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

import httpx

from nexus.config import settings

logger = logging.getLogger(__name__)

EXA_CONNECTION_ID = "exa"
EXA_PROVIDER = "exa"
EXA_CONNECTOR_NAME = "Exa"
EXA_MCP_ORIGIN = "https://mcp.exa.ai/mcp"
EXA_MCP_URL = (
    "https://mcp.exa.ai/mcp"
    "?tools=web_search_exa,web_fetch_exa,web_search_advanced_exa,agent_run"
)
EXA_OAUTH_PURPOSE = "exa_oauth"
_TOKEN_REFRESH_SKEW = timedelta(seconds=60)
_WWW_METADATA_RE = re.compile(r'resource_metadata="([^"]+)"', re.I)


class ExaOAuthError(RuntimeError):
    """Raised when Exa MCP OAuth discovery or registration fails."""


def exa_redirect_uri() -> str:
    return f"{settings.frontend_url.rstrip('/')}/auth/exa/callback"


def pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def token_expires_at_from_payload(payload: dict[str, Any]) -> str | None:
    expires_in = payload.get("expires_in")
    if isinstance(expires_in, bool) or not isinstance(expires_in, (int, float)):
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))).isoformat()


def access_token_needs_refresh(private: dict[str, Any]) -> bool:
    raw = private.get("tokenExpiresAt")
    if not isinstance(raw, str) or not raw.strip():
        return False
    try:
        expires_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) + _TOKEN_REFRESH_SKEW >= expires_at


def _absolute_url(base: str, maybe_relative: str) -> str:
    cleaned = (maybe_relative or "").strip()
    if not cleaned:
        return ""
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        return cleaned
    return urljoin(base.rstrip("/") + "/", cleaned.lstrip("/"))


def _parse_www_authenticate_metadata(header: str) -> str:
    match = _WWW_METADATA_RE.search(header or "")
    return match.group(1).strip() if match else ""


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


async def _fetch_json(client: httpx.AsyncClient, url: str) -> dict[str, Any] | None:
    try:
        response = await client.get(url)
    except httpx.HTTPError as exc:
        logger.info("Exa OAuth metadata fetch failed url=%s error=%s", url, type(exc).__name__)
        return None
    if response.status_code >= 400:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


async def discover_exa_authorization_server(client: httpx.AsyncClient) -> dict[str, Any]:
    """Resolve Exa's OAuth authorization-server metadata (RFC 8414 / RFC 9728)."""
    as_candidates: list[str] = []
    for metadata_url in (
        "https://mcp.exa.ai/.well-known/oauth-protected-resource",
        "https://mcp.exa.ai/.well-known/oauth-protected-resource/mcp",
    ):
        payload = await _fetch_json(client, metadata_url)
        if not payload:
            continue
        as_candidates.extend(_as_list(payload.get("authorization_servers")))
        if as_candidates:
            break

    if not as_candidates:
        try:
            probe = await client.get(EXA_MCP_ORIGIN, headers={"Accept": "application/json"})
        except httpx.HTTPError:
            probe = None
        if probe is not None:
            metadata_url = _parse_www_authenticate_metadata(probe.headers.get("www-authenticate", ""))
            if metadata_url:
                payload = await _fetch_json(client, metadata_url)
                if payload:
                    as_candidates.extend(_as_list(payload.get("authorization_servers")))

    if not as_candidates:
        as_candidates = ["https://mcp.exa.ai"]

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

    raise ExaOAuthError("Could not discover Exa OAuth authorization server metadata.")


async def register_exa_oauth_client(
    client: httpx.AsyncClient,
    metadata: dict[str, Any],
    redirect_uri: str,
) -> dict[str, Any]:
    endpoint = str(metadata.get("registration_endpoint") or "").strip()
    if not endpoint:
        raise ExaOAuthError(
            "Exa authorization server does not advertise Dynamic Client Registration."
        )

    payloads = [
        {
            "client_name": "CoComputer",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_post",
            "application_type": "web",
        },
        {
            "client_name": "CoComputer",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
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

    raise ExaOAuthError(f"Exa OAuth client registration failed: {last_error or 'unknown error'}")


def build_exa_authorization_url(
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
        "resource": EXA_MCP_ORIGIN,
    }
    resolved_scope = scope or " ".join(_as_list(metadata.get("scopes_supported")))
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
        "resource": EXA_MCP_ORIGIN,
    }
    if client_secret:
        data["client_secret"] = client_secret
    return data


async def exchange_exa_authorization_code(
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
        raise ExaOAuthError(f"Exa token exchange failed: {response.text[:500]}")
    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise ExaOAuthError("Exa token exchange returned no access token.")
    return payload


async def refresh_exa_access_token_payload(
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
        raise ExaOAuthError(f"Exa token refresh failed: {response.text[:500]}")
    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise ExaOAuthError("Exa token refresh returned no access token.")
    return payload


def is_unauthorized_mcp_error(exc: BaseException) -> bool:
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if status_code == 401:
        return True
    text = str(exc).lower()
    return "401" in text or "unauthorized" in text


async def persist_exa_tokens(
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
    existing = await repo.get_integration_connection(uid, EXA_CONNECTION_ID)
    existing_private = existing.private if existing else {}
    refresh_token = str(
        token_payload.get("refresh_token") or existing_private.get("refreshToken") or ""
    )
    return await repo.upsert_exa_connection(
        uid,
        url=EXA_MCP_URL,
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


async def ensure_exa_access_token(uid: str, *, force: bool = False) -> str:
    """Return a valid Exa access token, refreshing when it is expired or missing."""
    from nexus.dependencies import get_history_repository

    repo = get_history_repository()
    connection = await repo.get_integration_connection(uid, EXA_CONNECTION_ID)
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
            payload = await refresh_exa_access_token_payload(
                client,
                token_endpoint=token_endpoint,
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=str(private.get("oauthClientSecret") or ""),
            )
        updated = await persist_exa_tokens(
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
        logger.warning("Exa access token refresh failed for uid=%s", uid, exc_info=True)
        return access_token
