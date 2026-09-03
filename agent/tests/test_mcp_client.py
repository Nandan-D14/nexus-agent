# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from nexus.history_repository import StoredIntegrationConnection
from nexus.mcp_client import build_mcp_adk_tools, redact_sensitive


class McpClientToolTests(unittest.IsolatedAsyncioTestCase):
    def test_redact_sensitive_nested_values(self) -> None:
        payload = {
            "query": "select 1",
            "Authorization": "Bearer secret",
            "nested": {"api_key": "secret", "safe": "ok"},
        }

        self.assertEqual(
            redact_sensitive(payload),
            {
                "query": "select 1",
                "Authorization": "[redacted]",
                "nested": {"api_key": "[redacted]", "safe": "ok"},
            },
        )

    async def test_build_mcp_adk_tools_calls_remote_tool(self) -> None:
        connection = StoredIntegrationConnection(
            connection_id="mcp_demo",
            owner_id="user_1",
            connector_type="mcp_remote_http",
            provider="mcp",
            name="Demo Server",
            enabled=True,
            status="connected",
            public={},
            private={
                "url": "https://example.com/mcp",
                "bearerToken": "secret-token",
                "tools": [
                    {
                        "name": "query_database",
                        "description": "Query a database.",
                        "input_schema": {"type": "object"},
                    }
                ],
            },
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        tools = build_mcp_adk_tools([connection])

        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0].__name__, "mcp__demo_server__query_database")

        with patch(
            "nexus.mcp_client.McpRemoteClient.call_tool",
            new=AsyncMock(return_value={"status": "success", "text": "ok"}),
        ) as call_tool:
            result = await tools[0]({"sql": "select 1", "apiKey": "do-not-log"})

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["connection_id"], "mcp_demo")
        self.assertEqual(result["arguments"]["apiKey"], "[redacted]")
        call_tool.assert_awaited_once()

    async def test_build_mcp_adk_tools_passes_extra_headers(self) -> None:
        connection = StoredIntegrationConnection(
            connection_id="composio",
            owner_id="user_1",
            connector_type="mcp_remote_http",
            provider="composio",
            name="Composio",
            enabled=True,
            status="connected",
            public={},
            private={
                "url": "https://connect.composio.dev/mcp",
                "extraHeaders": {"x-consumer-api-key": "ck_test"},
                "tools": [
                    {
                        "name": "COMPOSIO_SEARCH_TOOLS",
                        "description": "Search Composio tools.",
                        "input_schema": {"type": "object"},
                    }
                ],
            },
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        tools = build_mcp_adk_tools([connection])
        self.assertEqual(len(tools), 1)

        with patch("nexus.mcp_client.McpRemoteClient") as client_cls:
            instance = client_cls.return_value
            instance.call_tool = AsyncMock(return_value={"status": "success", "text": "ok"})
            result = await tools[0]({"query": "gmail"})

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["connection_id"], "composio")
        client_cls.assert_called_once()
        self.assertEqual(client_cls.call_args.kwargs["url"], "https://connect.composio.dev/mcp")
        self.assertEqual(
            client_cls.call_args.kwargs["headers"],
            {"x-consumer-api-key": "ck_test"},
        )

