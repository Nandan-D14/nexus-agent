# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexus.auth import AuthenticatedUser
from nexus.history_models import StoredIntegrationConnection
from nexus.mcp_client import build_mcp_adk_tools
from nexus.routers.integrations import get_integrations_catalog
from nexus.treg_oauth import (
    TREG_MCP_ORIGIN,
    TREG_SCOPES,
    build_treg_authorization_url,
    discover_treg_authorization_server,
    exchange_treg_authorization_code,
    register_treg_oauth_client,
    treg_redirect_uri,
)


@pytest.mark.asyncio
async def test_discover_treg_authorization_server() -> None:
    async def fake_get(url: str, **kwargs):
        del kwargs
        response = MagicMock()
        response.status_code = 200
        if url.endswith("oauth-protected-resource") or url.endswith("oauth-protected-resource/mcp"):
            response.json.return_value = {
                "resource": TREG_MCP_ORIGIN,
                "authorization_servers": ["https://treg.to"],
            }
        elif url.endswith("oauth-authorization-server"):
            response.json.return_value = {
                "authorization_endpoint": "https://treg.to/oauth/authorize",
                "token_endpoint": "https://treg.to/oauth/token",
                "registration_endpoint": "https://treg.to/oauth/register",
                "scopes_supported": ["treg:catalog", "treg:call", "treg:read"],
                "token_endpoint_auth_methods_supported": ["none"],
            }
        else:
            response.status_code = 404
            response.json.return_value = {}
        return response

    client = MagicMock()
    client.get = AsyncMock(side_effect=fake_get)
    metadata = await discover_treg_authorization_server(client)
    assert metadata["authorization_endpoint"] == "https://treg.to/oauth/authorize"
    assert metadata["token_endpoint"] == "https://treg.to/oauth/token"
    assert metadata["registration_endpoint"] == "https://treg.to/oauth/register"


@pytest.mark.asyncio
async def test_register_treg_oauth_client_prefers_public_client() -> None:
    response = MagicMock()
    response.status_code = 201
    response.json.return_value = {"client_id": "cid-treg"}
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    registered = await register_treg_oauth_client(
        client,
        {"registration_endpoint": "https://treg.to/oauth/register"},
        "https://app.example/auth/treg/callback",
    )
    assert registered["client_id"] == "cid-treg"
    assert client.post.await_args.kwargs["json"]["token_endpoint_auth_method"] == "none"


def test_build_treg_authorization_url_includes_pkce_resource_and_scopes() -> None:
    url = build_treg_authorization_url(
        metadata={
            "authorization_endpoint": "https://treg.to/oauth/authorize",
            "scopes_supported": TREG_SCOPES.split(),
        },
        client_id="cid-1",
        redirect_uri="https://app.example/auth/treg/callback",
        state="state-token",
        code_verifier="verifier",
    )
    assert url.startswith("https://treg.to/oauth/authorize?")
    assert "client_id=cid-1" in url
    assert "code_challenge_method=S256" in url
    assert "resource=" in url
    assert "treg%3Acatalog" in url or "treg:catalog" in url


@pytest.mark.asyncio
async def test_exchange_treg_authorization_code() -> None:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"access_token": "tok", "refresh_token": "ref", "expires_in": 3600}
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    payload = await exchange_treg_authorization_code(
        client,
        token_endpoint="https://treg.to/oauth/token",
        code="abc",
        redirect_uri="https://app.example/auth/treg/callback",
        code_verifier="verifier",
        client_id="cid-1",
    )
    assert payload["access_token"] == "tok"


def test_treg_redirect_uri_uses_frontend_url() -> None:
    uri = treg_redirect_uri()
    assert uri.endswith("/auth/treg/callback")


def test_treg_auth_routes_are_mounted() -> None:
    from nexus.routers.auth import router

    paths = {getattr(route, "path", "") for route in router.routes}
    assert "/api/v1/auth/treg/url" in paths
    assert "/api/v1/auth/treg/exchange" in paths
    assert "/api/v1/auth/treg" in paths


@pytest.mark.asyncio
async def test_catalog_includes_treg() -> None:
    repo = MagicMock()
    repo.get_user_settings = AsyncMock(return_value={})
    repo.get_integration_connection = AsyncMock(return_value=None)
    user = AuthenticatedUser(uid="user-1")
    with patch("nexus.routers.integrations.history_repository", repo):
        result = await get_integrations_catalog(user)
    providers = [item["provider"] for item in result["catalog"]]
    assert "treg" in providers
    treg = next(item for item in result["catalog"] if item["provider"] == "treg")
    assert treg["name"] == "Treg"
    assert treg["status"] == "available"
    assert treg["connector_type"] == "mcp_remote_http"


def test_build_mcp_adk_tools_names_treg_tools() -> None:
    connection = StoredIntegrationConnection(
        connection_id="treg",
        owner_id="user_1",
        connector_type="mcp_remote_http",
        provider="treg",
        name="Treg",
        enabled=True,
        status="connected",
        public={},
        private={
            "url": "https://treg.to/mcp/",
            "bearerToken": "secret-token",
            "authType": "oauth",
            "tools": [
                {
                    "name": "catalog_search",
                    "description": "Search the catalog.",
                    "input_schema": {"type": "object"},
                }
            ],
        },
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    tools = build_mcp_adk_tools([connection])
    assert len(tools) == 1
    assert tools[0].__name__ == "mcp__treg__catalog_search"
    assert getattr(tools[0], "_connection_id") == "treg"
