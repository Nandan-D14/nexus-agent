# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexus.slack_oauth import (
    SLACK_REFRESH_URL,
    SLACK_TOKEN_URL,
    persist_slack_tokens,
    refresh_slack_access_token_payload,
    slack_refresh_token,
    slack_user_token,
)


def test_slack_user_token_prefers_authed_user_over_bot() -> None:
    payload = {
        "ok": True,
        "access_token": "xoxb-bot",
        "authed_user": {"access_token": "xoxp-user"},
    }
    assert slack_user_token(payload) == "xoxp-user"


def test_slack_refresh_token_prefers_authed_user() -> None:
    payload = {
        "ok": True,
        "refresh_token": "bot-refresh",
        "authed_user": {"access_token": "xoxp-user", "refresh_token": "user-refresh"},
    }
    assert slack_refresh_token(payload, existing="old") == "user-refresh"


def test_slack_refresh_token_falls_back_to_existing() -> None:
    payload = {"ok": True, "access_token": "xoxb-bot"}
    assert slack_refresh_token(payload, existing="kept-refresh") == "kept-refresh"


@pytest.mark.asyncio
async def test_refresh_slack_access_token_uses_oauth_v2_access() -> None:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "ok": True,
        "access_token": "xoxb-bot",
        "authed_user": {"access_token": "xoxp-new", "refresh_token": "refresh-new"},
    }
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    payload = await refresh_slack_access_token_payload(
        client,
        refresh_token="refresh-old",
        client_id="cid",
        client_secret="secret",
    )
    assert slack_user_token(payload) == "xoxp-new"
    assert slack_refresh_token(payload) == "refresh-new"
    posted_url = client.post.await_args.args[0]
    assert posted_url == SLACK_REFRESH_URL
    assert posted_url != SLACK_TOKEN_URL
    assert client.post.await_args.kwargs["data"]["grant_type"] == "refresh_token"
    assert client.post.await_args.kwargs["data"]["refresh_token"] == "refresh-old"


@pytest.mark.asyncio
async def test_persist_slack_tokens_stores_user_tokens_and_refresh_endpoint() -> None:
    repo = MagicMock()
    repo.get_integration_connection = AsyncMock(return_value=None)
    updated = MagicMock()
    repo.upsert_oauth_mcp_connection = AsyncMock(return_value=updated)
    payload = {
        "ok": True,
        "access_token": "xoxb-bot",
        "refresh_token": "bot-refresh",
        "authed_user": {
            "access_token": "xoxp-user",
            "refresh_token": "user-refresh",
            "expires_in": 43200,
        },
    }
    with patch("nexus.dependencies.get_history_repository", return_value=repo):
        await persist_slack_tokens("user-1", payload)
    kwargs = repo.upsert_oauth_mcp_connection.await_args.kwargs
    assert kwargs["bearer_token"] == "xoxp-user"
    assert kwargs["refresh_token"] == "user-refresh"
    assert kwargs["oauth_token_endpoint"] == SLACK_REFRESH_URL
    assert kwargs["oauth_token_endpoint"] != SLACK_TOKEN_URL
