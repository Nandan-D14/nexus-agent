# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Tests for the durable-resume leak fix."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.config import Settings, settings
from nexus.orchestrator import NexusOrchestrator
from nexus.agent_turn_runner import AgentTurnRunner


class ResumeContextTests(IsolatedAsyncioTestCase):
    def test_empty_checkpoint_returns_empty(self) -> None:
        self.assertEqual(AgentTurnRunner._resume_context({}), "")

    def test_context_block_excludes_user_text(self) -> None:
        block = AgentTurnRunner._resume_context(
            {"action_ledger": {"records": []}}
        )
        self.assertIn("[DURABLE RESUME CHECKPOINT]", block)
        self.assertIn("No completed action records were restored", block)
        # The original user text must NOT be embedded in the block.
        self.assertFalse(block.startswith("what can you do"))

    async def _call_handle_text_input(self, **kwargs):
        fake = SimpleNamespace(
            _send_json=AsyncMock(),
            _persist_message=AsyncMock(),
            _build_turn_input=AsyncMock(return_value="TURN_INPUT"),
            _run_agent_tracked=AsyncMock(),
        )
        await NexusOrchestrator.handle_text_input(fake, "summarize my emails", **kwargs)
        return fake

    async def test_resume_suppresses_persist_and_transcript(self) -> None:
        fake = await self._call_handle_text_input(
            emit_user_transcript=False,
            resume_context="[DURABLE RESUME CHECKPOINT] ...",
        )
        fake._persist_message.assert_not_awaited()
        fake._send_json.assert_not_awaited()
        # The checkpoint context is fed to the model turn input only.
        model_text = fake._build_turn_input.call_args.args[0]
        self.assertIn("summarize my emails", model_text)
        self.assertIn("[DURABLE RESUME CHECKPOINT]", model_text)

    async def test_normal_turn_persists_and_emits_original_text(self) -> None:
        fake = await self._call_handle_text_input(emit_user_transcript=True)
        fake._persist_message.assert_awaited_once()
        self.assertEqual(
            fake._persist_message.call_args.kwargs["text"], "summarize my emails"
        )
        model_text = fake._build_turn_input.call_args.args[0]
        self.assertEqual(model_text, "summarize my emails")

    def test_provider_validator_accepts_bynara(self) -> None:
        self.assertEqual(
            Settings.validate_model_provider("BYNARA"), "bynara"
        )

    def test_provider_validator_rejects_unknown(self) -> None:
        with self.assertRaises(ValueError):
            Settings.validate_model_provider("openai")
