# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from nexus.auth import AuthenticatedUser
from nexus.exa_oauth import (
    EXA_MCP_ORIGIN,
    access_token_needs_refresh,
    build_exa_authorization_url,
    discover_exa_authorization_server,
    exchange_exa_authorization_code,
    is_unauthorized_mcp_error,
    pkce_challenge,
    register_exa_oauth_client,
    token_expires_at_from_payload,
)
from nexus.history_models import StoredIntegrationConnection
from nexus.mcp_client import build_mcp_adk_tools
from nexus.routers.integrations import get_integrations_catalog


def test_pkce_challenge_is_s256() -> None:
    challenge = pkce_challenge("test-verifier")
    assert challenge
    assert "=" not in challenge


def test_token_expiry_helpers() -> None:
    payload = {"expires_in": 3600}
    expires_at = token_expires_at_from_payload(payload)
    assert expires_at is not None
    assert access_token_needs_refresh({"tokenExpiresAt": expires_at}) is False
    past = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    assert access_token_needs_refresh({"tokenExpiresAt": past}) is True


def test_is_unauthorized_mcp_error() -> None:
    response = MagicMock()
    response.status_code = 401
    exc = httpx.HTTPStatusError("unauthorized", request=MagicMock(), response=response)
    assert is_unauthorized_mcp_error(exc) is True
    assert is_unauthorized_mcp_error(RuntimeError("connection reset")) is False


@pytest.mark.asyncio
async def test_discover_exa_authorization_server() -> None:
    async def fake_get(url: str, **kwargs):
        del kwargs
        response = MagicMock()
        response.status_code = 200
        if url.endswith("oauth-protected-resource"):
            response.json.return_value = {
                "authorization_servers": ["https://auth.exa.ai"],
            }
        elif url.endswith("oauth-authorization-server"):
            response.json.return_value = {
                "authorization_endpoint": "https://auth.exa.ai/authorize",
                "token_endpoint": "https://auth.exa.ai/token",
                "registration_endpoint": "https://auth.exa.ai/register",
                "scopes_supported": ["mcp"],
            }
        else:
            response.status_code = 404
            response.json.return_value = {}
        return response

    client = MagicMock()
    client.get = AsyncMock(side_effect=fake_get)
    metadata = await discover_exa_authorization_server(client)
    assert metadata["authorization_endpoint"] == "https://auth.exa.ai/authorize"
    assert metadata["token_endpoint"] == "https://auth.exa.ai/token"
    assert metadata["registration_endpoint"] == "https://auth.exa.ai/register"


@pytest.mark.asyncio
async def test_register_exa_oauth_client() -> None:
    response = MagicMock()
    response.status_code = 201
    response.json.return_value = {"client_id": "cid-1", "client_secret": "secret"}
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    registered = await register_exa_oauth_client(
        client,
        {"registration_endpoint": "https://auth.exa.ai/register"},
        "https://app.example/auth/exa/callback",
    )
    assert registered["client_id"] == "cid-1"
    client.post.assert_awaited()


def test_build_exa_authorization_url_includes_pkce_and_resource() -> None:
    url = build_exa_authorization_url(
        metadata={"authorization_endpoint": "https://auth.exa.ai/authorize"},
        client_id="cid-1",
        redirect_uri="https://app.example/auth/exa/callback",
        state="state-token",
        code_verifier="verifier",
        scope="mcp",
    )
    assert url.startswith("https://auth.exa.ai/authorize?")
    assert "client_id=cid-1" in url
    assert "code_challenge_method=S256" in url
    assert f"resource={EXA_MCP_ORIGIN.replace(':', '%3A').replace('/', '%2F')}" in url or "resource=" in url


@pytest.mark.asyncio
async def test_exchange_exa_authorization_code() -> None:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"access_token": "tok", "refresh_token": "ref", "expires_in": 3600}
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    payload = await exchange_exa_authorization_code(
        client,
        token_endpoint="https://auth.exa.ai/token",
        code="abc",
        redirect_uri="https://app.example/auth/exa/callback",
        code_verifier="verifier",
        client_id="cid-1",
        client_secret="secret",
    )
    assert payload["access_token"] == "tok"


@pytest.mark.asyncio
async def test_catalog_includes_exa() -> None:
    repo = MagicMock()
    repo.get_user_settings = AsyncMock(return_value={})
    repo.get_integration_connection = AsyncMock(return_value=None)
    user = AuthenticatedUser(uid="user-1")
    with patch("nexus.routers.integrations.history_repository", repo):
        result = await get_integrations_catalog(user)
    providers = [item["provider"] for item in result["catalog"]]
    assert "exa" in providers
    exa = next(item for item in result["catalog"] if item["provider"] == "exa")
    assert exa["name"] == "Exa"
    assert exa["status"] == "available"
    assert exa["connector_type"] == "mcp_remote_http"


def test_build_mcp_adk_tools_names_exa_tools() -> None:
    connection = StoredIntegrationConnection(
        connection_id="exa",
        owner_id="user_1",
        connector_type="mcp_remote_http",
        provider="exa",
        name="Exa",
        enabled=True,
        status="connected",
        public={},
        private={
            "url": "https://mcp.exa.ai/mcp?tools=web_search_exa",
            "bearerToken": "secret-token",
            "authType": "oauth",
            "tools": [
                {
                    "name": "web_search_exa",
                    "description": "Search the web.",
                    "input_schema": {"type": "object"},
                }
            ],
        },
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    tools = build_mcp_adk_tools([connection])
    assert len(tools) == 1
    assert tools[0].__name__ == "mcp__exa__web_search_exa"
    assert getattr(tools[0], "_connection_id") == "exa"
