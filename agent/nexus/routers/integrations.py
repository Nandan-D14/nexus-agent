# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Integrations endpoints."""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException

from nexus.auth import AuthenticatedUser, require_current_user
from nexus.config import settings
from nexus.dependencies import get_history_repository
from nexus.models import (
    CreateMcpConnectionRequest,
    IntegrationCatalogItem,
    IntegrationConnection,
    StatusMessage,
    UpdateIntegrationConnectionRequest,
    UpsertGithubConnectionRequest,
    UpsertTavilyConnectionRequest,
    UpsertTinyfishConnectionRequest,
)
from nexus.mcp_client import McpRemoteClient, discovered_tools_payload, slugify_tool_part

router = APIRouter()
history_repository = get_history_repository()

def _serialize_integration_connection(connection) -> IntegrationConnection:
    public = connection.public or {}
    raw_tools = public.get("tools") if isinstance(public.get("tools"), list) else []
    raw_resources = public.get("resources") if isinstance(public.get("resources"), list) else []
    return IntegrationConnection(
        connection_id=connection.connection_id,
        connector_type=connection.connector_type,
        provider=connection.provider,
        name=connection.name,
        enabled=connection.enabled,
        status=connection.status,
        tools=[
            {
                "name": str(tool.get("name", "")),
                "description": str(tool.get("description", "") or ""),
                "input_schema": (
                    tool.get("input_schema")
                    if isinstance(tool.get("input_schema"), dict)
                    else tool.get("inputSchema")
                    if isinstance(tool.get("inputSchema"), dict)
                    else {}
                ),
            }
            for tool in raw_tools
            if isinstance(tool, dict) and tool.get("name")
        ],
        resources=[resource for resource in raw_resources if isinstance(resource, dict)],
        tool_count=int(public.get("toolCount", len(raw_tools)) or 0),
        last_checked_at=connection.last_checked_at,
        last_error=connection.last_error,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )

def _validate_remote_mcp_url(url: str) -> str:
    cleaned = (url or "").strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="MCP server URL must be an absolute http(s) URL.")
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and (settings.is_production or parsed.hostname not in local_hosts):
        raise HTTPException(status_code=400, detail="Remote MCP servers must use HTTPS.")
    return cleaned

@router.get("/api/v1/integrations/catalog")
async def get_integrations_catalog(user: AuthenticatedUser = Depends(require_current_user)):
    user_settings = await history_repository.get_user_settings(user.uid)
    google_drive_connection = await history_repository.get_integration_connection(user.uid, "google_drive")
    google_connected = bool((user_settings or {}).get("googleDriveRefreshToken")) or (
        bool(google_drive_connection)
        and google_drive_connection.status == "connected"
        and google_drive_connection.enabled
    )
    status = "connected" if google_connected else "needs_setup"
    
    return {
        "catalog": [
            IntegrationCatalogItem(
                provider="google_drive",
                connector_type="native",
                name="Google Drive",
                description="Search, read, create, and upload Drive files.",
                status=status,
            ).model_dump(mode="json"),
            IntegrationCatalogItem(
                provider="gmail",
                connector_type="native",
                name="Gmail",
                description="Search, read, and send emails.",
                status=status,
            ).model_dump(mode="json"),
            IntegrationCatalogItem(
                provider="google_calendar",
                connector_type="native",
                name="Google Calendar",
                description="List and create calendar events.",
                status=status,
            ).model_dump(mode="json"),
            IntegrationCatalogItem(
                provider="google_tasks",
                connector_type="native",
                name="Google Tasks",
                description="Manage your task lists and todo items.",
                status=status,
            ).model_dump(mode="json"),
            IntegrationCatalogItem(
                provider="github",
                connector_type="native",
                name="GitHub",
                description="Search repos, read files, list issues, create issues, and summarize PRs.",
                status="available",
            ).model_dump(mode="json"),
            IntegrationCatalogItem(
                provider="tavily",
                connector_type="native",
                name="Tavily",
                description="AI-powered web search with optimized results for agents.",
                status="available",
            ).model_dump(mode="json"),
            IntegrationCatalogItem(
                provider="tinyfish",
                connector_type="native",
                name="Tinyfish",
                description="Automate browser tasks on real websites using natural language goals.",
                status="available",
            ).model_dump(mode="json"),
            IntegrationCatalogItem(
                provider="mcp",
                connector_type="mcp_remote_http",
                name="Remote MCP Server",
                description="Connect any Streamable HTTP MCP server and expose its tools to the agent.",
                status="available",
            ).model_dump(mode="json"),
            IntegrationCatalogItem(
                provider="system",
                connector_type="system",
                name="Cloud Desktop Tools",
                description="Built-in Linux, browser, workspace, screen, and file tools.",
                status="connected",
            ).model_dump(mode="json"),
        ]
    }

@router.get("/api/v1/integrations/connections")
async def list_integration_connections(user: AuthenticatedUser = Depends(require_current_user)):
    user_settings = await history_repository.get_user_settings(user.uid)
    if (user_settings or {}).get("googleDriveRefreshToken"):
        await history_repository.upsert_google_connections(user.uid)
    connections = await history_repository.list_integration_connections(user.uid)
    return {
        "connections": [
            _serialize_integration_connection(connection).model_dump(mode="json")
            for connection in connections
        ]
    }

