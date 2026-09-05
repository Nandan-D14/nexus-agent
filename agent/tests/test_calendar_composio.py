# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from nexus.auth import AuthenticatedUser
from nexus.composio_mcp import (
    COMPOSIO_CONNECTION_ID,
    COMPOSIO_MCP_URL,
    COMPOSIO_PROVIDER,
    COMPOSIO_UNAUTHORIZED_HINT,
    composio_extra_headers,
    mcp_error_is_unauthorized,
)
from nexus.google_services import CalendarClient
from nexus.mcp_client import McpTestResult
from nexus.models import UpsertComposioConnectionRequest
from nexus.routers.integrations import upsert_composio_connection

ROOT = Path(__file__).resolve().parents[2]
INTENT_TS = ROOT / "frontend" / "src" / "lib" / "scheduling-intent.ts"
CONNECTORS_TS = ROOT / "frontend" / "src" / "lib" / "connectors.ts"


def _ts_string_list(source: str, const_name: str) -> list[str]:
    match = re.search(rf"const {const_name} = \[([^\]]+)\]", source)
    assert match, f"{const_name} missing from connectors.ts"
    return re.findall(r'"([^"]+)"', match.group(1))


def _scheduling_re() -> re.Pattern[str]:
    text = INTENT_TS.read_text(encoding="utf-8")
    match = re.search(r"const SCHEDULING_RE =\s*/(.+)/i;", text)
    assert match, "SCHEDULING_RE missing from scheduling-intent.ts"
    return re.compile(match.group(1), re.I)


def looks_like_scheduling_prompt(text: str) -> bool:
    return bool(_scheduling_re().search(text.strip()))


def with_scheduling_connectors(
    text: str,
    selected_connector_ids: list[str],
    selected_tool_ids: list[str],
    available: list[dict[str, str]],
) -> list[str]:
    picker_restricted = bool(selected_connector_ids) or bool(selected_tool_ids)
    if not picker_restricted or not looks_like_scheduling_prompt(text):
        return selected_connector_ids
    extra = [
        item["connection_id"]
        for item in available
        if item["provider"] in {"google_calendar", "google_tasks"}
    ]
    if not extra:
        return selected_connector_ids
    merged: list[str] = []
    for value in [*selected_connector_ids, *extra]:
        if value not in merged:
            merged.append(value)
    return merged


@pytest.mark.asyncio
async def test_calendar_create_event_includes_timezone_and_attendees() -> None:
    client = CalendarClient("token")
    with patch.object(CalendarClient, "_request", new_callable=AsyncMock) as request:
        request.return_value = {"id": "evt-1"}
        result = await client.create_event(
            "Design Review",
            "2026-08-28T15:00:00",
            "2026-08-28T15:30:00",
            time_zone="America/New_York",
            attendees=["ada@example.com", "  ", "bob@example.com"],
        )

    assert result["id"] == "evt-1"
    body = request.await_args.kwargs["json_body"]
    assert body["start"]["timeZone"] == "America/New_York"
    assert body["end"]["timeZone"] == "America/New_York"
    assert body["attendees"] == [
        {"email": "ada@example.com"},
        {"email": "bob@example.com"},
    ]


@pytest.mark.asyncio
async def test_calendar_create_event_defaults_to_utc_without_attendees() -> None:
    client = CalendarClient("token")
    with patch.object(CalendarClient, "_request", new_callable=AsyncMock) as request:
        request.return_value = {"id": "evt-2"}
        await client.create_event("Standup", "2026-08-28T15:00:00", "2026-08-28T15:15:00")

    body = request.await_args.kwargs["json_body"]
    assert body["start"]["timeZone"] == "UTC"
    assert body["end"]["timeZone"] == "UTC"
    assert "attendees" not in body


def test_composio_extra_headers_and_unauthorized_hint() -> None:
    assert composio_extra_headers(None) == {}
    assert composio_extra_headers("  ") == {}
    assert composio_extra_headers(" ck_test ") == {"x-consumer-api-key": "ck_test"}
    assert mcp_error_is_unauthorized("HTTP 401 Unauthorized")
    assert mcp_error_is_unauthorized("upstream returned unauthorized")
    assert not mcp_error_is_unauthorized("timeout")
    assert "consumer API key" in COMPOSIO_UNAUTHORIZED_HINT


