# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Routing tests after the full-agent-only migration.

The fast path / mode router / artifact mini-agent were removed
(``docs/FULL_AGENT_ONLY_MIGRATION_PLAN.md``). The routing shim now always
returns ``needs_full_agent=True`` and every request goes through the planner.
These tests pin that behavior so the planner never gets bypassed again by a
regressed classifier.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.config import settings
from nexus.orchestrator import NexusOrchestrator
from nexus.routing import (
    classify_request,
    classify_request_llm,
    classify_request_simple,
    extract_search_query,
)


class RequestRoutingTests(IsolatedAsyncioTestCase):
    async def test_every_request_goes_to_full_planner(self) -> None:
        for text in [
            "What is Python?",
            "hi",
            "do you have gmail?",
            "search web for Gemini docs",
            "what is today's IPL match?",
            "summarize https://example.com/post and cite sources",
            "Create a simple calculator",
            "Build a Next.js calculator app",
            "click the login button",
            "fix it",
            "",
        ]:
            with self.subTest(text=text):
                decision = await classify_request(text)
                self.assertTrue(
                    decision.needs_full_agent,
                    msg=f"fast path must not exist for {text!r}",
                )

    async def test_llm_and_simple_agree_after_migration(self) -> None:
        text = "research today's news from five sources"
        simple = classify_request_simple(text)
        llm = await classify_request_llm(text)

        self.assertEqual(simple.needs_full_agent, llm.needs_full_agent)
        self.assertTrue(simple.needs_full_agent)

    async def test_context_flags_still_force_full_agent(self) -> None:
        decision = classify_request_simple(
            "summarize my latest emails",
            has_connectors=True,
        )

        self.assertTrue(decision.needs_full_agent)

    def test_extract_search_query_trims_whitespace(self) -> None:
        self.assertEqual(
            extract_search_query("  search  web  for  Gemini  docs  "),
            "search web for Gemini docs",
        )


class TurnRunnerSelectionTests(TestCase):
    def test_single_planner_runner_with_default_cap(self) -> None:
        orchestrator = NexusOrchestrator.__new__(NexusOrchestrator)
        planner_runner = object()
        orchestrator._runner = planner_runner

        runner, turn_cap = orchestrator._select_turn_runner()

        self.assertIs(runner, planner_runner)
        self.assertEqual(turn_cap, settings.max_agent_turns)

    def test_cached_context_is_bound_to_the_session_lifecycle_mode(self) -> None:
        self.assertFalse(NexusOrchestrator._should_load_cached_context("fresh"))
        self.assertTrue(
            NexusOrchestrator._should_load_cached_context("continue_latest_workspace")
        )
        self.assertTrue(
            NexusOrchestrator._should_load_cached_context("continue_conversation")
        )
