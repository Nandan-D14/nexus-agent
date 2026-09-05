# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Shared remote-MCP OAuth 2.1 helpers (discovery, DCR, PKCE, token refresh)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx

from nexus.config import settings
from nexus.exa_oauth import (
    _absolute_url,
    _as_list,
    _parse_www_authenticate_metadata,
    access_token_needs_refresh,
    pkce_challenge,
    token_expires_at_from_payload,
)

logger = logging.getLogger(__name__)


class McpOAuthError(RuntimeError):
    """Raised when MCP OAuth discovery, registration, or token exchange fails."""


@dataclass(frozen=True)
class McpOAuthSpec:
    connection_id: str
    provider: str
    name: str
    mcp_url: str
    mcp_origin: str
    oauth_purpose: str
    callback_path: str
    scopes: str = ""
    resource_metadata_urls: tuple[str, ...] = ()
    fallback_issuer: str = ""


MCP_OAUTH_SPECS: dict[str, McpOAuthSpec] = {
    "linear": McpOAuthSpec(
        connection_id="linear",
        provider="linear",
        name="Linear",
        mcp_url="https://mcp.linear.app/mcp",
        mcp_origin="https://mcp.linear.app/mcp",
        oauth_purpose="linear_oauth",
        callback_path="/auth/linear/callback",
        resource_metadata_urls=(
            "https://mcp.linear.app/.well-known/oauth-protected-resource",
            "https://mcp.linear.app/.well-known/oauth-protected-resource/mcp",
        ),
        fallback_issuer="https://mcp.linear.app",
    ),
    "vercel": McpOAuthSpec(
        connection_id="vercel",
        provider="vercel",
        name="Vercel",
        mcp_url="https://mcp.vercel.com",
        mcp_origin="https://mcp.vercel.com",
        oauth_purpose="vercel_oauth",
        callback_path="/auth/vercel/callback",
        resource_metadata_urls=(
            "https://mcp.vercel.com/.well-known/oauth-protected-resource",
            "https://mcp.vercel.com/.well-known/oauth-protected-resource/mcp",
        ),
        fallback_issuer="https://mcp.vercel.com",
    ),
    "cloudflare": McpOAuthSpec(
        connection_id="cloudflare",
        provider="cloudflare",
        name="Cloudflare",
        mcp_url="https://mcp.cloudflare.com/mcp",
        mcp_origin="https://mcp.cloudflare.com/mcp",
        oauth_purpose="cloudflare_oauth",
        callback_path="/auth/cloudflare/callback",
        resource_metadata_urls=(
            "https://mcp.cloudflare.com/.well-known/oauth-protected-resource",
            "https://mcp.cloudflare.com/.well-known/oauth-protected-resource/mcp",
        ),
        fallback_issuer="https://mcp.cloudflare.com",
    ),
    "apify": McpOAuthSpec(
        connection_id="apify",
        provider="apify",
        name="Apify",
        mcp_url="https://mcp.apify.com",
        mcp_origin="https://mcp.apify.com",
        oauth_purpose="apify_oauth",
        callback_path="/auth/apify/callback",
        resource_metadata_urls=(
            "https://mcp.apify.com/.well-known/oauth-protected-resource",
            "https://mcp.apify.com/.well-known/oauth-protected-resource/mcp",
        ),
        fallback_issuer="https://mcp.apify.com",
    ),
}


def mcp_spec(provider: str) -> McpOAuthSpec | None:
    return MCP_OAUTH_SPECS.get(provider.strip().lower())


def mcp_redirect_uri(spec: McpOAuthSpec) -> str:
    path = spec.callback_path if spec.callback_path.startswith("/") else f"/{spec.callback_path}"
    return f"{settings.frontend_url.rstrip('/')}{path}"


async def _fetch_json(client: httpx.AsyncClient, url: str) -> dict[str, Any] | None:
    try:
        response = await client.get(url)
    except httpx.HTTPError as exc:
        logger.info("MCP OAuth metadata fetch failed url=%s error=%s", url, type(exc).__name__)
        return None
    if response.status_code >= 400:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _resource_metadata_urls(spec: McpOAuthSpec) -> list[str]:
    if spec.resource_metadata_urls:
        return list(spec.resource_metadata_urls)
    parsed = urlparse(spec.mcp_origin)
    base = f"{parsed.scheme}://{parsed.netloc}"
    origin = spec.mcp_origin.rstrip("/")
    return [
        f"{base}/.well-known/oauth-protected-resource",
        f"{base}/.well-known/oauth-protected-resource/mcp",
        f"{origin}/.well-known/oauth-protected-resource",
    ]


async def discover_mcp_authorization_server(
    client: httpx.AsyncClient,
    spec: McpOAuthSpec,
) -> dict[str, Any]:
    """Resolve OAuth authorization-server metadata (RFC 8414 / RFC 9728)."""
    as_candidates: list[str] = []
    for metadata_url in _resource_metadata_urls(spec):
        payload = await _fetch_json(client, metadata_url)
        if not payload:
            continue
        as_candidates.extend(_as_list(payload.get("authorization_servers")))
        if as_candidates:
            break

    if not as_candidates:
        try:
            probe = await client.get(spec.mcp_origin, headers={"Accept": "application/json"})
        except httpx.HTTPError:
            probe = None
        if probe is not None:
            metadata_url = _parse_www_authenticate_metadata(probe.headers.get("www-authenticate", ""))
            if metadata_url:
                payload = await _fetch_json(client, metadata_url)
                if payload:
                    as_candidates.extend(_as_list(payload.get("authorization_servers")))

    if not as_candidates:
        as_candidates = [spec.fallback_issuer or spec.mcp_origin]

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

    raise McpOAuthError(
        f"Could not discover {spec.name} OAuth authorization server metadata."
    )