@pytest.mark.asyncio
async def test_composio_connect_sends_consumer_header_and_hints_on_401() -> None:
    repo = MagicMock()
    repo.upsert_mcp_connection = AsyncMock(return_value=MagicMock())
    user = AuthenticatedUser(uid="user-1")
    discover = AsyncMock(
        return_value=McpTestResult(ok=False, tools=[], resources=[], error="401 Unauthorized")
    )
    with (
        patch("nexus.routers.integrations.history_repository", repo),
        patch("nexus.routers.integrations.McpRemoteClient") as client_cls,
    ):
        client_cls.return_value.discover = discover
        with pytest.raises(HTTPException) as exc:
            await upsert_composio_connection(
                UpsertComposioConnectionRequest(consumer_api_key="ck_secret"),
                user,
            )

    assert client_cls.call_args.kwargs["url"] == COMPOSIO_MCP_URL
    assert client_cls.call_args.kwargs["headers"] == {"x-consumer-api-key": "ck_secret"}
    assert exc.value.status_code == 400
    assert exc.value.detail == COMPOSIO_UNAUTHORIZED_HINT
    upsert_kwargs = repo.upsert_mcp_connection.await_args.kwargs
    assert upsert_kwargs["connection_id"] == COMPOSIO_CONNECTION_ID
    assert upsert_kwargs["provider"] == COMPOSIO_PROVIDER
    assert upsert_kwargs["extra_headers"] == {"x-consumer-api-key": "ck_secret"}
    assert upsert_kwargs["url"] == COMPOSIO_MCP_URL


@pytest.mark.asyncio
async def test_composio_connect_url_only_when_discover_succeeds() -> None:
    stored = MagicMock()
    repo = MagicMock()
    repo.upsert_mcp_connection = AsyncMock(return_value=stored)
    user = AuthenticatedUser(uid="user-1")
    serialized = MagicMock()
    with (
        patch("nexus.routers.integrations.history_repository", repo),
        patch("nexus.routers.integrations.McpRemoteClient") as client_cls,
        patch(
            "nexus.routers.integrations._serialize_integration_connection",
            return_value=serialized,
        ),
    ):
        client_cls.return_value.discover = AsyncMock(
            return_value=McpTestResult(ok=True, tools=[], resources=[])
        )
        result = await upsert_composio_connection(
            UpsertComposioConnectionRequest(consumer_api_key=None),
            user,
        )

    assert result is serialized
    assert client_cls.call_args.kwargs["headers"] == {}
    upsert_kwargs = repo.upsert_mcp_connection.await_args.kwargs
    assert upsert_kwargs["enabled"] is True
    assert upsert_kwargs["status"] == "connected"


def test_featured_calendar_tasks_and_developer_composio() -> None:
    source = CONNECTORS_TS.read_text(encoding="utf-8")
    featured = _ts_string_list(source, "FEATURED_PROVIDERS")
    developer = _ts_string_list(source, "DEVELOPER_PROVIDERS")
    assert featured.index("google_calendar") < featured.index("google_tasks")
    assert "composio" in developer
    assert developer.index("composio") < developer.index("mcp")


def test_scheduling_intent_helper() -> None:
    prompt = "create a 30-minute event tomorrow 3pm titled Design Review"
    assert looks_like_scheduling_prompt(prompt)
    assert looks_like_scheduling_prompt("Add a Google Task: send the weekly digest")
    assert not looks_like_scheduling_prompt("summarize this PDF")

    available = [
        {"connection_id": "google_calendar", "provider": "google_calendar"},
        {"connection_id": "google_tasks", "provider": "google_tasks"},
    ]
    assert with_scheduling_connectors(prompt, [], [], available) == []
    assert with_scheduling_connectors(prompt, ["github"], [], available) == [
        "github",
        "google_calendar",
        "google_tasks",
    ]
    assert with_scheduling_connectors("summarize this PDF", ["github"], [], available) == [
        "github"
    ]
    assert with_scheduling_connectors(prompt, [], ["terminal"], available) == [
        "google_calendar",
        "google_tasks",
    ]
