from __future__ import annotations

import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.orchestrator import NexusOrchestrator
from nexus.routing import build_current_lookup_queries, classify_request, extract_search_query


class RequestRoutingTests(TestCase):
    def test_simple_question_uses_fast_answer(self) -> None:
        decision = classify_request("What is Python?")

        self.assertEqual(decision.mode, "ask")
        self.assertFalse(decision.needs_full_agent)

    def test_google_tool_capability_question_uses_capability_answer(self) -> None:
        decision = classify_request("do you have gmail and other tools?")

        self.assertEqual(decision.mode, "capability")
        self.assertFalse(decision.needs_full_agent)

    def test_simple_question_with_code_words_stays_fast(self) -> None:
        decision = classify_request("What is a code repository?")

        self.assertEqual(decision.mode, "ask")
        self.assertFalse(decision.needs_full_agent)

    def test_simple_web_search_skips_full_agent(self) -> None:
        decision = classify_request("search web for Gemini docs")

        self.assertEqual(decision.mode, "search")
        self.assertFalse(decision.needs_full_agent)
        self.assertEqual(extract_search_query("search web for Gemini docs"), "Gemini docs")

    def test_current_sports_lookup_skips_full_agent(self) -> None:
        decision = classify_request("what is today's IPL match?")

        self.assertEqual(decision.mode, "current")
        self.assertFalse(decision.needs_full_agent)

    def test_current_news_lookup_skips_full_agent(self) -> None:
        decision = classify_request("latest AI news today")

        self.assertEqual(decision.mode, "current")
        self.assertFalse(decision.needs_full_agent)

    def test_research_news_stays_deep_agent(self) -> None:
        decision = classify_request("research today's news from five sources")

        self.assertEqual(decision.mode, "deep")
        self.assertTrue(decision.needs_full_agent)

    def test_current_ipl_queries_include_targeted_fallbacks(self) -> None:
        queries = build_current_lookup_queries("today IPL match", date_label="2026-04-30")

        self.assertIn("today IPL match", queries)
        self.assertIn("today IPL match 2026-04-30", queries)
        self.assertTrue(any("site:iplt20.com" in item for item in queries))

    def test_gui_request_uses_full_computer_flow(self) -> None:
        decision = classify_request("click the login button on the desktop")

        self.assertEqual(decision.mode, "computer")
        self.assertTrue(decision.needs_full_agent)

    def test_local_work_uses_full_agent_flow(self) -> None:
        decision = classify_request("fix the repo tests and update the code")

        self.assertEqual(decision.mode, "work")
        self.assertTrue(decision.needs_full_agent)

    def test_ambiguous_reference_asks_question_first(self) -> None:
        decision = classify_request("fix it")

        self.assertEqual(decision.mode, "clarify")
        self.assertFalse(decision.needs_full_agent)
        self.assertIn("What exactly", decision.clarification)


class FastSearchRouteTests(IsolatedAsyncioTestCase):
    async def test_fast_search_falls_back_when_no_results_parse(self) -> None:
        orchestrator = NexusOrchestrator.__new__(NexusOrchestrator)
        orchestrator.session = type("SessionStub", (), {"id": "session123"})()
        orchestrator._send_json = AsyncMock()
        orchestrator._send_agent_fast_response = AsyncMock()
        orchestrator._fetch_fast_search_results = AsyncMock(return_value=[])

        with patch("nexus.orchestrator.get_cached_value", return_value=None):
            handled = await orchestrator._run_fast_search("search web for Gemini docs")

        self.assertFalse(handled)
        orchestrator._send_agent_fast_response.assert_not_awaited()
