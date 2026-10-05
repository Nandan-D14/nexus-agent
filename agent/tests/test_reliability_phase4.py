# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Reliability roadmap phase 4: structured intent routing."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from nexus import intent
from nexus.config import settings
from nexus.control_loop import DELIVERABLE_DEMAND_RE, ActionLedger, verify_completion
from nexus.intent import TurnIntent, classify_turn_intent


def _classify(text: str, previous: str = "", model=None):
    with patch.object(settings, "intent_classifier_enabled", True):
        if model is None:
            return asyncio.run(classify_turn_intent(text, previous_task=previous))
        with patch.object(intent, "_model_intent", model):
            return asyncio.run(classify_turn_intent(text, previous_task=previous))


def test_clear_cases_never_call_the_model() -> None:
    model = AsyncMock(side_effect=AssertionError("model must not be called"))
    assert _classify("continue", "build a deck", model).is_followup
    assert _classify("where is my deck", "build a deck", model).is_deliverable_demand
    assert _classify("what went wrong", "build a deck", model).is_error_inquiry
    # No task in progress: nothing to follow up on.
    assert not _classify("sounds good, ship it", "", model).is_followup


def test_ambiguous_short_message_uses_model() -> None:
    model = AsyncMock(return_value=TurnIntent(is_followup=True, source="model"))
    result = _classify("sounds good, ship it", "Create a landing page for Ledgerline", model)
    assert result.is_followup and result.source == "model"
    model.assert_awaited_once()


def test_model_failure_falls_back_to_heuristics() -> None:
    model = AsyncMock(side_effect=RuntimeError("timeout"))
    result = _classify("sounds good, ship it", "Create a landing page", model)
    assert result == TurnIntent()


def test_long_new_request_skips_model() -> None:
    model = AsyncMock(side_effect=AssertionError("model must not be called"))
    long_request = "Research the top ten CRM vendors and compare pricing tiers " * 4
    assert not _classify(long_request, "Create a landing page", model).is_followup


def test_deliverable_demand_regex_is_shared_and_research_safe() -> None:
    assert DELIVERABLE_DEMAND_RE.search("where the heck is my website")
    assert DELIVERABLE_DEMAND_RE.search("give ppt")
    assert not DELIVERABLE_DEMAND_RE.search("where can I read about python packaging")
    result = verify_completion(request="where is my deck", final_response="Here it is.", ledger=ActionLedger())
    assert result.error_code == "MISSING_ARTIFACT"
