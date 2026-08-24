# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Correlated runtime and MCP tracing tests."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from nexus.event_sink import prepare_correlated_event
from nexus.mcp_client import McpRemoteClient
from nexus.tools._context import set_send_json
from nexus.tracing import (
    TraceContext,
    new_trace_id,
    safe_origin,
    set_trace_context,
    trace_headers,
)


def test_durable_run_trace_id_is_stable_and_w3c_compatible() -> None:
    first = new_trace_id("run_123")
    second = new_trace_id("run_123")
    assert first == second
    assert len(first) == 32
    int(first, 16)


def test_trace_headers_include_run_and_step_correlation() -> None:
    context = TraceContext(
        trace_id="a" * 32,
        run_id="run_1",
        step_id="tool_1",
    )
    headers = trace_headers(context)
    assert headers["X-Nexus-Trace-Id"] == "a" * 32
    assert headers["X-Nexus-Run-Id"] == "run_1"
    assert headers["X-Nexus-Step-Id"] == "tool_1"
    assert headers["traceparent"].startswith(f"00-{'a' * 32}-")


def test_trace_event_redacts_sensitive_fields() -> None:
    context = TraceContext(trace_id="b" * 32, run_id="run_2")
    prepared = prepare_correlated_event(
        {
            "type": "agent_tool_call",
            "tool": "mcp_call",
            "args": {
                "query": "safe",
                "api_key": "do-not-store",
                "nested": {"Authorization": "Bearer private"},
            },
        },
        context,
    )
    assert prepared["trace_id"] == "b" * 32
    assert prepared["run_id"] == "run_2"
    assert prepared["args"]["query"] == "safe"
    assert prepared["args"]["api_key"] == "[redacted]"
    assert prepared["args"]["nested"]["Authorization"] == "[redacted]"


def test_safe_origin_drops_mcp_path_and_query() -> None:
    assert (
        safe_origin("https://mcp.example.test/private/path?token=secret")
        == "https://mcp.example.test"
    )


def test_mcp_client_propagates_trace_headers_without_exposing_token() -> None:
    set_trace_context(
        TraceContext(trace_id="c" * 32, run_id="run_3", step_id="tool_3")
    )
    client = McpRemoteClient(
        url="https://mcp.example.test",
        bearer_token="private",
    )
    headers = client._headers()
    assert headers["Authorization"] == "Bearer private"
    assert headers["X-Nexus-Trace-Id"] == "c" * 32
    assert headers["X-Nexus-Step-Id"] == "tool_3"


@pytest.mark.asyncio
async def test_mcp_http_hooks_emit_safe_request_and_response_events() -> None:
    events: list[dict] = []

    async def send_json(event: dict) -> None:
        events.append(event)

    set_trace_context(
        TraceContext(trace_id="d" * 32, run_id="run_4", step_id="mcp_4")
    )
    set_send_json(send_json)
    client = McpRemoteClient(url="https://mcp.example.test/private?token=secret")
    hooks = client._event_hooks(operation="call_tool", tool_name="lookup")
    request = httpx.Request("POST", client.url)
    await hooks["request"][0](request)
    response = httpx.Response(200, request=request)
    await hooks["response"][0](response)
    set_send_json(None)

    assert [event["type"] for event in events] == [
        "mcp_http_request",
        "mcp_http_response",
    ]
    assert all(event["trace_id"] == "d" * 32 for event in events)
    assert all(event["server"] == "https://mcp.example.test" for event in events)
    assert "secret" not in str(events)


@pytest.mark.asyncio
async def test_mcp_http_error_emits_safe_error_event(monkeypatch) -> None:
    events: list[dict] = []

    async def send_json(event: dict) -> None:
        events.append(event)

    set_trace_context(
        TraceContext(trace_id="e" * 32, run_id="run_5", step_id="mcp_5")
    )
    set_send_json(send_json)
    client = McpRemoteClient(url="https://mcp.example.test/private?token=secret")

    class BoomClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class BoomStream:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            raise ConnectionError("upstream refused")

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr("nexus.mcp_client.httpx.AsyncClient", BoomClient)
    monkeypatch.setattr("nexus.mcp_client.streamable_http_client", BoomStream)

    with pytest.raises(ConnectionError):
        await client.call_tool(tool_name="lookup", arguments={"q": "x"})

    set_send_json(None)
    assert events
    assert events[-1]["type"] == "mcp_http_error"
    assert events[-1]["trace_id"] == "e" * 32
    assert events[-1]["server"] == "https://mcp.example.test"
    assert "token=secret" not in str(events)
