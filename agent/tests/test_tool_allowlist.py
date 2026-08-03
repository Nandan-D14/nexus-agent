# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Tests for per-turn tool allowlist resolution and gateway enforcement."""

from __future__ import annotations

import asyncio

from nexus.tool_catalog import (
    ALWAYS_ALLOWED,
    CONNECTOR_TOOLS,
    TOOL_CAPABILITIES,
    is_tool_allowed,
    resolve_tool_allowlist,
)
from nexus.tool_gateway import _check_tool_allowlist, gated_tool
from nexus.tools._context import clear_tool_allowlist, set_tool_allowlist


def test_empty_selection_is_unrestricted():
    assert resolve_tool_allowlist([], []) is None
    assert resolve_tool_allowlist(None, None) is None
    assert is_tool_allowed("gmail_send", None) is True
    assert is_tool_allowed("run_command", None) is True


def test_capability_expands_to_concrete_tools():
    allowlist = resolve_tool_allowlist(["terminal"], [])
    assert allowlist is not None
    assert "run_command" in allowlist
    assert "terminal_worker" in allowlist
    assert "ask_user" in allowlist  # always allowed
    assert "gmail_send" not in allowlist


def test_connector_map_covers_native_providers():
    expected_keys = {
        "gmail",
        "google_drive",
        "google_calendar",
        "google_tasks",
        "github",
        "tavily",
        "tinyfish",
    }
    assert expected_keys.issubset(set(CONNECTOR_TOOLS))

    allowlist = resolve_tool_allowlist([], ["gmail", "github"])
    assert allowlist is not None
    assert "gmail_search" in allowlist
    assert "gmail_send" in allowlist
    assert "github_create_issue" in allowlist
    assert "search_drive" not in allowlist


def test_infrastructure_tools_always_allowed_under_restriction():
    allowlist = resolve_tool_allowlist(["memory"], [])
    assert allowlist is not None
    for name in (
        "ask_user",
        "read_skill",
        "write_workspace_file",
        "read_workspace_file",
        "write_todo_list",
        "initialize_task_state",
    ):
        assert name in ALWAYS_ALLOWED
        assert is_tool_allowed(name, allowlist) is True


def test_mcp_tools_resolved_by_connection_id():
    async def mcp_tool() -> dict:
        return {"status": "ok"}

    mcp_tool.__name__ = "mcp__demo__search"
    setattr(mcp_tool, "_connection_id", "mcp_demo_abc")

    allowlist = resolve_tool_allowlist([], ["mcp_demo_abc"], mcp_tools=[mcp_tool])
    assert allowlist is not None
    assert "mcp__demo__search" in allowlist
    assert is_tool_allowed("mcp__demo__search", allowlist) is True
    assert is_tool_allowed("other_tool", allowlist) is False


def test_gateway_blocks_unselected_tool():
    async def gmail_send() -> dict:
        return {"status": "ok", "sent": True}

    wrapped = gated_tool(gmail_send)
    allowlist = resolve_tool_allowlist(["web_research"], [])
    set_tool_allowlist(allowlist)
    try:
        result = asyncio.run(wrapped())
        assert result["error_code"] == "TOOL_NOT_SELECTED"
        assert result["status"] == "blocked"
        assert "sent" not in result
    finally:
        clear_tool_allowlist()


def test_check_tool_allowlist_helper_passthrough():
    clear_tool_allowlist()
    assert _check_tool_allowlist("anything") is None

    set_tool_allowlist(resolve_tool_allowlist(["artifacts"], []))
    try:
        blocked = _check_tool_allowlist("gmail_send")
        assert blocked is not None
        assert blocked["error_code"] == "TOOL_NOT_SELECTED"
        assert _check_tool_allowlist("publish_html_artifact") is None
        assert _check_tool_allowlist("ask_user") is None
    finally:
        clear_tool_allowlist()


def test_all_capabilities_have_tools():
    assert set(TOOL_CAPABILITIES) == {
        "web_research",
        "terminal",
        "computer_use",
        "artifacts",
        "memory",
    }
    for tools in TOOL_CAPABILITIES.values():
        assert len(tools) > 0
