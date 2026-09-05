# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Composio Connect MCP constants."""

from __future__ import annotations

COMPOSIO_CONNECTION_ID = "composio"
COMPOSIO_PROVIDER = "composio"
COMPOSIO_NAME = "Composio"
COMPOSIO_MCP_URL = "https://connect.composio.dev/mcp"
COMPOSIO_CONSUMER_HEADER = "x-consumer-api-key"
COMPOSIO_UNAUTHORIZED_HINT = (
    "Composio returned 401. Paste a consumer API key from connect.composio.dev "
    "(Settings → Sessions & API Key)."
)


def composio_extra_headers(consumer_api_key: str | None) -> dict[str, str]:
    key = (consumer_api_key or "").strip()
    if not key:
        return {}
    return {COMPOSIO_CONSUMER_HEADER: key}


def mcp_error_is_unauthorized(error: str) -> bool:
    text = (error or "").lower()
    return "401" in text or "unauthorized" in text
