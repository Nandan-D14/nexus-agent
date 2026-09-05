# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Guards on what reaches the model and what the model can read.

Three separate ways a turn used to degrade: the user's tool selection was only
enforced at call time so the model still saw (and picked) blocked tools; an
uncapped workspace read could put an entire file into the prompt; and Office
uploads had no extraction path at all, so a .docx was invisible to both the
model and retrieval.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

sys.modules.setdefault(
    "redis",
    SimpleNamespace(Redis=object, from_url=lambda *args, **kwargs: None),
)

from nexus.context_window import _filter_tools_to_allowlist
from nexus.mcp_client import _describe_mcp_arguments
from nexus.tools._context import clear_tool_allowlist, set_tool_allowlist


class _Decl:
    def __init__(self, name: str) -> None:
        self.name = name
        self.description = ""
        self.parameters = None


class _Tool:
    def __init__(self, *names: str) -> None:
        self.function_declarations = [_Decl(name) for name in names]


def _names(tools: list) -> list[str]:
    return [
        decl.name
        for tool in tools
        for decl in getattr(tool, "function_declarations", [])
    ]


# --------------------------------------------------------------------------
# Tool schema filtering
# --------------------------------------------------------------------------


def test_unrestricted_selection_hides_nothing() -> None:
    clear_tool_allowlist()
    tools = [_Tool("web_search", "run_command")]

    filtered, hidden = _filter_tools_to_allowlist(tools)

    assert hidden == []
    assert _names(filtered) == ["web_search", "run_command"]


def test_unselected_tools_are_hidden_from_the_model() -> None:
    """Gating only at call time wastes a turn on a tool the model was shown but
    is not allowed to use."""
    token = set_tool_allowlist(frozenset({"web_search"}))
    try:
        filtered, hidden = _filter_tools_to_allowlist([_Tool("web_search", "gmail_send")])
    finally:
        token.var.reset(token)

    assert hidden == ["gmail_send"]
    assert _names(filtered) == ["web_search"]


def test_always_allowed_tools_survive_a_narrow_selection() -> None:
    """Planning, files and skills stay callable regardless of selection, so
    hiding them would break the agent in a way the gateway never would."""
    token = set_tool_allowlist(frozenset({"web_search"}))
    try:
        filtered, hidden = _filter_tools_to_allowlist([_Tool("ask_choice", "read_skill")])
    finally:
        token.var.reset(token)

    assert hidden == []
    assert _names(filtered) == ["ask_choice", "read_skill"]


def test_a_fully_blocked_tool_group_is_removed_entirely() -> None:
    token = set_tool_allowlist(frozenset({"web_search"}))
    try:
        filtered, hidden = _filter_tools_to_allowlist(
            [_Tool("web_search"), _Tool("gmail_send", "gmail_search")]
        )
    finally:
        token.var.reset(token)

    assert sorted(hidden) == ["gmail_search", "gmail_send"]
    assert len(filtered) == 1
    assert _names(filtered) == ["web_search"]


# --------------------------------------------------------------------------
# MCP argument disclosure
# --------------------------------------------------------------------------


def test_mcp_schema_is_folded_into_the_description() -> None:
    """Every MCP tool reaches ADK as `arguments: dict`, so the schema is the
    only thing telling the model which keys to send."""
    described = _describe_mcp_arguments(
        "Search the docs.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look for"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    )

    assert "Search the docs." in described
    assert "query (string, required): What to look for" in described
    assert "limit (integer)" in described


def test_mcp_description_is_unchanged_without_a_schema() -> None:
    assert _describe_mcp_arguments("Plain tool.", None) == "Plain tool."
    assert _describe_mcp_arguments("Plain tool.", {}) == "Plain tool."
    assert _describe_mcp_arguments("Plain tool.", {"properties": {}}) == "Plain tool."


def test_a_huge_mcp_schema_is_clipped() -> None:
    schema = {
        "type": "object",
        "properties": {
            f"field_{index}": {"type": "string", "description": "x" * 200}
            for index in range(40)
        },
    }

    described = _describe_mcp_arguments("Big tool.", schema)

    assert described.endswith("…")
    assert len(described) < 1200


# --------------------------------------------------------------------------
# Office document extraction
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_document_text_rejects_an_unsupported_format() -> None:
    from nexus.tools._context import (
        set_run_id,
        set_sandbox,
        set_session_id,
        set_workspace_path,
    )
    from nexus.tools.docs import extract_document_text

    tokens = [
        set_sandbox(SimpleNamespace()),
        set_session_id("session-1"),
        set_run_id("run-1"),
        set_workspace_path("/home/user/CoComputer/Workspaces/session-1/run-1"),
    ]
    try:
        result = await extract_document_text("notes.pdf")
    finally:
        for token in reversed(tokens):
            token.var.reset(token)

    assert result["status"] == "error"
    assert result["error_code"] == "UNSUPPORTED_FORMAT"
    assert "extract_pdf_text" in result["suggested_alternatives"]
