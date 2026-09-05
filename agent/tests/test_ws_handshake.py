# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
from starlette.datastructures import Headers, QueryParams

sys.modules.setdefault(
    "redis",
    SimpleNamespace(Redis=object, from_url=lambda *args, **kwargs: None),
)

from nexus.routers.ws import (
    _negotiated_subprotocol,
    _offered_subprotocols,
    _reject_ws,
    _ticket_candidates,
)


def test_ticket_candidates_from_query_param():
    ws = MagicMock()
    ws.query_params = QueryParams("ticket=jwt-query-token")
    ws.headers = Headers()

    candidates = _ticket_candidates(ws)
    assert candidates == [("jwt-query-token", None)]


def test_ticket_candidates_from_subprotocol_header():
    ws = MagicMock()
    ws.query_params = QueryParams()
    ws.headers = Headers({"sec-websocket-protocol": "jwt-sub-1, jwt-sub-2"})

    candidates = _ticket_candidates(ws)
    assert candidates == [("jwt-sub-1", "jwt-sub-1"), ("jwt-sub-2", "jwt-sub-2")]


def test_ticket_candidates_supports_both_query_and_subprotocol():
    ws = MagicMock()
    ws.query_params = QueryParams("ticket=query-tok")
    ws.headers = Headers({"sec-websocket-protocol": "proto-tok"})

    candidates = _ticket_candidates(ws)
    assert candidates == [("query-tok", None), ("proto-tok", "proto-tok")]


def test_offered_subprotocols_parses_header():
    ws = MagicMock()
    ws.headers = Headers({"sec-websocket-protocol": " jwt-a , jwt-b "})
    assert _offered_subprotocols(ws) == ["jwt-a", "jwt-b"]


def test_negotiated_subprotocol_echoes_offer_when_query_ticket_authenticated():
    ws = MagicMock()
    ws.headers = Headers({"sec-websocket-protocol": "client-jwt-proto"})
    # Query-string auth leaves accepted=None; the browser still sent a protocol.
    assert _negotiated_subprotocol(ws, None) == "client-jwt-proto"


def test_negotiated_subprotocol_prefers_accepted_header_ticket():
    ws = MagicMock()
    ws.headers = Headers({"sec-websocket-protocol": "ignored, ticket-from-header"})
    assert _negotiated_subprotocol(ws, "ticket-from-header") == "ticket-from-header"


def test_negotiated_subprotocol_none_without_offer():
    ws = MagicMock()
    ws.headers = Headers()
    assert _negotiated_subprotocol(ws, None) is None


@pytest.mark.asyncio
async def test_reject_ws_negotiates_subprotocol_header():
    ws = MagicMock()
    ws.headers = Headers({"sec-websocket-protocol": "client-jwt-proto"})
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()

    await _reject_ws(
        ws,
        code=4001,
        reason="WS_AUTH_FAILED",
        message="Invalid session ticket",
    )

    ws.accept.assert_awaited_once_with(subprotocol="client-jwt-proto")
    ws.send_json.assert_awaited_once_with({
        "type": "error",
        "code": "WS_AUTH_FAILED",
        "message": "Invalid session ticket",
    })
    ws.close.assert_awaited_once_with(code=4001, reason="Invalid session ticket")


@pytest.mark.asyncio
async def test_reject_ws_with_explicit_subprotocol():
    ws = MagicMock()
    ws.headers = Headers({"sec-websocket-protocol": "sub1, sub2"})
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()

    await _reject_ws(
        ws,
        code=4429,
        reason="WS_RATE_LIMITED",
        message="Rate limited",
        subprotocol="sub2",
    )

    ws.accept.assert_awaited_once_with(subprotocol="sub2")
    ws.send_json.assert_awaited_once_with({
        "type": "error",
        "code": "WS_RATE_LIMITED",
        "message": "Rate limited",
    })
    ws.close.assert_awaited_once_with(code=4429, reason="Rate limited")
