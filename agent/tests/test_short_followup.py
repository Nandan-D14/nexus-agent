# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Short follow-ups like 'continue' must resume the prior user task."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.orchestrator import (
    NexusOrchestrator,
    extract_html_dump,
    format_continue_task,
    is_deliverable_demand,
    is_short_followup,
    looks_like_create_or_build,
    looks_like_unpublished_markup,
    looks_like_website_request,
    outstanding_user_task,
)


class ShortFollowupHelpersTests(TestCase):
    def test_confirmations_are_short(self) -> None:
        for text in ("continue", "create it", "do it.", "ok", "go ahead", "try again"):
            self.assertTrue(is_short_followup(text), text)

    def test_real_requests_are_not_short(self) -> None:
        self.assertFalse(
            is_short_followup(
                "ok then can you tell me what is tembo ai , like web proto in react vite"
            )
        )
        self.assertFalse(is_short_followup("Landing page — marketing site"))

    def test_outstanding_task_skips_confirmations(self) -> None:
        messages = [
            {
                "role": "user",
                "text": "ok then can you tell me what is tembo ai , like web proto in react vite",
            },
            {"role": "user", "text": "Landing page"},
            {"role": "user", "text": "create it"},
            {"role": "user", "text": "continue"},
        ]
        goal = outstanding_user_task(messages, "continue")
        self.assertIn("tembo ai", goal.lower())
        self.assertIn("Landing page", goal)
        self.assertNotIn("continue", goal)

    def test_create_or_build_detects_landing_page(self) -> None:
        self.assertTrue(looks_like_create_or_build("Tembo landing page in React Vite"))
        self.assertFalse(looks_like_create_or_build("summarize my emails"))

    def test_continue_brief_names_the_goal(self) -> None:
        brief = format_continue_task("build a Tembo landing page", "create it")
        self.assertIn("[CONTINUE TASK]", brief)
        self.assertIn("Tembo landing page", brief)
        self.assertIn("create it", brief)

    def test_recover_website_on_empty_or_missing_artifact(self) -> None:
        from nexus.orchestrator import should_recover_website

        request = "Create a modern marketing website for my product"
        self.assertTrue(should_recover_website("MISSING_ARTIFACT", request))
        self.assertTrue(should_recover_website("MISSING_FINAL_RESPONSE", request))
        self.assertFalse(should_recover_website("MISSING_FINAL_RESPONSE", "summarize my emails"))
        self.assertFalse(should_recover_website("MISSING_ARTIFACT", "generate a pdf report"))
        self.assertTrue(is_deliverable_demand("where the fuck is my website"))
        self.assertTrue(is_deliverable_demand("where is my website"))
        self.assertFalse(is_deliverable_demand("do you have git and git cli"))
        self.assertTrue(looks_like_website_request(
            "Create a modern marketing website for my product"
        ))
        self.assertFalse(looks_like_website_request("generate a pdf report"))
        self.assertTrue(looks_like_unpublished_markup(
            '<section class="section features" id="features">'
        ))
        self.assertTrue(looks_like_unpublished_markup("Invoice card details: LEDGERLINE"))
        html = extract_html_dump(
            "Invoice card:\n\n"
            '<section class="hero"><div class="wrap">'
            "<h1>Ledgerline</h1>"
            "<p>Get paid faster with invoices that chase themselves across reminders, taxes, and receipts.</p>"
            "<p>Bill to Arcadia Studio LLC. Invoice 0042 is due September 17.</p>"
            "</div></section>"
        )
        self.assertIn("<section", html)
        self.assertGreater(len(html), 200)


class ShortFollowupHandleTextTests(IsolatedAsyncioTestCase):
    async def test_continue_expands_prior_user_task(self) -> None:
        fake = SimpleNamespace(
            session=SimpleNamespace(id="s1"),
            history_repository=SimpleNamespace(
                get_session_messages=AsyncMock(
                    return_value=[
                        {
                            "role": "user",
                            "text": "build a Tembo AI landing page in React Vite",
                        },
                        {"role": "user", "text": "continue"},
                    ]
                )
            ),
            _send_json=AsyncMock(),
            _persist_message=AsyncMock(),
            _build_turn_input=AsyncMock(return_value="TURN_INPUT"),
            _run_agent_tracked=AsyncMock(),
            _seed_context="",
        )
        await NexusOrchestrator.handle_text_input(fake, "continue")
        model_text = fake._build_turn_input.call_args.args[0]
        self.assertIn("[CONTINUE TASK]", model_text)
        self.assertIn("Tembo AI landing page", model_text)
        self.assertEqual(fake._persist_message.call_args.kwargs["text"], "continue")
        self.assertIn(
            "Tembo",
            fake._run_agent_tracked.call_args.kwargs["completion_request"],
        )
        self.assertEqual(
            fake._outstanding_task,
            "build a Tembo AI landing page in React Vite",
        )

    async def test_where_is_website_expands_prior_task(self) -> None:
        fake = SimpleNamespace(
            session=SimpleNamespace(id="s1"),
            history_repository=SimpleNamespace(
                get_session_messages=AsyncMock(
                    return_value=[
                        {
                            "role": "user",
                            "text": "Create a modern marketing website for my product",
                        },
                        {"role": "user", "text": "where the fuck is my website"},
                    ]
                )
            ),
            _send_json=AsyncMock(),
            _persist_message=AsyncMock(),
            _build_turn_input=AsyncMock(return_value="TURN_INPUT"),
            _run_agent_tracked=AsyncMock(),
            _seed_context="",
        )
        await NexusOrchestrator.handle_text_input(fake, "where the fuck is my website")
        model_text = fake._build_turn_input.call_args.args[0]
        self.assertIn("[CONTINUE TASK]", model_text)
        self.assertIn("modern marketing website", model_text)
        self.assertIn(
            "marketing website",
            fake._run_agent_tracked.call_args.kwargs["completion_request"].lower(),
        )

    async def test_full_prompt_is_unchanged(self) -> None:
        fake = SimpleNamespace(
            _send_json=AsyncMock(),
            _persist_message=AsyncMock(),
            _build_turn_input=AsyncMock(return_value="TURN_INPUT"),
            _run_agent_tracked=AsyncMock(),
        )
        await NexusOrchestrator.handle_text_input(fake, "summarize my emails")
        self.assertEqual(
            fake._build_turn_input.call_args.args[0],
            "summarize my emails",
        )
        self.assertEqual(
            fake._run_agent_tracked.call_args.kwargs["completion_request"],
            "summarize my emails",
        )