@router.post("/api/v1/integrations/mcp", response_model=IntegrationConnection)
async def create_mcp_connection(
    payload: CreateMcpConnectionRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    url = _validate_remote_mcp_url(payload.url)
    connection_id = f"mcp_{slugify_tool_part(payload.name, fallback='server')}_{uuid.uuid4().hex[:6]}"
    token = (payload.bearer_token or "").strip()
    test = await McpRemoteClient(url=url, bearer_token=token).discover()
    status = "connected" if test.ok else "error"
    connection = await history_repository.upsert_mcp_connection(
        user.uid,
        connection_id=connection_id,
        name=payload.name,
        url=url,
        bearer_token=token,
        enabled=payload.enabled and test.ok,
        tools=discovered_tools_payload(test.tools),
        resources=test.resources,
        status=status,
        last_error=test.error or None,
        latency_ms=test.latency_ms,
    )
    return _serialize_integration_connection(connection)

@router.post("/api/v1/integrations/mcp/{connection_id}/test", response_model=IntegrationConnection)
async def test_mcp_connection(
    connection_id: str,
    user: AuthenticatedUser = Depends(require_current_user),
):
    connection = await history_repository.get_integration_connection(user.uid, connection_id)
    if not connection or connection.provider != "mcp":
        raise HTTPException(status_code=404, detail="MCP connection not found")
    url = _validate_remote_mcp_url(str(connection.private.get("url") or ""))
    token = str(connection.private.get("bearerToken") or "")
    test = await McpRemoteClient(url=url, bearer_token=token).discover()
    updated = await history_repository.upsert_mcp_connection(
        user.uid,
        connection_id=connection_id,
        name=connection.name,
        url=url,
        bearer_token="",
        enabled=connection.enabled and test.ok,
        tools=discovered_tools_payload(test.tools),
        resources=test.resources,
        status="connected" if test.ok else "error",
        last_error=test.error or None,
        latency_ms=test.latency_ms,
    )
    return _serialize_integration_connection(updated)

@router.post("/api/v1/integrations/github", response_model=IntegrationConnection)
async def upsert_github_connection(
    payload: UpsertGithubConnectionRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    token = payload.token.strip()
    status = "connected"
    last_error = None
    try:
        async with httpx.AsyncClient(
            timeout=20.0,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        ) as client:
            response = await client.get("https://api.github.com/user")
            if response.status_code >= 400:
                status = "error"
                last_error = f"GitHub API returned HTTP {response.status_code}."
    except Exception as exc:
        status = "error"
        last_error = str(exc)[:500] or "GitHub token test failed."
    connection = await history_repository.upsert_github_connection(
        user.uid,
        token=token,
        enabled=payload.enabled and status == "connected",
        status=status,
        last_error=last_error,
    )
    return _serialize_integration_connection(connection)

@router.post("/api/v1/integrations/tavily", response_model=IntegrationConnection)
async def upsert_tavily_connection(
    payload: UpsertTavilyConnectionRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    api_key = payload.api_key.strip()
    status = "connected"
    last_error = None
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": "test",
                    "search_depth": "basic",
                    "max_results": 1,
                },
            )
            if response.status_code >= 400:
                status = "error"
                last_error = f"Tavily API returned HTTP {response.status_code}."
    except Exception as exc:
        status = "error"
        last_error = str(exc)[:500] or "Tavily API key test failed."
    connection = await history_repository.upsert_tavily_connection(
        user.uid,
        api_key=api_key,
        enabled=payload.enabled and status == "connected",
        status=status,
        last_error=last_error,
    )
    return _serialize_integration_connection(connection)

@router.post("/api/v1/integrations/tinyfish", response_model=IntegrationConnection)
async def upsert_tinyfish_connection(
    payload: UpsertTinyfishConnectionRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    api_key = payload.api_key.strip()
    status = "connected"
    last_error = None
    try:
        async with httpx.AsyncClient(
            timeout=20.0,
            headers={"X-API-Key": api_key},
        ) as client:
            response = await client.post(
                "https://agent.tinyfish.ai/v1/automation/run",
                json={
                    "url": "https://example.com",
                    "goal": "Extract the page title",
                },
            )
            if response.status_code >= 400:
                status = "error"
                last_error = f"Tinyfish API returned HTTP {response.status_code}."
    except Exception as exc:
        status = "error"
        last_error = str(exc)[:500] or "Tinyfish API key test failed."
    connection = await history_repository.upsert_tinyfish_connection(
        user.uid,
        api_key=api_key,
        enabled=payload.enabled and status == "connected",
        status=status,
        last_error=last_error,
    )
    return _serialize_integration_connection(connection)

@router.patch("/api/v1/integrations/{connection_id}", response_model=IntegrationConnection)
async def update_integration_connection(
    connection_id: str,
    payload: UpdateIntegrationConnectionRequest,
    user: AuthenticatedUser = Depends(require_current_user),
):
    updated = await history_repository.update_integration_connection(
        user.uid,
        connection_id,
        enabled=payload.enabled,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Integration connection not found")
    return _serialize_integration_connection(updated)

@router.delete("/api/v1/integrations/{connection_id}", response_model=StatusMessage)
async def delete_integration_connection(
    connection_id: str,
    user: AuthenticatedUser = Depends(require_current_user),
):
    deleted = await history_repository.delete_integration_connection(user.uid, connection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Integration connection not found")
    return StatusMessage(status="deleted")

@router.get("/api/v1/user/quota")
async def get_user_quota(user: AuthenticatedUser = Depends(require_current_user)):
    """Get the user's plan quota, with credit-first compatibility fields."""
    quota = await history_repository.get_user_quota(user.uid)
    return quota
