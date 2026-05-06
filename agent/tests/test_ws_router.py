# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import sys

import pytest

sys.modules.setdefault(
    "redis",
    SimpleNamespace(Redis=object, from_url=lambda *args, **kwargs: None),
)

from nexus.routers import ws as ws_router


class FakeWebSocket:
    def __init__(
        self,
        *,
        query_params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.query_params = query_params or {}
        self.headers = headers or {}
        self.close = AsyncMock()


@pytest.mark.asyncio
async def test_websocket_accepts_query_ticket_and_rehydrates_stored_session(monkeypatch) -> None:
    ws = FakeWebSocket(query_params={"ticket": "ticket-from-query"})
    dummy_session = SimpleNamespace(
        id="session-123",
        owner_id="firebase-uid",
        status="ended",
        runtime_config=None,
    )
    live_session = SimpleNamespace(
        id="session-123",
        owner_id="firebase-uid",
        status="ready",
        runtime_config=object(),
    )
    stored_session = SimpleNamespace(
        owner_id="firebase-uid",
        status="ended",
        created_at=datetime.now(timezone.utc),
        title="Stored session",
        task_id="task-123",
        artifact_count=3,
    )
    session_manager = SimpleNamespace(
        validate_ticket=lambda ticket: ("session-123", "firebase-uid"),
        get_session=AsyncMock(return_value=dummy_session),
        continue_session=AsyncMock(return_value=live_session),
    )
    history_repository = SimpleNamespace(
        get_user_settings=AsyncMock(return_value={}),
        get_session=AsyncMock(return_value=stored_session),
        get_workspace_state=AsyncMock(return_value={}),
    )
    handle_websocket = AsyncMock()

    monkeypatch.setattr(ws_router, "get_session_manager", lambda: session_manager)
    monkeypatch.setattr(ws_router, "get_ws_connect_limiter", lambda: SimpleNamespace(check=lambda uid: True))
    monkeypatch.setattr(ws_router, "get_history_repository", lambda: history_repository)
    monkeypatch.setattr(ws_router, "resolve_session_runtime_config", lambda settings: object())
    monkeypatch.setattr(ws_router, "handle_websocket", handle_websocket)

    await ws_router.websocket_endpoint(ws, "session-123")

    ws.close.assert_not_awaited()
    session_manager.continue_session.assert_awaited_once()
    handle_websocket.assert_awaited_once()
    assert handle_websocket.await_args.kwargs["session"] is live_session
    assert handle_websocket.await_args.kwargs["subprotocol"] is None


@pytest.mark.asyncio
async def test_websocket_accepts_ticket_subprotocol(monkeypatch) -> None:
    ws = FakeWebSocket(headers={"sec-websocket-protocol": "ignored, ticket-from-header"})
    live_session = SimpleNamespace(
        id="session-123",
        owner_id="firebase-uid",
        status="ready",
        runtime_config=object(),
    )

    def validate_ticket(ticket: str):
        if ticket == "ticket-from-header":
            return "session-123", "firebase-uid"
        return None, None

    session_manager = SimpleNamespace(
        validate_ticket=validate_ticket,
        get_session=AsyncMock(return_value=live_session),
    )
    history_repository = SimpleNamespace(get_user_settings=AsyncMock(return_value={}))
    handle_websocket = AsyncMock()

    monkeypatch.setattr(ws_router, "get_session_manager", lambda: session_manager)
    monkeypatch.setattr(ws_router, "get_ws_connect_limiter", lambda: SimpleNamespace(check=lambda uid: True))
    monkeypatch.setattr(ws_router, "get_history_repository", lambda: history_repository)
    monkeypatch.setattr(ws_router, "handle_websocket", handle_websocket)

    await ws_router.websocket_endpoint(ws, "session-123")

    ws.close.assert_not_awaited()
    handle_websocket.assert_awaited_once()
    assert handle_websocket.await_args.kwargs["session"] is live_session
    assert handle_websocket.await_args.kwargs["subprotocol"] == "ticket-from-header"
