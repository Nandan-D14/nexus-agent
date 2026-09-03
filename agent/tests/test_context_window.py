# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Tests for context-window budgeting and gmail_read truncation."""

from __future__ import annotations

import base64
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from google.genai import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.config import settings
from nexus.context_window import make_context_trimmer
from nexus.tools.integrations import _slim_gmail_message


def _text_content(role: str, text: str):
    return types.Content(role=role, parts=[types.Part(text=text)])


def _request(contents, system=None):
    config = SimpleNamespace(system_instruction=system)
    return SimpleNamespace(contents=contents, config=config)


def _trim_note_present(contents) -> bool:
    first = contents[0]
    return any(
        getattr(p, "text", "") and "trimmed to fit" in p.text
        for p in (first.parts or [])
    )


class ContextTrimmerTests(TestCase):
    def setUp(self) -> None:
        self._patchers = [
            patch.object(settings, "enforce_context_budget", True),
            patch.object(settings, "model_context_limit", 1000),
            patch.object(settings, "context_input_budget_ratio", 0.75),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self) -> None:
        for p in self._patchers:
            p.stop()

    def test_no_trim_when_under_budget(self) -> None:
        contents = [
            _text_content("user", "hi"),
            _text_content("model", "hello"),
        ]
        req = _request(list(contents))
        make_context_trimmer()(None, req)
        self.assertEqual(len(req.contents), 2)
        self.assertFalse(_trim_note_present(req.contents))

    def test_trims_oldest_and_keeps_last(self) -> None:
        big = "x" * 2000  # ~508 tokens each; budget ~750
        contents = [
            _text_content("user", "OLD " + big),
            _text_content("model", "MID " + big),
            _text_content("user", "LATEST " + big),
        ]
        req = _request(list(contents))
        make_context_trimmer()(None, req)
        # Oldest dropped, trim note prepended, latest preserved.
        self.assertTrue(_trim_note_present(req.contents))
        self.assertLess(len(req.contents), 4)
        last_text = req.contents[-1].parts[0].text
        self.assertTrue(last_text.startswith("LATEST"))

    def test_disabled_flag_is_noop(self) -> None:
        big = "x" * 5000
        contents = [_text_content("user", big) for _ in range(5)]
        req = _request(list(contents))
        with patch.object(settings, "enforce_context_budget", False):
            make_context_trimmer()(None, req)
        self.assertEqual(len(req.contents), 5)

    def test_drops_leading_orphan_tool_response(self) -> None:
        # Budget floor is 1000 tokens; at ratio 0.75 that is ~750. Size each
        # message near ~370 tokens so exactly the last two fit and the oldest
        # (the function_call) is dropped, orphaning the tool response.
        pad = "y" * 1450  # ~370 tokens each
        call = types.Content(
            role="model",
            parts=[
                types.Part(text=pad),
                types.Part(function_call=types.FunctionCall(name="t", args={"a": 1})),
            ],
        )
        resp = types.Content(
            role="user",
            parts=[
                types.Part(text=pad),
                types.Part(
                    function_response=types.FunctionResponse(name="t", response={"r": 1})
                ),
            ],
        )
        final = _text_content("user", "FINAL " + pad)
        req = _request([call, resp, final])
        make_context_trimmer()(None, req)
        # Trimming happened and no orphaned function_response remains.
        self.assertTrue(_trim_note_present(req.contents))
        for content in req.contents:
            has_fr = any(
                getattr(p, "function_response", None) is not None
                for p in (content.parts or [])
            )
            self.assertFalse(has_fr, "orphan tool response leaked into trimmed context")

    def test_groq_budget_prunes_mcp_tools_on_first_turn(self):
        with patch.object(settings, "model_context_limit", 262144):
            fat = types.FunctionDeclaration(
                name="mcp__exa__web_search_exa",
                description="x" * 20000,
                parameters={
                    "type": "object",
                    "properties": {
                        "q": {"type": "string", "description": "y" * 4000},
                    },
                },
            )
            core = types.FunctionDeclaration(
                name="terminal_worker",
                description="Run shell work",
            )
            req = _request([_text_content("user", "make xlsx")])
            req.config.tools = [
                types.Tool(function_declarations=[fat]),
                types.Tool(function_declarations=[core]),
            ]
            runtime = SimpleNamespace(
                llm_provider="groq",
                llm_api_base="https://api.groq.com/openai/v1",
            )
            make_context_trimmer(runtime)(None, req)
            names = [
                decl.name
                for tool in (req.config.tools or [])
                for decl in (tool.function_declarations or [])
            ]
            self.assertIn("terminal_worker", names)
            self.assertNotIn("mcp__exa__web_search_exa", names)


class GmailSlimTests(TestCase):
    def _raw_message(self, body: str):
        encoded = base64.urlsafe_b64encode(body.encode()).decode()
        return {
            "id": "abc123",
            "threadId": "thr1",
            "labelIds": ["INBOX"],
            "snippet": "preview...",
            "payload": {
                "mimeType": "multipart/alternative",
                "headers": [
                    {"name": "From", "value": "a@b.com"},
                    {"name": "Subject", "value": "Hello"},
                    {"name": "X-Spam", "value": "ignore me"},
                ],
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": encoded}},
                ],
            },
        }

    def test_caps_large_body(self) -> None:
        msg = self._raw_message("z" * 50000)
        slim = _slim_gmail_message(msg, 8000)
        self.assertEqual(len(slim["body"]), 8000)
        self.assertTrue(slim["truncated"])
        self.assertEqual(slim["headers"]["From"], "a@b.com")
        self.assertEqual(slim["headers"]["Subject"], "Hello")
        self.assertNotIn("X-Spam", slim["headers"])
        self.assertEqual(slim["snippet"], "preview...")

    def test_short_body_untouched(self) -> None:
        msg = self._raw_message("short body")
        slim = _slim_gmail_message(msg, 8000)
        self.assertEqual(slim["body"], "short body")
        self.assertFalse(slim["truncated"])

    def test_non_dict_message(self) -> None:
        slim = _slim_gmail_message("weird", 8000)
        self.assertIn("raw", slim)
