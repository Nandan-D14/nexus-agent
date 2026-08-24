# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.tools.ask_user import format_ask_user_history_text, normalize_ask_user_options


def test_normalize_accepts_two_or_more_labels() -> None:
    assert normalize_ask_user_options(
        ["Create a new skill", "Integrate with an existing agent/tool"]
    ) == ["Create a new skill", "Integrate with an existing agent/tool"]


def test_normalize_rejects_single_option() -> None:
    assert normalize_ask_user_options(["Only one"]) is None


def test_normalize_parses_json_string_and_strips_numbers() -> None:
    assert normalize_ask_user_options(
        '["1. Create a new skill", "2. Integrate with an existing agent/tool"]'
    ) == ["Create a new skill", "Integrate with an existing agent/tool"]


def test_normalize_dedupes_and_caps_length() -> None:
    labels = normalize_ask_user_options(
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


def test_history_text_appends_numbered_options() -> None:
    text = format_ask_user_history_text(
        "What are you trying to do with Agent Skills?",
        ["Create a new skill", "Something else"],
    )
    assert text.startswith("What are you trying to do with Agent Skills?")
    assert "1. Create a new skill" in text
    assert "2. Something else" in text


def test_history_text_does_not_duplicate_existing_numbers() -> None:
    question = "Pick one:\n1. Alpha\n2. Beta"
    assert format_ask_user_history_text(question, ["Alpha", "Beta"]) == question