async def register_mcp_oauth_client(
    client: httpx.AsyncClient,
    spec: McpOAuthSpec,
    metadata: dict[str, Any],
    redirect_uri: str,
) -> dict[str, Any]:
    endpoint = str(metadata.get("registration_endpoint") or "").strip()
    if not endpoint:
        raise McpOAuthError(
            f"{spec.name} authorization server does not advertise Dynamic Client Registration. "
            "If this vendor only allows approved MCP clients, use Remote MCP as an escape hatch."
        )

    advertised = [item.lower() for item in _as_list(metadata.get("token_endpoint_auth_methods_supported"))]
    methods: list[str] = []
    for method in advertised or ["client_secret_post", "none"]:
        if method not in methods:
            methods.append(method)
    for fallback in ("client_secret_post", "none"):
        if fallback not in methods:
            methods.append(fallback)

    last_error = ""
    for method in methods:
        body = {
            "client_name": "CoComputer",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": method,
            "application_type": "web",
        }
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

    raise McpOAuthError(
        f"{spec.name} OAuth client registration failed: {last_error or 'unknown error'}"
    )


def build_mcp_authorization_url(
    spec: McpOAuthSpec,
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
        "resource": spec.mcp_origin,
    }
    resolved_scope = scope or spec.scopes or " ".join(_as_list(metadata.get("scopes_supported")))
    if resolved_scope:
        params["scope"] = resolved_scope
    return str(metadata["authorization_endpoint"]) + "?" + urlencode(params)


def _token_form(
    *,
    grant: dict[str, str],
    client_id: str,
    client_secret: str,
    resource: str = "",
) -> dict[str, str]:
    data = {**grant, "client_id": client_id}
    if resource:
        data["resource"] = resource
    if client_secret:
        data["client_secret"] = client_secret
    return data


async def exchange_mcp_authorization_code(
    client: httpx.AsyncClient,
    spec: McpOAuthSpec,
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
            resource=spec.mcp_origin,
        ),
        headers={"Accept": "application/json"},
    )
    if response.status_code >= 400:
        raise McpOAuthError(f"{spec.name} token exchange failed: {response.text[:500]}")
    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise McpOAuthError(f"{spec.name} token exchange returned no access token.")
    return payload


async def refresh_mcp_access_token_payload(
    client: httpx.AsyncClient,
    *,
    token_endpoint: str,
    refresh_token: str,
    client_id: str,
    client_secret: str = "",
    resource: str = "",
    provider_name: str = "MCP",
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
            resource=resource,
        ),
        headers={"Accept": "application/json"},
    )
    if response.status_code >= 400:
        raise McpOAuthError(f"{provider_name} token refresh failed: {response.text[:500]}")
    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise McpOAuthError(f"{provider_name} token refresh returned no access token.")
    return payload


async def persist_mcp_oauth_tokens(
    spec: McpOAuthSpec,
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
    existing = await repo.get_integration_connection(uid, spec.connection_id)
    existing_private = existing.private if existing else {}
    refresh_token = str(
        token_payload.get("refresh_token") or existing_private.get("refreshToken") or ""
    )
    return await repo.upsert_oauth_mcp_connection(
        uid,
        connection_id=spec.connection_id,
        provider=spec.provider,
        name=spec.name,
        url=spec.mcp_url,
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


async def ensure_mcp_oauth_access_token(
    uid: str,
    connection_id: str,
    *,
    force: bool = False,
    resource: str = "",
) -> str:
    """Return a valid MCP access token, refreshing when expired or missing."""
    from nexus.dependencies import get_history_repository

    repo = get_history_repository()
    connection = await repo.get_integration_connection(uid, connection_id)
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
    spec = mcp_spec(connection_id)
    resolved_resource = resource or (spec.mcp_origin if spec else "")
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            payload = await refresh_mcp_access_token_payload(
                client,
                token_endpoint=token_endpoint,
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=str(private.get("oauthClientSecret") or ""),
                resource=resolved_resource,
                provider_name=spec.name if spec else connection.name or connection_id,
            )
        if spec:
            updated = await persist_mcp_oauth_tokens(
                spec,
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
        updated = await repo.upsert_oauth_mcp_connection(
            uid,
            connection_id=connection.connection_id,
            provider=connection.provider,
            name=connection.name,
            url=str(private.get("url") or ""),
            bearer_token=str(payload.get("access_token") or ""),
            refresh_token=str(payload.get("refresh_token") or refresh_token),
            token_expires_at=token_expires_at_from_payload(payload),
            oauth_client_id=client_id,
            oauth_client_secret=str(private.get("oauthClientSecret") or ""),
            oauth_token_endpoint=token_endpoint,
            enabled=connection.enabled,
            tools=private.get("tools") if isinstance(private.get("tools"), list) else None,
            resources=private.get("resources") if isinstance(private.get("resources"), list) else None,
            status=connection.status,
            last_error=None,
        )
        return str((updated.private or {}).get("bearerToken") or payload.get("access_token") or "")
    except Exception:
        logger.warning(
            "MCP access token refresh failed for uid=%s connection=%s",
            uid,
            connection_id,
            exc_info=True,
        )
        return access_token
