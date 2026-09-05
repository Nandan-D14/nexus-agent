# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.tools.elicitation import (
    ask_choice,
    format_choice_history_text,
    format_suggestion_history_text,
    normalize_choice_options,
    normalize_suggestion_items,
    suggest_options,
)


def test_normalize_choice_options_accepts_two_to_four_labels() -> None:
    assert normalize_choice_options(
        ["Create a new skill", "Integrate with an existing agent/tool"]
    ) == ["Create a new skill", "Integrate with an existing agent/tool"]

    assert normalize_choice_options(
        ["Option 1", "Option 2", "Option 3", "Option 4"]
    ) == ["Option 1", "Option 2", "Option 3", "Option 4"]


def test_normalize_choice_options_clamps_to_max_four() -> None:
    result = normalize_choice_options(
        ["Option 1", "Option 2", "Option 3", "Option 4", "Option 5", "Option 6"]
    )
    assert result == ["Option 1", "Option 2", "Option 3", "Option 4"]


def test_normalize_choice_options_rejects_single_option() -> None:
    assert normalize_choice_options(["Only one"]) is None
    assert normalize_choice_options([]) is None


def test_normalize_choice_options_parses_json_string_and_strips_numbers() -> None:
    assert normalize_choice_options(
        '["1. Create a new skill", "2. Integrate with an existing agent/tool"]'
    ) == ["Create a new skill", "Integrate with an existing agent/tool"]


def test_normalize_choice_options_dedupes() -> None:
    labels = normalize_choice_options(
        [
            "Create a new skill",
            "create a new skill",
            "Understand how skills work",
            "Something else",
        ]
    )
    assert labels == [
        "Create a new skill",
        "Understand how skills work",
        "Something else",
    ]


def test_format_choice_history_text() -> None:
    text = format_choice_history_text(
        "What do you want to test MCP for?",
        ["Connect a task/project tool", "Just checking how the tool works", "Something else"],
    )
    assert text.startswith("What do you want to test MCP for?")
    assert "1. Connect a task/project tool" in text
    assert "2. Just checking how the tool works" in text
    assert "3. Something else" in text


def test_normalize_suggestion_items() -> None:
    items = [
        {"name": "Gmail", "description": "Draft replies, summarize threads", "action_label": "Connect"},
        {"name": "Google Drive", "description": "Search and read files"},
    ]
    normalized = normalize_suggestion_items(items)
    assert normalized is not None
    assert len(normalized) == 2
    assert normalized[0]["name"] == "Gmail"
    assert normalized[0]["action_label"] == "Connect"
    assert normalized[1]["name"] == "Google Drive"
    assert normalized[1]["action_label"] == "Connect"


def test_normalize_suggestion_items_from_json() -> None:
    raw = '[{"name": "Slack", "description": "Send notifications", "action_label": "Enable"}]'
    normalized = normalize_suggestion_items(raw)
    assert normalized is not None
    assert len(normalized) == 1
    assert normalized[0]["name"] == "Slack"
    assert normalized[0]["action_label"] == "Enable"


def test_format_suggestion_history_text() -> None:
    text = format_suggestion_history_text(
        "Connectors that could help",
        [
            {"name": "Gmail", "description": "Draft replies", "action_label": "Connect"},
            {"name": "Google Drive", "description": "Search files", "action_label": "Connect"},
        ],
    )
    assert "Connectors that could help" in text
    assert "- Gmail: Draft replies [Connect]" in text
    assert "- Google Drive: Search files [Connect]" in text


@pytest.mark.asyncio
async def test_ask_choice_auto_resolves_when_skip_confirmations_active() -> None:
    from nexus.tools._context import clear_skip_confirmations, set_skip_confirmations

    set_skip_confirmations(True)
    try:
        result = await ask_choice("Should I send the email?", options=["Yes, send", "No, cancel"])
        assert result["status"] == "success"
        assert "Yes, send" in result["summary"]
        assert result["metadata"]["selected"] == "Yes, send"
    finally:
        clear_skip_confirmations()


@pytest.mark.asyncio
async def test_suggest_options_auto_resolves_when_skip_confirmations_active() -> None:
    from nexus.tools._context import clear_skip_confirmations, set_skip_confirmations

    set_skip_confirmations(True)
    try:
        result = await suggest_options(
            "Connectors that could help",
            items=[
                {"name": "Gmail", "description": "Draft replies"},
                {"name": "Google Drive", "description": "Search files"},
            ],
        )
        assert result["status"] == "success"
        assert "Gmail" in result["summary"]
        assert result["metadata"]["selected"] == "Gmail"
    finally:
        clear_skip_confirmations()


@pytest.mark.asyncio
async def test_ask_choice_invokes_elicitation_callback() -> None:
    from nexus.tools._context import set_elicitation_callback

    recorded = {}

    async def fake_callback(mode, **kwargs):
        recorded["mode"] = mode
        recorded.update(kwargs)
        return "Just checking how the tool works"

    set_elicitation_callback(fake_callback)
    try:
        result = await ask_choice(
            "What do you want to test MCP for?",
            options=["Connect a task/project tool", "Just checking how the tool works"],
        )
        assert result["status"] == "success"
        assert recorded["mode"] == "choice"
        assert recorded["question"] == "What do you want to test MCP for?"
        assert result["metadata"]["selected"] == "Just checking how the tool works"
    finally:
        set_elicitation_callback(None)


@pytest.mark.asyncio
async def test_suggest_options_invokes_elicitation_callback() -> None:
    from nexus.tools._context import set_elicitation_callback

    recorded = {}

    async def fake_callback(mode, **kwargs):
        recorded["mode"] = mode
        recorded.update(kwargs)
        return "Gmail"

    set_elicitation_callback(fake_callback)
    try:
        result = await suggest_options(
            "Connectors that could help",
            items=[
                {"name": "Gmail", "description": "Draft replies"},
                {"name": "Google Drive", "description": "Search files"},
            ],
        )
        assert result["status"] == "success"
        assert recorded["mode"] == "suggestion"
        assert recorded["title"] == "Connectors that could help"
        assert result["metadata"]["selected"] == "Gmail"
    finally:
        set_elicitation_callback(None)
