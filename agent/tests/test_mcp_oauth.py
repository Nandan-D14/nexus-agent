# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexus.auth import AuthenticatedUser
from nexus.mcp_oauth import (
    MCP_OAUTH_SPECS,
    build_mcp_authorization_url,
    discover_mcp_authorization_server,
    register_mcp_oauth_client,
)
from nexus.routers.integrations import get_integrations_catalog
from nexus.slack_oauth import slack_user_token
from nexus.tool_catalog import CONNECTOR_TOOLS


def test_mcp_oauth_specs_cover_planned_providers() -> None:
    assert set(MCP_OAUTH_SPECS) == {"linear", "vercel", "cloudflare", "apify"}
    assert MCP_OAUTH_SPECS["linear"].mcp_url == "https://mcp.linear.app/mcp"
    assert MCP_OAUTH_SPECS["vercel"].mcp_url == "https://mcp.vercel.com"
    assert MCP_OAUTH_SPECS["cloudflare"].mcp_url == "https://mcp.cloudflare.com/mcp"
    assert MCP_OAUTH_SPECS["apify"].mcp_url == "https://mcp.apify.com"


def test_build_mcp_authorization_url_includes_pkce_and_resource() -> None:
    spec = MCP_OAUTH_SPECS["linear"]
    url = build_mcp_authorization_url(
        spec,
        metadata={"authorization_endpoint": "https://auth.linear.app/authorize"},
        client_id="cid-1",
        redirect_uri="https://app.example/auth/linear/callback",
        state="state-token",
        code_verifier="verifier",
        scope="read",
    )
    assert url.startswith("https://auth.linear.app/authorize?")
    assert "client_id=cid-1" in url
    assert "code_challenge_method=S256" in url
    assert "resource=" in url
    assert "scope=read" in url


@pytest.mark.asyncio
async def test_discover_mcp_authorization_server() -> None:
    spec = MCP_OAUTH_SPECS["linear"]

    async def fake_get(url: str, **kwargs):
        del kwargs
        response = MagicMock()
        response.status_code = 200
        if url.endswith("oauth-protected-resource"):
            response.json.return_value = {"authorization_servers": ["https://auth.linear.app"]}
        elif url.endswith("oauth-authorization-server"):
            response.json.return_value = {
                "authorization_endpoint": "https://auth.linear.app/authorize",
                "token_endpoint": "https://auth.linear.app/token",
                "registration_endpoint": "https://auth.linear.app/register",
            }
        else:
            response.status_code = 404
            response.json.return_value = {}
        return response

    client = MagicMock()
    client.get = AsyncMock(side_effect=fake_get)
    metadata = await discover_mcp_authorization_server(client, spec)
    assert metadata["authorization_endpoint"] == "https://auth.linear.app/authorize"
    assert metadata["token_endpoint"] == "https://auth.linear.app/token"


@pytest.mark.asyncio
async def test_register_mcp_oauth_client() -> None:
    spec = MCP_OAUTH_SPECS["apify"]
    response = MagicMock()
    response.status_code = 201
    response.json.return_value = {"client_id": "cid-1", "client_secret": "secret"}
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    registered = await register_mcp_oauth_client(
        client,
        spec,
        {"registration_endpoint": "https://auth.apify.com/register"},
        "https://app.example/auth/apify/callback",
    )
    assert registered["client_id"] == "cid-1"


def test_slack_user_token_prefers_authed_user() -> None:
    payload = {
        "ok": True,
        "access_token": "xoxb-bot",
        "authed_user": {"access_token": "xoxp-user"},
    }
    assert slack_user_token(payload) == "xoxp-user"


@pytest.mark.asyncio
async def test_catalog_includes_new_connectors() -> None:
    repo = MagicMock()
    repo.get_user_settings = AsyncMock(return_value={})
    github = MagicMock()
    github.enabled = True
    github.status = "connected"
    repo.get_integration_connection = AsyncMock(side_effect=lambda uid, connection_id: github if connection_id == "github" else None)
    user = AuthenticatedUser(uid="user-1")
    with (
        patch("nexus.routers.integrations.history_repository", repo),
        patch("nexus.routers.integrations.slack_oauth_configured", return_value=False),
        patch("nexus.routers.integrations._github_auth_mode", return_value="token"),
    ):
        result = await get_integrations_catalog(user)
    providers = [item["provider"] for item in result["catalog"]]
    for provider in (
        "github",
        "linear",
        "vercel",
        "cloudflare",
        "apify",
        "slack",
        "vyora",
        "openai",
        "composio",
    ):
        assert provider in providers
    composio = next(item for item in result["catalog"] if item["provider"] == "composio")
    assert composio["connector_type"] == "mcp_remote_http"
    assert composio["name"] == "Composio"
    github_item = next(item for item in result["catalog"] if item["provider"] == "github")
    assert github_item["status"] == "connected"
    assert github_item["auth_mode"] == "token"
    slack = next(item for item in result["catalog"] if item["provider"] == "slack")
    assert slack["auth_mode"] == "token"
    linear = next(item for item in result["catalog"] if item["provider"] == "linear")
    assert linear["connector_type"] == "mcp_remote_http"
    assert linear["status"] == "available"


@pytest.mark.asyncio
async def test_catalog_slack_auth_mode_oauth_when_configured() -> None:
    repo = MagicMock()
    repo.get_user_settings = AsyncMock(return_value={})
    repo.get_integration_connection = AsyncMock(return_value=None)
    user = AuthenticatedUser(uid="user-1")
    with (
        patch("nexus.routers.integrations.history_repository", repo),
        patch("nexus.routers.integrations.slack_oauth_configured", return_value=True),
    ):
        result = await get_integrations_catalog(user)
    slack = next(item for item in result["catalog"] if item["provider"] == "slack")
    assert slack["auth_mode"] == "oauth"


def test_native_connector_tools_include_vyora_and_openai() -> None:
    assert "vyora_start_call" in CONNECTOR_TOOLS["vyora"]
    assert "openai_web_search" in CONNECTOR_TOOLS["openai"]
