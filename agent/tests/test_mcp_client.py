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

