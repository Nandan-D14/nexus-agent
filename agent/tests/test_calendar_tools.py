# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from nexus.auth import AuthenticatedUser
from nexus.google_services import CalendarClient, GoogleApiError, slim_calendar_event
from nexus.policy import evaluate_tool_policy
from nexus.routers.integrations import list_calendar_events
from nexus.tool_catalog import CONNECTOR_TOOLS
from nexus.tools.integrations import (
    calendar_delete,
    calendar_get,
    calendar_list,
    calendar_update,
)
from nexus.tools.parallel import is_parallelizable


def test_google_calendar_allowlist_covers_crud() -> None:
    assert CONNECTOR_TOOLS["google_calendar"] == frozenset(
        {
            "calendar_list",
            "calendar_get",
            "calendar_create",
            "calendar_update",
            "calendar_delete",
        }
    )
    assert is_parallelizable("calendar_list") is True
    assert is_parallelizable("calendar_get") is True
    assert is_parallelizable("calendar_update") is False
    assert is_parallelizable("calendar_delete") is False


def test_calendar_mutations_require_approval() -> None:
    for name in ("calendar_create", "calendar_update", "calendar_delete"):
        decision = evaluate_tool_policy(name, {"event_id": "evt-1"}, autonomy_mode="auto")
        assert decision.action == "require_approval", name


def test_slim_calendar_event_keeps_dashboard_fields() -> None:
    slim = slim_calendar_event(
        {
            "id": "evt-1",
            "summary": "Design Review",
            "htmlLink": "https://calendar.google.com/event?eid=1",
            "status": "confirmed",
            "start": {"dateTime": "2026-09-02T10:00:00+05:30"},
            "end": {"dateTime": "2026-09-02T10:30:00+05:30"},
            "description": "ignore me",
        }
    )
    assert slim == {
        "id": "evt-1",
        "summary": "Design Review",
        "start": "2026-09-02T10:00:00+05:30",
        "end": "2026-09-02T10:30:00+05:30",
        "htmlLink": "https://calendar.google.com/event?eid=1",
        "status": "confirmed",
    }


@pytest.mark.asyncio
async def test_calendar_list_forwards_time_bounds() -> None:
    with (
        patch(
            "nexus.tools.integrations.get_google_services_token_from_context",
            new=AsyncMock(return_value="token"),
        ),
        patch.object(CalendarClient, "_request", new_callable=AsyncMock) as request,
    ):
        request.return_value = {"items": [{"id": "evt-1"}]}
        result = await calendar_list(
            max_results=5,
            time_min="2026-09-01T00:00:00Z",
            time_max="2026-09-02T00:00:00Z",
        )

    assert result["status"] == "success"
    params = request.await_args.kwargs["params"]
    assert params["maxResults"] == 5
    assert params["timeMin"] == "2026-09-01T00:00:00Z"
    assert params["timeMax"] == "2026-09-02T00:00:00Z"


@pytest.mark.asyncio
async def test_calendar_get_update_delete_success() -> None:
    with (
        patch(
            "nexus.tools.integrations.get_google_services_token_from_context",
            new=AsyncMock(return_value="token"),
        ),
        patch.object(CalendarClient, "_request", new_callable=AsyncMock) as request,
    ):
        request.return_value = {"id": "evt-1", "summary": "Standup"}
        got = await calendar_get("evt-1")
        updated = await calendar_update("evt-1", summary="Standup moved", start_time="2026-09-02T10:00:00")
        request.return_value = {}
        deleted = await calendar_delete("evt-1")

    assert got["status"] == "success"
    assert updated["status"] == "success"
    assert deleted["status"] == "success"
    methods = [call.args[0] for call in request.await_args_list]
    assert methods == ["GET", "PATCH", "DELETE"]
    patch_body = request.await_args_list[1].kwargs["json_body"]
    assert patch_body["summary"] == "Standup moved"
    assert patch_body["start"]["dateTime"] == "2026-09-02T10:00:00"


@pytest.mark.asyncio
async def test_calendar_tools_require_google_token() -> None:
    with patch(
        "nexus.tools.integrations.get_google_services_token_from_context",
        new=AsyncMock(return_value=None),
    ):
        listed = await calendar_list()
        got = await calendar_get("evt-1")
        updated = await calendar_update("evt-1", summary="Nope")
        deleted = await calendar_delete("evt-1")

    for result in (listed, got, updated, deleted):
        assert result["status"] == "error"
        assert result["error_code"] == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_list_calendar_events_requires_google_token() -> None:
    user = AuthenticatedUser(uid="user-1")
    with patch(
        "nexus.routers.integrations.get_google_drive_access_token_for_user",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(HTTPException) as exc:
            await list_calendar_events(max_results=10, user=user)

    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_list_calendar_events_forwards_time_bounds() -> None:
    user = AuthenticatedUser(uid="user-1")
    client = AsyncMock()
    client.list_events = AsyncMock(return_value={"items": []})
    with (
        patch(
            "nexus.routers.integrations.get_google_drive_access_token_for_user",
            new=AsyncMock(return_value="token"),
        ),
        patch("nexus.routers.integrations.CalendarClient", return_value=client),
    ):
        result = await list_calendar_events(
            user=user,
            max_results=20,
            time_min="2026-09-01T00:00:00Z",
            time_max="2026-10-01T00:00:00Z",
        )

    client.list_events.assert_awaited_once()
    kwargs = client.list_events.await_args.kwargs
    assert kwargs["max_results"] == 20
    assert kwargs["time_min"] == "2026-09-01T00:00:00Z"
    assert kwargs["time_max"] == "2026-10-01T00:00:00Z"
    assert result["event_count"] == 0


@pytest.mark.asyncio
async def test_calendar_list_maps_missing_calendar_scope() -> None:
    with (
        patch(
            "nexus.tools.integrations.get_google_services_token_from_context",
            new=AsyncMock(return_value="token"),
        ),
        patch.object(
            CalendarClient,
            "_request",
            new=AsyncMock(
                side_effect=GoogleApiError(
                    "Google Calendar is missing permission. Disconnect Google in Connectors and reconnect.",
                    error_code="AUTH_REQUIRED",
                    status_code=403,
                )
            ),
        ),
    ):
        result = await calendar_list()

    assert result["status"] == "error"
    assert result["error_code"] == "AUTH_REQUIRED"
    assert "reconnect" in result["summary"].lower()
